"""
Calibrate a player-form predictor against the full international match
corpus (data/intl_player_ratings.csv, 2,053 matches, 2002-2026 — not just
World Cups), rather than the ~500-match World-Cup-only backtest everything
else in this project uses.

CRITICAL: a team's rating FROM a match cannot be used to predict THAT match
— SofaScore's player "rating" is a post-hoc grade for how well they played
in that exact game, so using it to "predict" the same game's outcome is
circular (an early version of this script did exactly that and got an
impossible Brier score of ~0.065 as a result — a bug, not a finding, caught
before being reported). Every team's predictive feature here is a
recency-weighted average of its OWN rating from STRICTLY PRIOR matches only
— the same as-of discipline (never see the outcome being predicted) used
everywhere else in this project.

Each match's contribution to the loss is WEIGHTED by:
  - competition tier (world_cup > other competitive > friendly), reusing
    the existing H2H_TIER_WEIGHTS/classify_h2h_tier from wc_predictor.
  - recency (years before the train/holdout cutoff), reusing the existing
    recency_weight() shape.

Train/holdout split is by DATE: matches before 2023 train, 2023-2026 hold
out — mirrors the discipline used everywhere else in this project.
"""
import csv
import math
import os
from collections import defaultdict

import numpy as np
from scipy.optimize import minimize

import importlib.util
spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

DATA_DIR = "data"
HOLDOUT_START_DATE = "2023-01-01"
MAX_AGE_YEARS = 10          # loss-weighting recency window (older matches count less toward the objective)
DECAY_POWER = 1.5
FORM_MAX_AGE_YEARS = 2.0    # separate, shorter window for the PREDICTIVE feature itself —
                            # a player's rating from 2 years ago says much less about
                            # current form than one from last month
FORM_DECAY_POWER = 1.0


