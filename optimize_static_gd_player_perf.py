"""
Joint re-optimization of:
  - WEIGHT_STATIC_GD / WEIGHT_PLAYER_PERF (never tuned this rigorously
    before -- still the original hand-picked 0.45/0.55 from project start)
  - W_BASE / W_TAC / W_H2H / W_REL_GD / K_SIG (the gap-combination weights,
    already adopted once, but worth re-checking now that intl_form changed
    the scale/distribution of the "historical" component they were
    originally tuned against)

Both groups are read LIVE per-prediction (not baked into base_teams at
load time), so this reuses cached datasets the same way optimize_gap_weights.py
did -- no HIST_DECAY-style dataset rebuild needed.

Reparametrization: 3 unconstrained reals -> softmax -> W_BASE/W_TAC/W_H2H/W_REL_GD
(always positive, sums to 1), 1 more -> sigmoid -> WEIGHT_STATIC_GD /
(1 - that) -> WEIGHT_PLAYER_PERF, plus K_SIG directly. 6 free parameters
total against 320 training matches.

NOTE: the WC-specific train/holdout split (320/163) is unchanged by any of
the international-corpus work -- that expansion only helped intl_form,
which was validated on its own separate, much larger corpus. This
optimization has exactly the same statistical power it always would have.
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
CURRENT_STATIC_GD = wcp.WEIGHT_STATIC_GD
CURRENT_PLAYER_PERF = wcp.WEIGHT_PLAYER_PERF

print("Loading datasets (USE_INTL_FORM stays at its live default)...")
print(f"  USE_INTL_FORM={wcp.USE_INTL_FORM}  WEIGHT_INTL_FORM={wcp.WEIGHT_INTL_FORM}")
train_ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
holdout_ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
fold_ds = {y: wcp.load_backtest_dataset("data", [y]) for y in TRAIN_YEARS}


def softmax4(u):
    e = np.exp(u - np.max(u))
    return e / e.sum()


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def apply_params(x):
    w = softmax4(np.array(x[:4]))
    wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = [float(v) for v in w]
    wcp.K_SIG = float(np.clip(x[4], 0.3, 4.0))
    s = float(sigmoid(x[5]))
    wcp.WEIGHT_STATIC_GD = s
    wcp.WEIGHT_PLAYER_PERF = 1.0 - s


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


u0 = np.log(np.array(CURRENT_W) + 1e-9)
logit0 = np.log(CURRENT_STATIC_GD / (1 - CURRENT_STATIC_GD))
x0 = np.array([*u0, CURRENT_K_SIG, logit0])

base_train = train_brier(x0)
base_cv = cv_briers(x0)
base_holdout = holdout_brier(x0)
print(f"\nCURRENT  W_BASE={CURRENT_W[0]:.3f} W_TAC={CURRENT_W[1]:.3f} W_H2H={CURRENT_W[2]:.3f} "
      f"W_REL_GD={CURRENT_W[3]:.3f} K_SIG={CURRENT_K_SIG:.3f} "
      f"STATIC_GD={CURRENT_STATIC_GD:.3f} PLAYER_PERF={CURRENT_PLAYER_PERF:.3f}")
print(f"  train={base_train:.4f}  cv_mean={np.mean(base_cv):.4f}  cv_std={np.std(base_cv):.4f}  holdout={base_holdout:.4f}")

print("\nOptimizing (6 free params, 4 restarts)...")
np.random.seed(6)
starts = [x0] + [
    np.array([*np.random.uniform(-2, 2, 4), np.random.uniform(0.5, 2.5), np.random.uniform(-2, 2)])
    for _ in range(3)
]
best = None
for i, sx0 in enumerate(starts):
    r = minimize(train_brier, sx0, method="Nelder-Mead",
                 options={"xatol": 1e-5, "fatol": 1e-8, "maxiter": 2000})
    apply_params(r.x)
    w = (wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD)
    ho = holdout_brier(r.x)
    print(f"  start {i}: W_BASE={w[0]:.3f} W_TAC={w[1]:.3f} W_H2H={w[2]:.3f} W_REL_GD={w[3]:.3f} "
          f"K_SIG={wcp.K_SIG:.3f} STATIC_GD={wcp.WEIGHT_STATIC_GD:.3f}  train={r.fun:.4f}  holdout={ho:.4f}")
    if best is None or r.fun < best.fun:
        best = r

apply_params(best.x)
opt_w = (wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD)
opt_k_sig = wcp.K_SIG
opt_static_gd = wcp.WEIGHT_STATIC_GD
opt_train = train_brier(best.x)
opt_cv = cv_briers(best.x)
opt_holdout = holdout_brier(best.x)

print(f"\nBEST  W_BASE={opt_w[0]:.3f} W_TAC={opt_w[1]:.3f} W_H2H={opt_w[2]:.3f} W_REL_GD={opt_w[3]:.3f} "
      f"K_SIG={opt_k_sig:.3f} STATIC_GD={opt_static_gd:.3f} PLAYER_PERF={1-opt_static_gd:.3f}")
print(f"  train={opt_train:.4f}  cv_mean={np.mean(opt_cv):.4f}  cv_std={np.std(opt_cv):.4f}  holdout={opt_holdout:.4f}")

print(f"\n--- Summary ---")
print(f"train:   {base_train:.4f} -> {opt_train:.4f}  (delta {opt_train-base_train:+.4f})")
print(f"cv_mean: {np.mean(base_cv):.4f} -> {np.mean(opt_cv):.4f}  (delta {np.mean(opt_cv)-np.mean(base_cv):+.4f})")
print(f"holdout: {base_holdout:.4f} -> {opt_holdout:.4f}  (delta {opt_holdout-base_holdout:+.4f})")

print("\n--- Paired bootstrap: current vs optimized, holdout ---")
apply_params(x0)
_, _, base_err_list = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds, return_errors=True)
base_err = {(y, eid): e for (y, eid, e) in base_err_list}
apply_params(best.x)
_, _, opt_err_list = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds, return_errors=True)
opt_err = {(y, eid): e for (y, eid, e) in opt_err_list}
common = sorted(set(base_err) & set(opt_err))
b_arr = np.array([base_err[k] for k in common])
o_arr = np.array([opt_err[k] for k in common])
diffs = b_arr - o_arr
rng = np.random.default_rng(0)
n = len(common)
boot = np.array([diffs[rng.integers(0, n, n)].mean() for _ in range(5000)])
lo, hi = np.percentile(boot, [2.5, 97.5])
print(f"  current - optimized: {diffs.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  significant={(lo>0) or (hi<0)}")
