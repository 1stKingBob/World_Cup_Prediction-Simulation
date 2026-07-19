"""
Test: does dropping the tactical-matchup component entirely (W_TAC=0) and
redistributing its weight among Base/H2H/Relative-GD do better, worse, or
about the same as the current 4-component model? Unlike the other three
components, the tactical matrix is a fixed hand-picked lookup table
(+-0.02 to +-0.04 per style pairing) that's never been fitted against real
match data — a reasonable thing to be suspicious of.

Same discipline as every other weight-tuning script this session: 3-way
softmax over Base/H2H/Relative-GD (always positive, sums to 1) + K_SIG,
fit on train years only, checked via leave-one-tournament-out CV, and
validated against the untouched holdout.
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

print("Loading datasets...")
train_ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
holdout_ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
fold_ds = {y: wcp.load_backtest_dataset("data", [y]) for y in TRAIN_YEARS}


def softmax3(u):
    e = np.exp(u - np.max(u))
    return e / e.sum()


def apply_params(x):
    """x[:3] -> Base/H2H/RelGD via softmax, W_TAC pinned at 0. x[3] -> K_SIG."""
    w_base, w_h2h, w_relgd = softmax3(x[:3])
    wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = float(w_base), 0.0, float(w_h2h), float(w_relgd)
    wcp.K_SIG = float(np.clip(x[3], 0.3, 4.0))


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


# --- Reference: current 4-component model ---
wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = CURRENT_W
wcp.K_SIG = CURRENT_K_SIG
ref_train, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=train_ds)
ref_holdout, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds)
print(f"\nCURRENT (4-component, W_TAC={CURRENT_W[1]:.3f}):")
print(f"  train={ref_train:.4f}  holdout={ref_holdout:.4f}")

# --- Optimize the 3-component (no tactical) model ---
x0 = np.array([np.log(CURRENT_W[0]), np.log(CURRENT_W[2]), np.log(CURRENT_W[3]), CURRENT_K_SIG])
print("\nOptimizing 3-component model (W_TAC pinned at 0)...")
result = minimize(train_brier, x0, method="Nelder-Mead",
                   options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 1000})

opt_x = result.x
apply_params(opt_x)
opt_w = (wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD)
opt_train = train_brier(opt_x)
opt_cv = cv_briers(opt_x)
opt_holdout = holdout_brier(opt_x)

print(f"\nNO-TACTICAL  W_BASE={opt_w[0]:.3f} W_H2H={opt_w[2]:.3f} W_REL_GD={opt_w[3]:.3f} K_SIG={wcp.K_SIG:.3f}")
print(f"  train={opt_train:.4f}  cv_mean={np.mean(opt_cv):.4f}  cv_std={np.std(opt_cv):.4f}  holdout={opt_holdout:.4f}")

# --- Random-restart robustness check ---
print("\n--- Random-restart robustness check ---")
np.random.seed(3)
for trial in range(3):
    rx0 = np.array([*np.random.uniform(-1, 1, 3), np.random.uniform(0.5, 2.5)])
    r = minimize(train_brier, rx0, method="Nelder-Mead",
                 options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 1000})
    apply_params(r.x)
    w = (wcp.W_BASE, wcp.W_H2H, wcp.W_REL_GD)
    ho = holdout_brier(r.x)
    print(f"  trial {trial}: W_BASE={w[0]:.3f} W_H2H={w[1]:.3f} W_REL_GD={w[2]:.3f} K_SIG={wcp.K_SIG:.3f}  train={r.fun:.4f} holdout={ho:.4f}")

# --- Paired bootstrap: is the difference real or noise? ---
print("\n--- Paired bootstrap: current (4-comp) vs no-tactical (3-comp), holdout ---")
wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = CURRENT_W
wcp.K_SIG = CURRENT_K_SIG
_, _, ref_errors_list = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds, return_errors=True)
ref_errors = {(y, eid): e for (y, eid, e) in ref_errors_list}

apply_params(opt_x)
_, _, opt_errors_list = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds, return_errors=True)
opt_errors = {(y, eid): e for (y, eid, e) in opt_errors_list}

common = sorted(set(ref_errors) & set(opt_errors))
ref_arr = np.array([ref_errors[k] for k in common])
opt_arr = np.array([opt_errors[k] for k in common])
diffs = ref_arr - opt_arr  # positive means current (with tactical) is WORSE than no-tactical
rng = np.random.default_rng(0)
n = len(common)
boot = np.array([diffs[rng.integers(0, n, n)].mean() for _ in range(5000)])
lo, hi = np.percentile(boot, [2.5, 97.5])
print(f"  matched matches: {n}")
print(f"  current - no_tactical: {diffs.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  significant={(lo>0) or (hi<0)}")

print(f"\n--- Summary ---")
print(f"train:   current={ref_train:.4f}  no_tactical={opt_train:.4f}  (delta {opt_train-ref_train:+.4f})")
print(f"holdout: current={ref_holdout:.4f}  no_tactical={opt_holdout:.4f}  (delta {opt_holdout-ref_holdout:+.4f})")