def load_match_events():
    """One event per (event_id, team): minutes-weighted average rating for
    that team in that match, plus date/competition/opponent/actual outcome
    (joined from h2h_matches.csv)."""
    rating_sum = defaultdict(float)
    minutes_sum = defaultdict(float)
    meta = {}
    with open(os.path.join(DATA_DIR, "intl_player_ratings.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["event_id"], row["team"])
            minutes = float(row["minutes_played"] or 0)
            if minutes <= 0:
                continue
            rating_sum[key] += float(row["rating"]) * minutes
            minutes_sum[key] += minutes
            meta[row["event_id"]] = {
                "date": row["date"], "competition": row["competition"],
                "is_friendly": row["is_friendly"] == "1",
            }
    avg_rating = {key: rating_sum[key] / minutes_sum[key] for key in rating_sum}

    outcomes = {}
    seen = set()
    with open(os.path.join(DATA_DIR, "h2h_matches.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            eid = row["event_id"]
            if eid in seen:
                continue
            seen.add(eid)
            outcomes[eid] = {"team": row["team"], "opponent": row["opponent"], "gd": int(row["gd"])}

    matches = []
    for eid, m in meta.items():
        if eid not in outcomes:
            continue
        team, opp, gd = outcomes[eid]["team"], outcomes[eid]["opponent"], outcomes[eid]["gd"]
        key_a, key_b = (eid, team), (eid, opp)
        if key_a not in avg_rating or key_b not in avg_rating:
            continue
        actual = 1.0 if gd > 0 else (0.5 if gd == 0 else 0.0)
        tier = wcp.classify_h2h_tier(m["competition"], m["is_friendly"])
        matches.append({
            "event_id": eid, "date": m["date"], "tier": tier,
            "team_a": team, "team_b": opp,
            "own_rating_a": avg_rating[key_a], "own_rating_b": avg_rating[key_b],
            "actual": actual,
        })
    matches.sort(key=lambda m: m["date"])
    return matches


def years_between(earlier, later):
    return (int(later[:4]) * 365.25 + int(later[5:7]) * 30.44
            - int(earlier[:4]) * 365.25 - int(earlier[5:7]) * 30.44) / 365.25


def build_prior_form_features(matches):
    """For every match, each team's predictive feature is a recency-weighted
    average of ITS OWN rating from matches strictly before this one — never
    including this match's own rating. Teams with no prior history yet get
    None (excluded from that match's evaluation, same as any as-of cutoff)."""
    history = defaultdict(list)   # team -> [(date, own_rating), ...] strictly in the past
    out = []
    for m in matches:
        prior_a = history[m["team_a"]]
        prior_b = history[m["team_b"]]
        out.append({**m, "prior_a": list(prior_a), "prior_b": list(prior_b)})
        history[m["team_a"]].append((m["date"], m["own_rating_a"]))
        history[m["team_b"]].append((m["date"], m["own_rating_b"]))
    return out


def form_rating(prior_games, as_of_date):
    if not prior_games:
        return None
    weighted_sum, weight_total = 0.0, 0.0
    for date, rating in prior_games:
        age = years_between(date, as_of_date)
        if age < 0:
            continue
        w = wcp.recency_weight(age, FORM_MAX_AGE_YEARS, FORM_DECAY_POWER)
        weighted_sum += w * rating
        weight_total += w
    return weighted_sum / weight_total if weight_total > 0 else None


def weight_of(m, cutoff_date):
    age = max(years_between(m["date"], cutoff_date), 0.0)
    return wcp.recency_weight(age, MAX_AGE_YEARS, DECAY_POWER) * wcp.H2H_TIER_WEIGHTS[m["tier"]]


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def evaluable(matches):
    """Only matches where BOTH teams have at least one prior real result to
    form a genuine as-of prediction from."""
    out = []
    for m in matches:
        fa = form_rating(m["prior_a"], m["date"])
        fb = form_rating(m["prior_b"], m["date"])
        if fa is None or fb is None:
            continue
        out.append({**m, "form_a": fa, "form_b": fb})
    return out


def weighted_brier(matches, k_form, cutoff_date):
    total_w, total_err = 0.0, 0.0
    for m in matches:
        w = weight_of(m, cutoff_date)
        predicted = sigmoid(k_form * (m["form_a"] - m["form_b"]))
        total_err += w * (predicted - m["actual"]) ** 2
        total_w += w
    return total_err / total_w if total_w > 0 else float("nan")


def main():
    print("Loading matches and building prior-form features (as-of, no leakage)...")
    raw_matches = load_match_events()
    with_priors = build_prior_form_features(raw_matches)
    matches = evaluable(with_priors)
    print(f"{len(raw_matches)} total matches, {len(matches)} have prior history for both teams")

    train = [m for m in matches if m["date"] < HOLDOUT_START_DATE]
    holdout = [m for m in matches if m["date"] >= HOLDOUT_START_DATE]
    print(f"train (before {HOLDOUT_START_DATE}): {len(train)}   holdout: {len(holdout)}")

    base_train = weighted_brier(train, 0.0, HOLDOUT_START_DATE)
    base_holdout = weighted_brier(holdout, 0.0, HOLDOUT_START_DATE)
    print(f"\nBaseline (K_FORM=0, i.e. predicts 0.5 always): train={base_train:.4f}  holdout={base_holdout:.4f}")

    def objective(x):
        return weighted_brier(train, x[0], HOLDOUT_START_DATE)

    print("\nOptimizing K_FORM (Nelder-Mead, weighted train Brier only, bounded)...")
    result = minimize(objective, x0=np.array([0.3]), method="Nelder-Mead",
                       bounds=[(0.0, 3.0)], options={"xatol": 1e-5, "fatol": 1e-8, "maxiter": 300})
    k_fit = float(result.x[0])
    opt_train = weighted_brier(train, k_fit, HOLDOUT_START_DATE)
    opt_holdout = weighted_brier(holdout, k_fit, HOLDOUT_START_DATE)

    print(f"\nFIT  K_FORM={k_fit:.4f}")
    print(f"  train={opt_train:.4f}  holdout={opt_holdout:.4f}")

    print(f"\n--- Summary ---")
    print(f"{'Model':<28}{'Train':>8}{'Holdout':>8}")
    print(f"{'No signal (K=0)':<28}{base_train:>8.4f}{base_holdout:>8.4f}")
    print(f"{'Prior-form differential':<28}{opt_train:>8.4f}{opt_holdout:>8.4f}")


if __name__ == "__main__":
    main()
