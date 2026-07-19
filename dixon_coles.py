"""
Dixon-Coles Poisson goal-scoring model — an alternative prediction engine to
the hand-weighted logit model in wc_predictor (1).py, exposed as a toggle in
the frontend rather than a replacement.

Unlike the main model (a single win-probability logit built from weighted
feature gaps), this predicts each team's own goal-scoring rate as a Poisson
process, derived from real goal-difference data across ~5,000 real
international matches (data/h2h_matches.csv, 1998-2026, real calendar
dates) — the same corpus already used for intl_form, just consumed
differently: instead of a recency-weighted average "how good is this team,"
it fits an ATTACK strength and a DEFENSE weakness per team via maximum
likelihood, so a team's rating is specifically "how many goals do you
score/concede against an average opponent," not a single scalar.

Model (Dixon & Coles, 1997):
    lambda_A = exp(attack_A + defense_B)   # A's expected goals vs B
    lambda_B = exp(attack_B + defense_A)
    P(A scores x, B scores y) = Poisson(x; lambda_A) * Poisson(y; lambda_B)
                                 * tau(x, y, lambda_A, lambda_B, rho)
tau is a small correlation correction for low-scoring outcomes (0-0, 1-0,
0-1, 1-1) — without it, independent Poisson draws systematically
underestimate how often real matches end 0-0 or 1-1.

No home-advantage term: almost every World Cup match is played at a neutral
venue (host-nation games are the exception, and rare enough not to warrant
the extra parameter here).

Fit via weighted maximum likelihood (L-BFGS-B — this is a ~100-200
parameter problem, one attack + one defense per team, far beyond what
Nelder-Mead-style derivative-free search handles well), with exponential
time-decay weighting by real calendar days (not the WC-only "games ago"
ordinal proxy used elsewhere in this codebase, since this corpus has real
dates) — the same "older data should count for less" philosophy as
everywhere else in this project, just measured precisely instead of
approximately.
"""
import csv
import math
import os
from datetime import date, datetime

import numpy as np
from scipy.optimize import minimize

DEFAULT_XI = 0.0003   # per-day exponential decay. Swept 0-0.005 in
                       # backtest_dixon_coles.py against the same WC
                       # train/holdout years and Brier convention used
                       # throughout this project: holdout Brier is flat
                       # (~0.144, noise-level differences) across
                       # 0.0002-0.0005, and WORSE at faster decay (0.0018
                       # literature default: 0.149; 0.005: 0.163) -- this
                       # model needs more history than the main model to
                       # get stable per-team attack/defense estimates, so
                       # aggressive forgetting hurts rather than helps.
                       # holdout=0.1439 here vs the live custom model's
                       # 0.1473 and the rank-only baseline's 0.1453 -- a
                       # genuinely competitive alternative, not just a
                       # working toy.
MAX_GOALS = 10         # truncation for the scoreline summation — Poisson
                       # mass beyond 10 goals is negligible (<1e-6 for any
                       # realistic international-match lambda).


def _parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def load_international_matches(data_dir):
    """One row per REAL match (deduped from h2h_matches.csv's two-rows-per-
    match, team-perspective format) with a real calendar date. Returns
    list of {date, team1, team2, g1, g2}."""
    path = os.path.join(data_dir, "h2h_matches.csv")
    seen = set()
    matches = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            eid = row["event_id"]
            if eid in seen:
                continue
            seen.add(eid)
            gf = int(row["gf"])
            gd = int(row["gd"])
            matches.append({
                "date": _parse_date(row["date"]),
                "team1": row["team"],
                "team2": row["opponent"],
                "g1": gf,
                "g2": gf - gd,
            })
    return matches


