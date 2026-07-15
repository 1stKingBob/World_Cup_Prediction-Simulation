"""
Third optimization group: K_REL, K_FORM, RGD_PRIOR_GAMES — the relative_gd
(Context(A,B) opponent-form) formula's own internal constants. Never swept
before; K_FORM alone was tested manually earlier (flat/noise-level effect on
holdout, mild overfitting signature at the high end) but K_REL and
RGD_PRIOR_GAMES were both set by intuition and never touched.

Unlike HIST_DECAY_MAX_YEARS/POWER, these ARE safe to tune against a cached
dataset: relative_gd is recomputed fresh inside build_teams_asof() for every
single as-of prediction (not baked into base_teams at load time), and that
function reads K_REL/K_FORM/RGD_PRIOR_GAMES as live globals — so mutating
them between evaluate_brier() calls takes effect immediately, same as the
first (gap-weight) optimization group.
"""
import importlib.util
import numpy as np
from scipy.optimize import minimize

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]

DEFAULT_K_REL = wcp.K_REL
DEFAULT_K_FORM = wcp.K_FORM
DEFAULT_RGD_PRIOR_GAMES = wcp.RGD_PRIOR_GAMES

print("Loading datasets...")
train_ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
holdout_ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
fold_ds = {y: wcp.load_backtest_dataset("data", [y]) for y in TRAIN_YEARS}

BOUNDS = [(0.05, 1.5), (0.0, 2.0), (0.0, 8.0)]


def apply_params(x):
    wcp.K_REL = float(np.clip(x[0], *BOUNDS[0]))
    wcp.K_FORM = float(np.clip(x[1], *BOUNDS[1]))
    wcp.RGD_PRIOR_GAMES = float(np.clip(x[2], *BOUNDS[2]))


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


x0 = np.array([DEFAULT_K_REL, DEFAULT_K_FORM, DEFAULT_RGD_PRIOR_GAMES])

base_train = train_brier(x0)
base_cv = cv_briers(x0)
base_holdout = holdout_brier(x0)
print(f"\nBASELINE  K_REL={x0[0]:.3f} K_FORM={x0[1]:.3f} RGD_PRIOR_GAMES={x0[2]:.3f}")
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

print(f"\nOPTIMIZED  K_REL={opt_x[0]:.3f} K_FORM={opt_x[1]:.3f} RGD_PRIOR_GAMES={opt_x[2]:.3f}")
print(f"  train={opt_train:.4f}  cv_mean={np.mean(opt_cv):.4f}  cv_std={np.std(opt_cv):.4f}  holdout={opt_holdout:.4f}")
print(f"  cv per-year: " + " ".join(f"{y}:{s:.4f}" for y, s in zip(TRAIN_YEARS, opt_cv)))

print("\n--- Random-restart robustness check ---")
np.random.seed(7)
for trial in range(4):
    rx0 = np.array([
        np.random.uniform(*BOUNDS[0]),
        np.random.uniform(*BOUNDS[1]),
        np.random.uniform(*BOUNDS[2]),
    ])
    r = minimize(train_brier, rx0, method="Nelder-Mead", bounds=BOUNDS,
                 options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 500})
    apply_params(r.x)
    ho = holdout_brier(r.x)
    print(f"  trial {trial}: K_REL={r.x[0]:.3f} K_FORM={r.x[1]:.3f} RGD_PRIOR_GAMES={r.x[2]:.3f}  "
          f"train={r.fun:.4f} holdout={ho:.4f}")

print(f"\n--- Summary ---")
print(f"train:   {base_train:.4f} -> {opt_train:.4f}  (delta {opt_train-base_train:+.4f})")
print(f"cv_mean: {np.mean(base_cv):.4f} -> {np.mean(opt_cv):.4f}  (delta {np.mean(opt_cv)-np.mean(base_cv):+.4f})")
print(f"holdout: {base_holdout:.4f} -> {opt_holdout:.4f}  (delta {opt_holdout-base_holdout:+.4f})")
