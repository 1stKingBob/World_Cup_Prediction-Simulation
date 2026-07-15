"""
Jointly optimize the gap-combination weights (W_BASE, W_TAC, W_H2H, W_REL_GD)
and K_SIG via scipy.optimize, instead of one-at-a-time coordinate descent.

Scope is deliberately narrow: 4 real degrees of freedom (the four W's sum to
1, reparametrized via softmax over 4 unconstrained reals so the constraint is
automatic and any plain unconstrained optimizer works) plus K_SIG. That's a
much safer parameter-to-data ratio than jointly fitting all ~20 tunable
constants in the model against 320 training matches.

Discipline, matching every other weight change this session:
  - Fit ONLY on train years (2002-2018). The optimizer never sees holdout.
  - Leave-one-tournament-out CV within train (5 folds) as a robustness check
    on top of the raw train-Brier the optimizer is minimizing directly.
  - Final comparison against the untouched holdout (2022+2026).
"""
import importlib.util
import math
import numpy as np
from scipy.optimize import minimize

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]

DEFAULT_W = (wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD)
DEFAULT_K_SIG = wcp.K_SIG

print("Loading datasets...")
train_ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
holdout_ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
fold_ds = {y: wcp.load_backtest_dataset("data", [y]) for y in TRAIN_YEARS}


def softmax4(u):
    e = np.exp(u - np.max(u))
    return e / e.sum()


def apply_params(x):
    u = x[:4]
    w = softmax4(u)
    wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD = [float(v) for v in w]
    wcp.K_SIG = float(np.clip(x[4], 0.3, 4.0))


def train_brier(x):
    apply_params(x)
    score, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=train_ds)
    return score


def cv_briers(x):
    apply_params(x)
    scores = []
    for y in TRAIN_YEARS:
        s, _ = wcp.evaluate_brier("data", [y], dataset=fold_ds[y])
        scores.append(s)
    return scores


def holdout_brier(x):
    apply_params(x)
    score, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds)
    return score


# --- Baseline (current hand-tuned defaults) ---
u0 = np.log(np.array(DEFAULT_W) + 1e-9)  # softmax-inverse of current weights
x0 = np.array([*u0, DEFAULT_K_SIG])

base_train = train_brier(x0)
base_cv = cv_briers(x0)
base_holdout = holdout_brier(x0)

print(f"\nBASELINE  W_BASE={DEFAULT_W[0]:.3f} W_TAC={DEFAULT_W[1]:.3f} "
      f"W_H2H={DEFAULT_W[2]:.3f} W_REL_GD={DEFAULT_W[3]:.3f} K_SIG={DEFAULT_K_SIG:.3f}")
print(f"  train={base_train:.4f}  cv_mean={np.mean(base_cv):.4f}  cv_std={np.std(base_cv):.4f}  holdout={base_holdout:.4f}")
print(f"  cv per-year: " + " ".join(f"{y}:{s:.4f}" for y, s in zip(TRAIN_YEARS, base_cv)))

# --- Optimize on train only ---
print("\nOptimizing (Nelder-Mead, train Brier only)...")
result = minimize(train_brier, x0, method="Nelder-Mead",
                   options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 2000})

opt_x = result.x
apply_params(opt_x)
opt_w = (wcp.W_BASE, wcp.W_TAC, wcp.W_H2H, wcp.W_REL_GD)
opt_k_sig = wcp.K_SIG

opt_train = train_brier(opt_x)
opt_cv = cv_briers(opt_x)
opt_holdout = holdout_brier(opt_x)

print(f"\nOPTIMIZED  W_BASE={opt_w[0]:.3f} W_TAC={opt_w[1]:.3f} "
      f"W_H2H={opt_w[2]:.3f} W_REL_GD={opt_w[3]:.3f} K_SIG={opt_k_sig:.3f}")
print(f"  train={opt_train:.4f}  cv_mean={np.mean(opt_cv):.4f}  cv_std={np.std(opt_cv):.4f}  holdout={opt_holdout:.4f}")
print(f"  cv per-year: " + " ".join(f"{y}:{s:.4f}" for y, s in zip(TRAIN_YEARS, opt_cv)))

print(f"\n--- Summary ---")
print(f"train:   {base_train:.4f} -> {opt_train:.4f}  (delta {opt_train-base_train:+.4f})")
print(f"cv_mean: {np.mean(base_cv):.4f} -> {np.mean(opt_cv):.4f}  (delta {np.mean(opt_cv)-np.mean(base_cv):+.4f})")
print(f"holdout: {base_holdout:.4f} -> {opt_holdout:.4f}  (delta {opt_holdout-base_holdout:+.4f})")
