"""
Tune FORM_DECAY_XI for intl_form's exponential-decay path (per-day
exp(-xi*days), matching dixon_coles.py's own decay on the same real-dated
corpus) as a straight swap-in for the current power-law-with-hard-cutoff
shape (FORM_MAX_AGE_YEARS/FORM_DECAY_POWER).

Unlike gap-weight tuning, FORM_DECAY_XI is baked into the CACHED dataset at
load time (_compute_intl_form_corpus_partial runs once inside
load_teams_from_csv) — so every candidate needs load_backtest_dataset()
rebuilt, not just a live constant swap. Measured at ~0.9s per year to
rebuild; a handful of restarts is still comfortably fast (see the timing
check before this script was written).

Same discipline as every other tuning pass this session: train-only fit,
multiple random restarts, holdout check after fitting (never during),
paired bootstrap significance test before calling anything adopted.
"""
import importlib.util
import numpy as np
from scipy.optimize import minimize_scalar

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]
BOUNDS = (0.00005, 0.02)   # ~half-life of 100 days to ~40 years

wcp.USE_EXPONENTIAL_FORM_DECAY = True


def train_brier(xi):
    wcp.FORM_DECAY_XI = float(xi)
    ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
    brier, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=ds)
    return brier


def holdout_brier(xi):
    wcp.FORM_DECAY_XI = float(xi)
    ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
    brier, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=ds)
    return brier


# --- baseline: current live (power-law) model ---
wcp.USE_EXPONENTIAL_FORM_DECAY = False
base_train, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=wcp.load_backtest_dataset("data", TRAIN_YEARS))
base_holdout, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=wcp.load_backtest_dataset("data", HOLDOUT_YEARS))
print(f"CURRENT (power-law, FORM_MAX_AGE_YEARS={wcp.FORM_MAX_AGE_YEARS} POWER={wcp.FORM_DECAY_POWER}):")
print(f"  train={base_train:.4f}  holdout={base_holdout:.4f}")

# --- untuned guess (borrowed from dixon_coles.py's own default) ---
wcp.USE_EXPONENTIAL_FORM_DECAY = True
guess_train = train_brier(0.0018)
guess_holdout = holdout_brier(0.0018)
print(f"\nEXPONENTIAL untuned (xi=0.0018, borrowed from dixon_coles.py):")
print(f"  train={guess_train:.4f}  holdout={guess_holdout:.4f}")

# --- tune xi on train only, 1-D bounded search + a coarse grid to avoid
#     a bad local optimum (1 parameter, cheap enough to just grid+refine) ---
print("\nGrid search (train only)...")
grid = [0.0001, 0.0003, 0.0006, 0.001, 0.0018, 0.003, 0.005, 0.008, 0.012, 0.018]
best_xi, best_score = None, float("inf")
for xi in grid:
    s = train_brier(xi)
    print(f"  xi={xi:<8} train={s:.4f}")
    if s < best_score:
        best_score, best_xi = s, xi

print(f"\nRefining around xi={best_xi} with bounded Nelder-Mead...")
res = minimize_scalar(train_brier, bounds=(max(BOUNDS[0], best_xi/3), min(BOUNDS[1], best_xi*3)),
                      method="bounded", options={"xatol": 1e-6})
tuned_xi = res.x
tuned_train = res.fun
tuned_holdout = holdout_brier(tuned_xi)

print(f"\nTUNED  xi={tuned_xi:.6f}")
print(f"  train={tuned_train:.4f}  holdout={tuned_holdout:.4f}")
print(f"\n--- Summary ---")
print(f"train:   power-law={base_train:.4f}  exponential(tuned)={tuned_train:.4f}  (delta {tuned_train-base_train:+.4f})")
print(f"holdout: power-law={base_holdout:.4f}  exponential(tuned)={tuned_holdout:.4f}  (delta {tuned_holdout-base_holdout:+.4f})")

# --- paired bootstrap on holdout ---
wcp.USE_EXPONENTIAL_FORM_DECAY = False
ds_holdout_base = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
_, _, base_errs = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=ds_holdout_base, return_errors=True)
base_err_map = {(y, e): v for (y, e, v) in base_errs}

wcp.USE_EXPONENTIAL_FORM_DECAY = True
wcp.FORM_DECAY_XI = tuned_xi
ds_holdout_tuned = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
_, _, tuned_errs = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=ds_holdout_tuned, return_errors=True)
tuned_err_map = {(y, e): v for (y, e, v) in tuned_errs}

common = sorted(set(base_err_map) & set(tuned_err_map))
a = np.array([base_err_map[k] for k in common])
b = np.array([tuned_err_map[k] for k in common])
diffs = a - b
rng = np.random.default_rng(0)
n = len(common)
boot = np.array([diffs[rng.integers(0, n, n)].mean() for _ in range(5000)])
lo, hi = np.percentile(boot, [2.5, 97.5])
print(f"\nbootstrap (power-law - exponential): {diffs.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  significant={(lo>0) or (hi<0)}")
