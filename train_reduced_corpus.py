"""
Reduced 2-component model (prior-form + pairwise H2H) calibrated against
the broader international corpus, as a fair test of whether combining these
two components benefits from the extra data — unlike W_TAC/WEIGHT_STATIC_GD/
WEIGHT_PLAYER_PERF, both of these have inputs that exist for ANY match, not
just World Cup ones, so this is a legitimate use of the expanded corpus
(see the conversation: W_TAC needs team style only tracked per-WC-year,
static_gd/player_perf need WC-specific rank/tournament-progression data).

predicted_a = sigmoid(K_FORM * form_diff + K_H2H * h2h_diff)
  - form_diff: same as-of, no-leakage prior-form differential as
    train_intl_ratings.py (a team's own recency-weighted rating from
    STRICTLY PRIOR matches, never the match being predicted).
  - h2h_diff: pairwise history between THESE TWO SPECIFIC teams, as-of
    strictly before this match, recency+tier weighted — same mechanics as
    wc_predictor's compute_h2h_per_team, just run in a chronological batch
    loop instead of a live single lookup. 0.0 (neutral) if no prior
    meeting exists between this exact pair yet.

Same discipline throughout: as-of only, tier+recency loss weighting
(World Cup matches count 1.3x, friendlies 0.7x, recency decay on top),
train/holdout split by date (before/after 2023-01-01), bootstrap
significance check at the end.
"""
import csv
import math
import os
from collections import defaultdict

import numpy as np
from scipy.optimize import minimize

import train_intl_ratings as base   # reuses load_match_events, build_prior_form_features, years_between, weight_of, sigmoid

DATA_DIR = "data"
HOLDOUT_START_DATE = base.HOLDOUT_START_DATE
H2H_MAX_AGE_YEARS = 5.0   # same window already used for H2H elsewhere in this project


def build_h2h_diff_features(matches):
    """For every match (already sorted chronologically by base.load_match_events),
    compute the pairwise H2H differential as-of strictly before it — the
    recency+tier-weighted win rate between these two specific teams, minus
    0.5, using only meetings strictly before this match's date. 0.0 if no
    prior meeting exists yet for this exact pair."""
    pair_history = defaultdict(list)   # frozenset({a,b}) -> [(date, tier, team_a_won_or_drew_value), ...]
    out = []
    for m in matches:
        a, b = m["team_a"], m["team_b"]
        key = frozenset((a, b))
        history = pair_history[key]

        weighted_outcome_a, weight_total = 0.0, 0.0
        for date, tier, perspective_team, outcome_for_perspective in history:
            age = base.years_between(date, m["date"])
            if age < 0 or age > H2H_MAX_AGE_YEARS:
                continue
            w = base.wcp.recency_weight(age, H2H_MAX_AGE_YEARS, 1.5) * base.wcp.H2H_TIER_WEIGHTS[tier]
            outcome_for_a = outcome_for_perspective if perspective_team == a else (1.0 - outcome_for_perspective)
            weighted_outcome_a += w * outcome_for_a
            weight_total += w
        h2h_diff = (weighted_outcome_a / weight_total - 0.5) if weight_total > 0 else 0.0

        out.append({**m, "h2h_diff": h2h_diff})
        pair_history[key].append((m["date"], m["tier"], a, m["actual"]))
    return out


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def weighted_brier(matches, k_form, k_h2h, cutoff_date):
    total_w, total_err = 0.0, 0.0
    for m in matches:
        w = base.weight_of(m, cutoff_date)
        predicted = sigmoid(k_form * (m["form_a"] - m["form_b"]) + k_h2h * m["h2h_diff"])
        total_err += w * (predicted - m["actual"]) ** 2
        total_w += w
    return total_err / total_w if total_w > 0 else float("nan")


print("Loading matches, building prior-form + pairwise-H2H features (as-of, no leakage)...")
raw_matches = base.load_match_events()
with_priors = base.build_prior_form_features(raw_matches)
with_form = base.evaluable(with_priors)
matches = build_h2h_diff_features(with_form)
print(f"{len(matches)} matches with both form and H2H features")

train = [m for m in matches if m["date"] < HOLDOUT_START_DATE]
holdout = [m for m in matches if m["date"] >= HOLDOUT_START_DATE]
print(f"train: {len(train)}   holdout: {len(holdout)}")

FORM_ONLY_K = 2.2817   # already-validated form-only result, for comparison
form_only_train = weighted_brier(train, FORM_ONLY_K, 0.0, HOLDOUT_START_DATE)
form_only_holdout = weighted_brier(holdout, FORM_ONLY_K, 0.0, HOLDOUT_START_DATE)
print(f"\nForm-only (K_FORM={FORM_ONLY_K}, no H2H): train={form_only_train:.4f}  holdout={form_only_holdout:.4f}")


def objective(x):
    return weighted_brier(train, x[0], x[1], HOLDOUT_START_DATE)


print("\nOptimizing K_FORM + K_H2H jointly (4 restarts)...")
np.random.seed(7)
starts = [np.array([FORM_ONLY_K, 0.0])] + [
    np.array([np.random.uniform(0.5, 3.0), np.random.uniform(-1.0, 1.0)]) for _ in range(3)
]
best = None
for i, x0 in enumerate(starts):
    r = minimize(objective, x0, method="Nelder-Mead", bounds=[(0.0, 5.0), (-3.0, 3.0)],
                 options={"xatol": 1e-5, "fatol": 1e-8, "maxiter": 500})
    ho = weighted_brier(holdout, r.x[0], r.x[1], HOLDOUT_START_DATE)
    print(f"  start {i}: K_FORM={r.x[0]:.4f} K_H2H={r.x[1]:.4f}  train={r.fun:.4f}  holdout={ho:.4f}")
    if best is None or r.fun < best.fun:
        best = r

k_form_fit, k_h2h_fit = best.x
opt_train = weighted_brier(train, k_form_fit, k_h2h_fit, HOLDOUT_START_DATE)
opt_holdout = weighted_brier(holdout, k_form_fit, k_h2h_fit, HOLDOUT_START_DATE)
print(f"\nBEST  K_FORM={k_form_fit:.4f}  K_H2H={k_h2h_fit:.4f}")
print(f"  train={opt_train:.4f}  holdout={opt_holdout:.4f}")

print(f"\n--- Summary ---")
print(f"{'Model':<28}{'Train':>8}{'Holdout':>8}")
print(f"{'Form only':<28}{form_only_train:>8.4f}{form_only_holdout:>8.4f}")
print(f"{'Form + H2H':<28}{opt_train:>8.4f}{opt_holdout:>8.4f}")

# --- paired bootstrap on holdout: form-only vs form+H2H ---
diffs = []
for m in holdout:
    w = base.weight_of(m, HOLDOUT_START_DATE)
    p_form = sigmoid(FORM_ONLY_K * (m["form_a"] - m["form_b"]))
    p_both = sigmoid(k_form_fit * (m["form_a"] - m["form_b"]) + k_h2h_fit * m["h2h_diff"])
    err_form = w * (p_form - m["actual"]) ** 2
    err_both = w * (p_both - m["actual"]) ** 2
    diffs.append(err_form - err_both)
diffs = np.array(diffs)
rng = np.random.default_rng(0)
n = len(diffs)
boot = np.array([diffs[rng.integers(0, n, n)].mean() for _ in range(5000)])
lo, hi = np.percentile(boot, [2.5, 97.5])
print(f"\nholdout bootstrap (form-only err - form+H2H err): {diffs.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  significant={(lo>0) or (hi<0)}")
