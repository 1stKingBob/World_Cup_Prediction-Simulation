"""
Second optimization group (see optimize_gap_weights.py for the first):
  1. WEIGHT_STATIC_GD / WEIGHT_PLAYER_PERF  (current-tournament split, sum to 1)
  2. HIST_WEIGHTS / CURR_WEIGHTS            (historical-vs-current-tournament
                                              curve, indexed by games played
                                              this tournament) — parametrized
                                              as floor + (1-floor)*(1-i/7)^power
                                              instead of 8 raw numbers, to keep
                                              the free-parameter count sane
  3. HIST_DECAY_MAX_YEARS / HIST_DECAY_POWER (recency decay across a team's
                                              last 3 World Cups)
That's 5 real degrees of freedom total.

IMPORTANT: unlike the gap-combination weights, HIST_DECAY_MAX_YEARS/POWER
feed into historical_score, which is computed ONCE per team at dataset-load
time (_compute_historical_scores, called from load_teams_from_csv) and then
cached on the team dict — NOT read live per-prediction. So base_teams must be
rebuilt fresh on every objective evaluation for these two params to have any
effect; the h2h/match/rating CSVs are cached since they're untouched by this
group.

Known risk flagged going in: the HIST_WEIGHTS/CURR_WEIGHTS curve specifically
was already grid-searched earlier this project on a much thinner setup (WC
2026 group-stage only) and the "best on train" curve made holdout WORSE
(0.1487 -> 0.1504) — a real overfitting result, not a hypothetical one. This
run repeats that test with the proper train/CV/holdout discipline the gap-
weight optimization used, on the full 2002-2018 training set, to see if it
holds up under more data and more rigor.
"""
import importlib.util
import time
import numpy as np
from scipy.optimize import minimize

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]

DEFAULT_WEIGHT_STATIC_GD = wcp.WEIGHT_STATIC_GD
DEFAULT_HIST_DECAY_MAX_YEARS = wcp.HIST_DECAY_MAX_YEARS
DEFAULT_HIST_DECAY_POWER = wcp.HIST_DECAY_POWER

# Cache the parts of the dataset NOT affected by this parameter group.
print("Caching static dataset parts (h2h/match/rating rows)...")
static_cache = {}
for y in TRAIN_YEARS + HOLDOUT_YEARS:
    h2h_matches = wcp.load_h2h_matches_csv("data")
    h2h_index = {}
    for row in h2h_matches:
        h2h_index.setdefault((row["team"], row["opponent"]), []).append(row)
    static_cache[y] = {
        "h2h_matches": h2h_matches,
        "h2h_index": h2h_index,
        "match_rows": wcp.read_matches_csv("data", y),
        "rating_rows": wcp.read_ratings_csv("data", y),
    }


def build_dataset(years):
    """Rebuild base_teams fresh (respecting current global constants) for
    the given years, reusing the cached static parts."""
    ds = {}
    for y in years:
        ds[y] = {
            "base_teams": wcp.load_teams_from_csv("data", y),
            **static_cache[y],
        }
    return ds


def apply_params(x):
    static_gd_w = float(np.clip(x[0], 0.05, 0.95))
    floor = float(np.clip(x[1], 0.05, 0.6))
    power = float(np.clip(x[2], 0.2, 4.0))
    max_years = float(np.clip(x[3], 4.0, 24.0))
    decay_power = float(np.clip(x[4], 0.3, 4.0))

    wcp.WEIGHT_STATIC_GD = static_gd_w
    wcp.WEIGHT_PLAYER_PERF = 1.0 - static_gd_w

    hist_curve = [floor + (1.0 - floor) * (1.0 - i / 7.0) ** power for i in range(8)]
    wcp.HIST_WEIGHTS = hist_curve
    wcp.CURR_WEIGHTS = [1.0 - h for h in hist_curve]

    wcp.HIST_DECAY_MAX_YEARS = max_years
    wcp.HIST_DECAY_POWER = decay_power


