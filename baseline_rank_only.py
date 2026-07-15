"""
Baseline #2: FIFA-ranking-only prediction. Uses ONLY each team's adjusted
rank (raw_rank * confederation coefficient) — no static GD anchors, no
player ratings, no historical WC performance, no H2H, no relative_gd, no
tactical matchup. The question this answers: does everything else in the
full model actually earn its keep over a signal that's already public and
free?

Same train/holdout split and same real matches as the full model's
backtest, so the comparison is apples-to-apples — only the model differs.
Rank doesn't change within a tournament in this dataset (each team's
raw_rank/confederation is fixed per tournament-year in teams.csv), so this
baseline needs no as-of/cutoff machinery at all: it's a genuinely static,
pre-tournament-only prediction, which is exactly the right spirit for a
naive baseline (it should NOT see any real in-tournament results).

gap = ln(rank_b / rank_a): positive when team A is better-ranked (lower
rank number). Log-ratio, not a raw difference, matching the same
compression pattern used everywhere else in this project (K_REL) — a
5-vs-1 rank gap should matter more than a 104-vs-100 one, even though both
are "4 positions apart."
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


def adjusted_rank(team_data):
    return team_data["raw_rank"] * wcp.CONF_COEFFICIENTS[team_data["confederation"]]


def rank_only_errors(years, dataset, k_baseline):
    """Mirrors evaluate_brier's match iteration exactly (same dedup, same
    actual-outcome convention) but scores with the rank-only sigmoid instead
    of the full model."""
    errors = []
    for year in years:
        base_teams = dataset[year]["base_teams"]
        match_rows = dataset[year]["match_rows"]
        seen_events = set()
        for r in match_rows:
            if r["gd"] == "":
                continue
            eid = r["event_id"]
            if eid in seen_events:
                continue
            seen_events.add(eid)

            team_a, team_b = r["team"], r["opponent"]
            if team_a not in base_teams or team_b not in base_teams:
                continue
            gd = int(r["gd"])
            actual = 1.0 if gd > 0 else (0.0 if gd < 0 else 0.5)

            rank_a = adjusted_rank(base_teams[team_a])
            rank_b = adjusted_rank(base_teams[team_b])
            gap = math.log(rank_b / rank_a) if rank_a > 0 and rank_b > 0 else 0.0
            predicted = 1.0 / (1.0 + math.exp(-k_baseline * gap))

            errors.append((predicted - actual) ** 2)
    return np.array(errors)


print("Loading datasets...")
train_ds = wcp.load_backtest_dataset("data", TRAIN_YEARS)
holdout_ds = wcp.load_backtest_dataset("data", HOLDOUT_YEARS)
fold_ds = {y: wcp.load_backtest_dataset("data", [y]) for y in TRAIN_YEARS}


def train_brier(x):
    return rank_only_errors(TRAIN_YEARS, train_ds, x[0]).mean()


print("\nFitting K_BASELINE (Nelder-Mead, train Brier only, bounded)...")
result = minimize(train_brier, x0=np.array([0.5]), method="Nelder-Mead",
                   bounds=[(0.05, 5.0)], options={"xatol": 1e-5, "fatol": 1e-8, "maxiter": 200})
k_fit = float(result.x[0])
print(f"  K_BASELINE fit to: {k_fit:.4f}")

train_errors = rank_only_errors(TRAIN_YEARS, train_ds, k_fit)
holdout_errors = rank_only_errors(HOLDOUT_YEARS, holdout_ds, k_fit)
cv_scores = [rank_only_errors([y], fold_ds[y], k_fit).mean() for y in TRAIN_YEARS]

print(f"\n=== Baseline #2: FIFA-ranking-only (K_BASELINE={k_fit:.4f}) ===")
print(f"  train   ({len(train_errors)}): {train_errors.mean():.4f}")
print(f"  cv_mean: {np.mean(cv_scores):.4f}  cv_std: {np.std(cv_scores):.4f}")
print(f"  holdout ({len(holdout_errors)}): {holdout_errors.mean():.4f}")
print(f"  cv per-year: " + " ".join(f"{y}:{s:.4f}" for y, s in zip(TRAIN_YEARS, cv_scores)))

# --- Full model, for direct comparison (current adopted defaults) ---
full_train, _ = wcp.evaluate_brier("data", TRAIN_YEARS, dataset=train_ds)
full_holdout, _ = wcp.evaluate_brier("data", HOLDOUT_YEARS, dataset=holdout_ds)

print(f"\n=== Comparison table ===")
print(f"  {'Model':<28} {'Train':>8} {'Holdout':>8}")
print(f"  {'-'*28} {'-'*8} {'-'*8}")
print(f"  {'Coin flip (no info)':<28} {0.2500:>8.4f} {0.2500:>8.4f}")
print(f"  {'FIFA rank only':<28} {train_errors.mean():>8.4f} {holdout_errors.mean():>8.4f}")
print(f"  {'Full model':<28} {full_train:>8.4f} {full_holdout:>8.4f}")
