"""
Properly tune FORM_MAX_AGE_YEARS and FORM_DECAY_POWER (intl_form's recency
window shape) jointly with K_FORM, against the full international corpus
(1,882 evaluable matches) — these were previously just reasonable guesses
(2.0, 1.0), never actually validated the way K_FORM itself was.

Same as-of discipline as train_intl_ratings.py (a team's rating from a
match can never be used to predict that same match), same train/holdout
split by date (before/after 2023-01-01), same competition-tier + recency
loss weighting. The difference: FORM_MAX_AGE_YEARS/FORM_DECAY_POWER change
what "prior form" even means for a team at a given match, so — unlike
K_FORM alone — the per-match form features have to be recomputed fresh for
every candidate (x[1], x[2]), not just cached once upfront.
"""
import math
import numpy as np
from scipy.optimize import minimize

import train_intl_ratings as base   # reuses load_match_events, build_prior_form_features, etc.

HOLDOUT_START_DATE = base.HOLDOUT_START_DATE
MAX_AGE_YEARS = base.MAX_AGE_YEARS
DECAY_POWER = base.DECAY_POWER


def form_rating(prior_games, as_of_date, form_max_age, form_decay_power):
    if not prior_games:
        return None
    weighted_sum, weight_total = 0.0, 0.0
    for date, rating in prior_games:
        age = base.years_between(date, as_of_date)
        if age < 0:
            continue
        w = base.wcp.recency_weight(age, form_max_age, form_decay_power)
        weighted_sum += w * rating
        weight_total += w
    return weighted_sum / weight_total if weight_total > 0 else None


def evaluable(with_priors, form_max_age, form_decay_power):
    out = []
    for m in with_priors:
        fa = form_rating(m["prior_a"], m["date"], form_max_age, form_decay_power)
        fb = form_rating(m["prior_b"], m["date"], form_max_age, form_decay_power)
        if fa is None or fb is None:
            continue
        out.append({**m, "form_a": fa, "form_b": fb})
    return out


def weighted_brier(matches, k_form, cutoff_date):
    total_w, total_err = 0.0, 0.0
    for m in matches:
        w = base.weight_of(m, cutoff_date)
        predicted = base.sigmoid(k_form * (m["form_a"] - m["form_b"]))
        total_err += w * (predicted - m["actual"]) ** 2
        total_w += w
    return total_err / total_w if total_w > 0 else float("nan")


print("Loading raw match history (independent of form window)...")
raw_matches = base.load_match_events()
with_priors = base.build_prior_form_features(raw_matches)
print(f"{len(raw_matches)} total matches with ratings + outcomes")


def split(matches):
    train = [m for m in matches if m["date"] < HOLDOUT_START_DATE]
    holdout = [m for m in matches if m["date"] >= HOLDOUT_START_DATE]
    return train, holdout


def objective(x):
    k_form, form_max_age, form_decay_power = x
    form_max_age = max(form_max_age, 0.1)
    matches = evaluable(with_priors, form_max_age, form_decay_power)
    train, _ = split(matches)
    return weighted_brier(train, k_form, HOLDOUT_START_DATE)


# --- baseline: current guessed values (2.0, 1.0), K_FORM re-fit alone (already done) ---
CURRENT_K_FORM, CURRENT_MAX_AGE, CURRENT_DECAY = 2.2817, 2.0, 1.0
base_matches = evaluable(with_priors, CURRENT_MAX_AGE, CURRENT_DECAY)
base_train, base_holdout = split(base_matches)
b_train = weighted_brier(base_train, CURRENT_K_FORM, HOLDOUT_START_DATE)
b_holdout = weighted_brier(base_holdout, CURRENT_K_FORM, HOLDOUT_START_DATE)
print(f"\nCURRENT (K_FORM={CURRENT_K_FORM}, MAX_AGE={CURRENT_MAX_AGE}, DECAY={CURRENT_DECAY}):")
print(f"  train={b_train:.4f}  holdout={b_holdout:.4f}  n_train={len(base_train)} n_holdout={len(base_holdout)}")

BOUNDS = [(0.0, 4.0), (0.3, 8.0), (0.2, 4.0)]

print("\nOptimizing K_FORM + FORM_MAX_AGE_YEARS + FORM_DECAY_POWER jointly (4 restarts)...")
np.random.seed(4)
starts = [np.array([CURRENT_K_FORM, CURRENT_MAX_AGE, CURRENT_DECAY])] + [
    np.array([np.random.uniform(0.2, 3.0), np.random.uniform(0.5, 6.0), np.random.uniform(0.3, 3.0)])
    for _ in range(3)
]

best = None
for i, x0 in enumerate(starts):
    r = minimize(objective, x0, method="Nelder-Mead", bounds=BOUNDS,
                 options={"xatol": 1e-4, "fatol": 1e-7, "maxiter": 800})
    k, ma, dp = r.x
    ma = max(ma, 0.1)
    matches = evaluable(with_priors, ma, dp)
    tr, ho = split(matches)
    ho_score = weighted_brier(ho, k, HOLDOUT_START_DATE)
    print(f"  start {i}: K_FORM={k:.3f} MAX_AGE={ma:.3f} DECAY={dp:.3f}  train={r.fun:.4f}  holdout={ho_score:.4f}")
    if best is None or r.fun < best[0]:
        best = (r.fun, r.x, ho_score)

_, best_x, best_holdout = best
k_fit, ma_fit, dp_fit = best_x
ma_fit = max(ma_fit, 0.1)
print(f"\nBEST: K_FORM={k_fit:.4f}  FORM_MAX_AGE_YEARS={ma_fit:.4f}  FORM_DECAY_POWER={dp_fit:.4f}")
print(f"  train={best[0]:.4f}  holdout={best_holdout:.4f}")

print(f"\n--- Summary ---")
print(f"train:   current={b_train:.4f}  tuned={best[0]:.4f}  (delta {best[0]-b_train:+.4f})")
print(f"holdout: current={b_holdout:.4f}  tuned={best_holdout:.4f}  (delta {best_holdout-b_holdout:+.4f})")