def brier_on(x, years):
    apply_params(x)
    ds = build_dataset(years)
    score, _ = wcp.evaluate_brier("data", years, dataset=ds)
    return score


def train_obj(x):
    return brier_on(x, TRAIN_YEARS)


def cv_briers(x):
    apply_params(x)
    scores = []
    for y in TRAIN_YEARS:
        ds = build_dataset([y])
        s, _ = wcp.evaluate_brier("data", [y], dataset=ds)
        scores.append(s)
    return scores


def holdout_obj(x):
    return brier_on(x, HOLDOUT_YEARS)


x0 = np.array([
    DEFAULT_WEIGHT_STATIC_GD,   # 0.45
    0.15,                       # floor (approx current curve's tail value)
    0.64,                       # power (approx fit to current curve shape)
    DEFAULT_HIST_DECAY_MAX_YEARS,  # 16
    DEFAULT_HIST_DECAY_POWER,      # 1.5
])

print("\nBASELINE (current hand-tuned defaults)")
t0 = time.time()
base_train = train_obj(x0)
base_cv = cv_briers(x0)
base_holdout = holdout_obj(x0)
print(f"  WEIGHT_STATIC_GD={x0[0]:.3f}  hist_curve(floor={x0[1]:.3f}, power={x0[2]:.3f})  "
      f"HIST_DECAY_MAX_YEARS={x0[3]:.2f}  HIST_DECAY_POWER={x0[4]:.3f}")
print(f"  train={base_train:.4f}  cv_mean={np.mean(base_cv):.4f}  cv_std={np.std(base_cv):.4f}  holdout={base_holdout:.4f}")
print(f"  cv per-year: " + " ".join(f"{y}:{s:.4f}" for y, s in zip(TRAIN_YEARS, base_cv)))
print(f"  (baseline eval took {time.time()-t0:.1f}s)")

print("\nOptimizing (Nelder-Mead, train Brier only, bounded)...")
t0 = time.time()
bounds = [(0.05, 0.95), (0.05, 0.6), (0.2, 4.0), (4.0, 24.0), (0.3, 4.0)]
result = minimize(train_obj, x0, method="Nelder-Mead", bounds=bounds,
                   options={"xatol": 1e-3, "fatol": 1e-6, "maxiter": 300})
print(f"  (optimization took {time.time()-t0:.1f}s, {result.nit} iterations)")

opt_x = result.x
apply_params(opt_x)
opt_train = train_obj(opt_x)
opt_cv = cv_briers(opt_x)
opt_holdout = holdout_obj(opt_x)

print(f"\nOPTIMIZED  WEIGHT_STATIC_GD={opt_x[0]:.3f}  "
      f"hist_curve(floor={opt_x[1]:.3f}, power={opt_x[2]:.3f})  "
      f"HIST_DECAY_MAX_YEARS={opt_x[3]:.2f}  HIST_DECAY_POWER={opt_x[4]:.3f}")
print(f"  train={opt_train:.4f}  cv_mean={np.mean(opt_cv):.4f}  cv_std={np.std(opt_cv):.4f}  holdout={opt_holdout:.4f}")
print(f"  cv per-year: " + " ".join(f"{y}:{s:.4f}" for y, s in zip(TRAIN_YEARS, opt_cv)))
print(f"  resulting HIST_WEIGHTS: {[round(h,3) for h in wcp.HIST_WEIGHTS]}")

print(f"\n--- Summary ---")
print(f"train:   {base_train:.4f} -> {opt_train:.4f}  (delta {opt_train-base_train:+.4f})")
print(f"cv_mean: {np.mean(base_cv):.4f} -> {np.mean(opt_cv):.4f}  (delta {np.mean(opt_cv)-np.mean(base_cv):+.4f})")
print(f"holdout: {base_holdout:.4f} -> {opt_holdout:.4f}  (delta {opt_holdout-base_holdout:+.4f})")
