"""
Follow-up to test_drop_tactical.py: that test only let the no-tactical
model compensate through 4 parameters (W_BASE/W_H2H/W_REL_GD/K_SIG) — a
narrow search that structurally favors "removal costs nothing" regardless
of the truth. This version gives it every lever that's safe to include
(everything read live per-prediction, so no expensive dataset rebuild
needed): relative_gd's own internals (K_REL, K_FORM, RGD_PRIOR_GAMES) and
H2H's shape (H2H_DECAY_POWER, tier weights for world_cup/friendly), on top
of the same 3-way gap split + K_SIG. That's ~10 free parameters against 320
training matches — a real overfitting risk, so this keeps the same
discipline as everything else this session: fit on train only, check via
leave-one-tournament-out CV, validate against the untouched holdout, and
report honestly whether it generalizes or not.
"""
import importlib.util
import numpy as np
from scipy.optimize import minimize

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]

CURRENT_W = (wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD)
CURRENT_K_SIG = wcp.K_SIG
CURRENT_K_REL, CURRENT_K_FORM, CURRENT_PRIOR = wcp.K_REL, wcp.K_FORM, wcp.RGD_PRIOR_GAMES
CURRENT_DECAY_POWER = wcp.H2H_DECAY_POWER
CURRENT_TIER = dict(wcp.H2H_TIER_WEIGHTS)

print("Loading datasets...")
train_ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
holdout_ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
fold_ds = {y: wcp.load_backtest_dataset("data", [y]) for y in TRAIN_YEARS}

# x = [u1,u2,u3 (softmax->Base/H2H/RelGD), K_SIG, K_REL, K_FORM, RGD_PRIOR_GAMES,
#      H2H_DECAY_POWER, tier_wc, tier_friendly]
BOUNDS = [(-5,5),(-5,5),(-5,5), (0.3,4.0), (0.05,1.5), (0.0,2.0), (0.0,8.0),
          (0.3,4.0), (0.8,3.0), (0.2,1.5)]


def softmax3(u):
    e = np.exp(u - np.max(u))
    return e / e.sum()


def apply_params(x):
    w_base, w_h2h, w_relgd = softmax3(np.array(x[:3]))
    wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = float(w_base), 0.0, float(w_h2h), float(w_relgd)
    wcp.K_SIG = float(np.clip(x[3], *BOUNDS[3]))
    wcp.K_REL = float(np.clip(x[4], *BOUNDS[4]))
    wcp.K_FORM = float(np.clip(x[5], *BOUNDS[5]))
    wcp.RGD_PRIOR_GAMES = float(np.clip(x[6], *BOUNDS[6]))
    wcp.H2H_DECAY_POWER = float(np.clip(x[7], *BOUNDS[7]))
    wcp.H2H_TIER_WEIGHTS = {
        "world_cup": float(np.clip(x[8], *BOUNDS[8])),
        "other": 1.0,
        "friendly": float(np.clip(x[9], *BOUNDS[9])),
    }


def train_brier(x):
    apply_params(x)
    s, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=train_ds)
    return s


def cv_briers(x):
    apply_params(x)
    return [wcp.evaluate_brier("data", [y], dataset=fold_ds[y])[0] for y in TRAIN_YEARS]


def holdout_brier(x):
    apply_params(x)
    s, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds)
    return s


# --- Reference: current (adopted) 4-component model ---
wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = CURRENT_W
wcp.K_SIG, wcp.K_REL, wcp.K_FORM, wcp.RGD_PRIOR_GAMES = CURRENT_K_SIG, CURRENT_K_REL, CURRENT_K_FORM, CURRENT_PRIOR
wcp.H2H_DECAY_POWER, wcp.H2H_TIER_WEIGHTS = CURRENT_DECAY_POWER, CURRENT_TIER
ref_train, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=train_ds)
ref_holdout, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds)
print(f"\nCURRENT (adopted, with tactical): train={ref_train:.4f}  holdout={ref_holdout:.4f}")

x0 = np.array([
    np.log(CURRENT_W[0]), np.log(CURRENT_W[2]), np.log(CURRENT_W[3]),
    CURRENT_K_SIG, CURRENT_K_REL, CURRENT_K_FORM, CURRENT_PRIOR,
    CURRENT_DECAY_POWER, CURRENT_TIER["world_cup"], CURRENT_TIER["friendly"],
])

