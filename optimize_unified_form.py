"""
Tuning of unified_form's genuinely free parameters only:
  - TIER_CURRENT_TOURNAMENT_MULT: flat boost any current-tournament match gets
  - MOMENTUM_BOOST_MULT: additional bonus for the most recent games
  - WEIGHT_UNIFIED_FORM: how much the combined signal nudges historical_score

CURRENT_MOMENTUM_MAX_GAMES/DECAY_POWER are now FIXED design constants
("previous 2 matches", linear decay) per explicit user intent, not fit
targets — the earlier 5-param search let those float and overfit badly
(boundary-hugging restarts, holdout got significantly worse). All three
params here are read live per-prediction (not baked into cached
base_teams), so this reuses the same fast cached-dataset pattern as
optimize_gap_weights.py.

Same discipline as every other test this session: train-only fit, CV,
holdout check, 4 random restarts, paired bootstrap on holdout against the
CURRENT (non-unified) model.
"""
import importlib.util
import numpy as np
from scipy.optimize import minimize

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]

BOUNDS = [(0.0, 20.0), (0.0, 20.0), (0.0, 3.0)]

print("Loading datasets...")
train_ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
holdout_ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
fold_ds = {y: wcp.load_backtest_dataset("data", [y]) for y in TRAIN_YEARS}


def apply_params(x):
    wcp.TIER_CURRENT_TOURNAMENT_MULT = float(np.clip(x[0], *BOUNDS[0]))
    wcp.MOMENTUM_BOOST_MULT = float(np.clip(x[1], *BOUNDS[1]))
    wcp.WEIGHT_UNIFIED_FORM = float(np.clip(x[2], *BOUNDS[2]))
    # fixed design constants, not fit
    wcp.CURRENT_MOMENTUM_MAX_GAMES = 2.0
    wcp.CURRENT_MOMENTUM_DECAY_POWER = 1.0


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


wcp.USE_UNIFIED_FORM = True

x0 = np.array([5.0, 5.0, 0.4395])
base_train = train_brier(x0)
base_holdout = holdout_brier(x0)
print(f"\nSTART (guessed)  TIER={x0[0]:.2f} MOMENTUM={x0[1]:.2f} WEIGHT={x0[2]:.4f}")
print(f"  train={base_train:.4f}  holdout={base_holdout:.4f}")

print("\nOptimizing (3 free params, 4 restarts)...")
np.random.seed(15)
starts = [x0] + [
    np.array([np.random.uniform(0, 15), np.random.uniform(0, 15), np.random.uniform(0.1, 2)])
    for _ in range(3)
]
best = None
for i, sx0 in enumerate(starts):
    r = minimize(train_brier, sx0, method="Nelder-Mead", bounds=BOUNDS,
                 options={"xatol": 1e-4, "fatol": 1e-7, "maxiter": 1500})
    ho = holdout_brier(r.x)
    print(f"  start {i}: TIER={r.x[0]:.3f} MOMENTUM={r.x[1]:.3f} WEIGHT={r.x[2]:.4f}  "
          f"train={r.fun:.4f}  holdout={ho:.4f}")
    if best is None or r.fun < best.fun:
        best = r

apply_params(best.x)
opt_train = train_brier(best.x)
opt_cv = cv_briers(best.x)
opt_holdout = holdout_brier(best.x)
print(f"\nBEST  TIER={best.x[0]:.3f} MOMENTUM={best.x[1]:.3f} WEIGHT={best.x[2]:.4f}")
print(f"  train={opt_train:.4f}  cv_mean={np.mean(opt_cv):.4f}  cv_std={np.std(opt_cv):.4f}  holdout={opt_holdout:.4f}")

# --- reference: current (non-unified) model ---
wcp.USE_UNIFIED_FORM = False
ref_train, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=train_ds)
ref_holdout, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds)
print(f"\n--- Summary ---")
print(f"train:   current={ref_train:.4f}  unified={opt_train:.4f}  (delta {opt_train-ref_train:+.4f})")
print(f"holdout: current={ref_holdout:.4f}  unified={opt_holdout:.4f}  (delta {opt_holdout-ref_holdout:+.4f})")

# --- paired bootstrap on holdout ---
_, _, ref_err_list = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds, return_errors=True)
ref_err = {(y, eid): e for (y, eid, e) in ref_err_list}
wcp.USE_UNIFIED_FORM = True
apply_params(best.x)
_, _, opt_err_list = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds, return_errors=True)
opt_err = {(y, eid): e for (y, eid, e) in opt_err_list}
common = sorted(set(ref_err) & set(opt_err))
a = np.array([ref_err[k] for k in common])
b = np.array([opt_err[k] for k in common])
diffs = a - b
rng = np.random.default_rng(0)
n = len(common)
boot = np.array([diffs[rng.integers(0, n, n)].mean() for _ in range(5000)])
lo, hi = np.percentile(boot, [2.5, 97.5])
print(f"\nbootstrap (current - unified): {diffs.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  significant={(lo>0) or (hi<0)}")
