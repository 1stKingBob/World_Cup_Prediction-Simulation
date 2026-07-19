"""
Tune ELO_SEED_K: the fixed per-match step size for the pre-tournament
Elo-style relative_gd seed (built from the full international match corpus,
see _compute_elo_seed), against the always-0.0 baseline.

ELO_SEED_K affects historical_score-like data computed once at dataset-load
time (inside load_teams_from_csv, via _compute_elo_seed), NOT read live per
prediction — so base_teams must be rebuilt fresh for each candidate value,
same reason HIST_DECAY_MAX_YEARS needed this treatment earlier. The h2h/
match/rating CSV parts are unaffected and cached.
"""
import importlib.util
import numpy as np
from scipy.optimize import minimize_scalar

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]

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
    ds = {}
    for y in years:
        ds[y] = {"base_teams": wcp.load_teams_from_csv("data", y), **static_cache[y]}
    return ds


def brier_on(years):
    ds = build_dataset(years)
    score, n = wcp.evaluate_brier("data", years, dataset=ds)
    return score, n


# --- Baseline: no seed ---
wcp.USE_ELO_SEED = False
base_train, ntr = brier_on(TRAIN_YEARS)
base_holdout, nho = brier_on(HOLDOUT_YEARS)
print(f"\nBASELINE (no seed): train={base_train:.4f} ({ntr})  holdout={base_holdout:.4f} ({nho})")

# --- Grid scan across ELO_SEED_K ---
wcp.USE_ELO_SEED = True
print("\nGrid scan over ELO_SEED_K:")
results = []
for k in [0.02, 0.05, 0.08, 0.12, 0.15, 0.20, 0.30, 0.45, 0.65]:
    wcp.ELO_SEED_K = k
    train_ds = build_dataset(TRAIN_YEARS)
    cv_scores = []
    for y in TRAIN_YEARS:
        s, _ = wcp.evaluate_brier("data", [y], dataset=build_dataset([y]))
        cv_scores.append(s)
    train_score, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=train_ds)
    holdout_score, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=build_dataset(HOLDOUT_YEARS))
    results.append((k, train_score, np.mean(cv_scores), np.std(cv_scores), holdout_score))
    print(f"  K={k:.2f}  train={train_score:.4f}  cv_mean={np.mean(cv_scores):.4f}  cv_std={np.std(cv_scores):.4f}  holdout={holdout_score:.4f}")

best_train = min(results, key=lambda r: r[1])
best_holdout = min(results, key=lambda r: r[4])
print(f"\nBest on train: K={best_train[0]:.2f}  train={best_train[1]:.4f}  holdout={best_train[4]:.4f}")
print(f"Best on holdout: K={best_holdout[0]:.2f}  train={best_holdout[1]:.4f}  holdout={best_holdout[4]:.4f}")