def fit_dixon_coles(matches, cutoff_date, xi=DEFAULT_XI, min_date=None):
    """Fit attack/defense/rho using only matches strictly before cutoff_date
    (as-of, no lookahead — mirrors predict_match_asof's own discipline).
    `min_date` optionally bounds how far back matches are considered at all
    (irrelevant once xi has decayed them to ~0 weight, but keeps the fitted
    match count smaller/faster for very old cutoffs)."""
    train = [m for m in matches if m["date"] < cutoff_date and (min_date is None or m["date"] >= min_date)]
    if not train:
        raise ValueError(f"No training matches before {cutoff_date}")

    teams = sorted({m["team1"] for m in train} | {m["team2"] for m in train})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    t1 = np.array([idx[m["team1"]] for m in train])
    t2 = np.array([idx[m["team2"]] for m in train])
    g1 = np.array([m["g1"] for m in train], dtype=float)
    g2 = np.array([m["g2"] for m in train], dtype=float)
    days_ago = np.array([(cutoff_date - m["date"]).days for m in train], dtype=float)
    weights = np.exp(-xi * days_ago)

    def unpack(x):
        return x[:n], x[n:2 * n], x[2 * n]

    def neg_log_lik(x):
        alpha, beta, rho = unpack(x)
        lam1 = np.exp(alpha[t1] + beta[t2])
        lam2 = np.exp(alpha[t2] + beta[t1])
        ll = g1 * np.log(lam1) - lam1 + g2 * np.log(lam2) - lam2

        tau = np.ones_like(lam1)
        m00 = (g1 == 0) & (g2 == 0)
        m01 = (g1 == 0) & (g2 == 1)
        m10 = (g1 == 1) & (g2 == 0)
        m11 = (g1 == 1) & (g2 == 1)
        tau[m00] = 1 - lam1[m00] * lam2[m00] * rho
        tau[m01] = 1 + lam1[m01] * rho
        tau[m10] = 1 + lam2[m10] * rho
        tau[m11] = 1 - rho
        tau = np.clip(tau, 1e-8, None)
        ll = ll + np.log(tau)

        return -np.sum(weights * ll)

    x0 = np.zeros(2 * n + 1)
    res = minimize(neg_log_lik, x0, method="L-BFGS-B",
                   bounds=[(None, None)] * (2 * n) + [(-0.3, 0.3)])
    alpha, beta, rho = unpack(res.x)

    return {
        "teams": teams,
        "attack": {t: float(alpha[idx[t]]) for t in teams},
        "defense": {t: float(beta[idx[t]]) for t in teams},
        "rho": float(rho),
        "n_matches": len(train),
    }


def _poisson_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))


def _tau(x, y, lam1, lam2, rho):
    if x == 0 and y == 0:
        return 1 - lam1 * lam2 * rho
    if x == 0 and y == 1:
        return 1 + lam1 * rho
    if x == 1 and y == 0:
        return 1 + lam2 * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def team_lambdas(model, team_a, team_b):
    """Each team's fitted expected goals for this specific matchup. Teams
    unseen in the fitted corpus fall back to the average attack/defense
    across the fitted pool (an "average international team" prior) rather
    than erroring. Capped at 8.0 to guard against runaway lambdas for teams
    far outside the fitted distribution (e.g. a debutant with almost no
    history)."""
    attack, defense = model["attack"], model["defense"]
    avg_attack = sum(attack.values()) / len(attack)
    avg_defense = sum(defense.values()) / len(defense)

    a_att = attack.get(team_a, avg_attack)
    a_def = defense.get(team_a, avg_defense)
    b_att = attack.get(team_b, avg_attack)
    b_def = defense.get(team_b, avg_defense)

    lam_a = min(math.exp(a_att + b_def), 8.0)
    lam_b = min(math.exp(b_att + a_def), 8.0)
    return lam_a, lam_b


def predict_scoreline_grid(model, team_a, team_b, max_goals=MAX_GOALS):
    """Full P(team_a scores x, team_b scores y) grid, renormalized to sum
    to 1 after truncation at max_goals. Row x = team_a's goals, column y =
    team_b's goals — this is the model's actual native output; win/draw/
    loss are just this grid summed over its lower/diagonal/upper triangle."""
    lam_a, lam_b = team_lambdas(model, team_a, team_b)
    rho = model["rho"]
    grid = [[_poisson_pmf(x, lam_a) * _poisson_pmf(y, lam_b) * _tau(x, y, lam_a, lam_b, rho)
             for y in range(max_goals + 1)] for x in range(max_goals + 1)]
    total = sum(sum(row) for row in grid)
    return [[p / total for p in row] for row in grid], lam_a, lam_b


def most_likely_scoreline(model, team_a, team_b, max_goals=MAX_GOALS):
    """The single highest-probability exact scoreline (x, y) — a point
    estimate, not the win/draw/loss aggregate."""
    grid, _, _ = predict_scoreline_grid(model, team_a, team_b, max_goals)
    best, best_p = (0, 0), -1.0
    for x, row in enumerate(grid):
        for y, p in enumerate(row):
            if p > best_p:
                best_p, best = p, (x, y)
    return best


def predict_dixon_coles(model, team_a, team_b, max_goals=MAX_GOALS):
    """Returns (prob_a_win, prob_draw, prob_b_win) — the scoreline grid
    summed over its lower triangle (a>b), diagonal (a==b), upper triangle
    (a<b) respectively."""
    grid, _, _ = predict_scoreline_grid(model, team_a, team_b, max_goals)
    p_a = p_draw = p_b = 0.0
    for x, row in enumerate(grid):
        for y, p in enumerate(row):
            if x > y:
                p_a += p
            elif x == y:
                p_draw += p
            else:
                p_b += p
    return p_a, p_draw, p_b