print("\nOptimizing full 10-parameter no-tactical model (train Brier only)...")
best_result = None
np.random.seed(5)
starts = [x0] + [np.array([
    *np.random.uniform(-2, 2, 3),
    np.random.uniform(0.5, 2.5), np.random.uniform(0.1, 1.0), np.random.uniform(0.1, 1.5),
    np.random.uniform(0.5, 5.0), np.random.uniform(0.5, 2.5), np.random.uniform(1.0, 2.0), np.random.uniform(0.4, 1.0),
]) for _ in range(3)]

for i, sx0 in enumerate(starts):
    r = minimize(train_brier, sx0, method="Nelder-Mead", bounds=BOUNDS,
                 options={"xatol": 1e-4, "fatol": 1e-7, "maxiter": 3000, "maxfev": 4000})
    apply_params(r.x)
    ho = holdout_brier(r.x)
    print(f"  start {i}: train={r.fun:.4f}  holdout={ho:.4f}")
    if best_result is None or r.fun < best_result.fun:
        best_result = r

opt_x = best_result.x
apply_params(opt_x)
opt_w = (wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD)
opt_train = train_brier(opt_x)
opt_cv = cv_briers(opt_x)
opt_holdout = holdout_brier(opt_x)

print(f"\nBEST NO-TACTICAL (full 10-param search):")
print(f"  W_BASE={opt_w[0]:.3f} W_H2H={opt_w[2]:.3f} W_REL_GD={opt_w[3]:.3f} K_SIG={wcp.K_SIG:.3f}")
print(f"  K_REL={wcp.K_REL:.3f} K_FORM={wcp.K_FORM:.3f} RGD_PRIOR_GAMES={wcp.RGD_PRIOR_GAMES:.3f}")
print(f"  H2H_DECAY_POWER={wcp.H2H_DECAY_POWER:.3f} tier_wc={wcp.H2H_TIER_WEIGHTS['world_cup']:.3f} tier_friendly={wcp.H2H_TIER_WEIGHTS['friendly']:.3f}")
print(f"  train={opt_train:.4f}  cv_mean={np.mean(opt_cv):.4f}  cv_std={np.std(opt_cv):.4f}  holdout={opt_holdout:.4f}")

# --- Paired bootstrap vs current, on holdout ---
print("\n--- Paired bootstrap: current (with tactical) vs best no-tactical, holdout ---")
wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = CURRENT_W
wcp.K_SIG, wcp.K_REL, wcp.K_FORM, wcp.RGD_PRIOR_GAMES = CURRENT_K_SIG, CURRENT_K_REL, CURRENT_K_FORM, CURRENT_PRIOR
wcp.H2H_DECAY_POWER, wcp.H2H_TIER_WEIGHTS = CURRENT_DECAY_POWER, CURRENT_TIER
_, _, ref_errors_list = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds, return_errors=True)
ref_errors = {(y, eid): e for (y, eid, e) in ref_errors_list}

apply_params(opt_x)
_, _, opt_errors_list = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds, return_errors=True)
opt_errors = {(y, eid): e for (y, eid, e) in opt_errors_list}

common = sorted(set(ref_errors) & set(opt_errors))
ref_arr = np.array([ref_errors[k] for k in common])
opt_arr = np.array([opt_errors[k] for k in common])
diffs = ref_arr - opt_arr
rng = np.random.default_rng(0)
n = len(common)
boot = np.array([diffs[rng.integers(0, n, n)].mean() for _ in range(5000)])
lo, hi = np.percentile(boot, [2.5, 97.5])
print(f"  current - no_tactical: {diffs.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  significant={(lo>0) or (hi<0)}")

print(f"\n--- Summary ---")
print(f"train:   current={ref_train:.4f}  no_tactical={opt_train:.4f}  (delta {opt_train-ref_train:+.4f})")
print(f"holdout: current={ref_holdout:.4f}  no_tactical={opt_holdout:.4f}  (delta {opt_holdout-ref_holdout:+.4f})")
