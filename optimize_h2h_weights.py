"""
Fourth optimization group: ALPHA_H2H, H2H_DECAY_POWER, and the two
H2H_TIER_WEIGHTS entries (world_cup, friendly — "other" anchored at 1.0).
H2H_MAX_AGE_YEARS is left fixed at 5: that was an explicit user design
decision ("H2H should max take data from 5 years before the prediction
match date"), not a free knob.

Unlike the historical-score decay, these ARE safe against a cached dataset:
compute_h2h_per_team() reads ALPHA_H2H/H2H_DECAY_POWER/H2H_TIER_WEIGHTS as
live globals per prediction (confirmed by reading the function), nothing is
baked into base_teams at load time.

Revisited after correcting a stale assumption: 66.9% of backtest matches
(323/483) have at least one qualifying H2H pair with the current 10,380-row
dataset (1998-2026 coverage) — this component has real signal behind it now,
unlike when an old in-code comment (from the placeholder-data era) said H2H
coverage started at 2020.
"""
import importlib.util
import numpy as np
from scipy.optimize import minimize

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]

DEFAULT_ALPHA_H2H = wcp.ALPHA_H2H
DEFAULT_H2H_DECAY_POWER = wcp.H2H_DECAY_POWER
DEFAULT_WC_TIER = wcp.H2H_TIER_WEIGHTS["world_cup"]
DEFAULT_FRIENDLY_TIER = wcp.H2H_TIER_WEIGHTS["friendly"]

print("Loading datasets...")
train_ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
holdout_ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
fold_ds = {y: wcp.load_backtest_dataset("data", [y]) for y in TRAIN_YEARS}

BOUNDS = [(0.005, 0.15), (0.3, 4.0), (0.8, 3.0), (0.2, 1.5)]


def apply_params(x):
    wcp.ALPHA_H2H = float(np.clip(x[0], *BOUNDS[0]))
    wcp.H2H_DECAY_POWER = float(np.clip(x[1], *BOUNDS[1]))
    wcp.H2H_TIER_WEIGHTS = {
        "world_cup": float(np.clip(x[2], *BOUNDS[2])),
        "other": 1.0,
        "friendly": float(np.clip(x[3], *BOUNDS[3])),
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


x0 = np.array([DEFAULT_ALPHA_H2H, DEFAULT_H2H_DECAY_POWER, DEFAULT_WC_TIER, DEFAULT_FRIENDLY_TIER])

base_train = train_brier(x0)
base_cv = cv_briers(x0)
base_holdout = holdout_brier(x0)
print(f"\nBASELINE  ALPHA_H2H={x0[0]:.4f} H2H_DECAY_POWER={x0[1]:.3f} "
      f"tier(wc={x0[2]:.3f}, other=1.0, friendly={x0[3]:.3f})")
print(f"  train={base_train:.4f}  cv_mean={np.mean(base_cv):.4f}  cv_std={np.std(base_cv):.4f}  holdout={base_holdout:.4f}")
print(f"  cv per-year: " + " ".join(f"{y}:{s:.4f}" for y, s in zip(TRAIN_YEARS, base_cv)))

print("\nOptimizing (Nelder-Mead, bounded, train Brier only)...")
result = minimize(train_brier, x0, method="Nelder-Mead", bounds=BOUNDS,
                   options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 500})

opt_x = result.x
apply_params(opt_x)
opt_train = train_brier(opt_x)
opt_cv = cv_briers(opt_x)
opt_holdout = holdout_brier(opt_x)

print(f"\nOPTIMIZED  ALPHA_H2H={opt_x[0]:.4f} H2H_DECAY_POWER={opt_x[1]:.3f} "
      f"tier(wc={opt_x[2]:.3f}, other=1.0, friendly={opt_x[3]:.3f})")
print(f"  train={opt_train:.4f}  cv_mean={np.mean(opt_cv):.4f}  cv_std={np.std(opt_cv):.4f}  holdout={opt_holdout:.4f}")
print(f"  cv per-year: " + " ".join(f"{y}:{s:.4f}" for y, s in zip(TRAIN_YEARS, opt_cv)))

print("\n--- Random-restart robustness check ---")
np.random.seed(11)
for trial in range(4):
    rx0 = np.array([np.random.uniform(*b) for b in BOUNDS])
    r = minimize(train_brier, rx0, method="Nelder-Mead", bounds=BOUNDS,
                 options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 500})
    apply_params(r.x)
    ho = holdout_brier(r.x)
    print(f"  trial {trial}: ALPHA_H2H={r.x[0]:.4f} H2H_DECAY_POWER={r.x[1]:.3f} "
          f"tier(wc={r.x[2]:.3f}, friendly={r.x[3]:.3f})  train={r.fun:.4f} holdout={ho:.4f}")

print(f"\n--- Summary ---")
print(f"train:   {base_train:.4f} -> {opt_train:.4f}  (delta {opt_train-base_train:+.4f})")
print(f"cv_mean: {np.mean(base_cv):.4f} -> {np.mean(opt_cv):.4f}  (delta {np.mean(opt_cv)-np.mean(base_cv):+.4f})")
print(f"holdout: {base_holdout:.4f} -> {opt_holdout:.4f}  (delta {opt_holdout-base_holdout:+.4f})")
