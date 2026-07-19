"""
"My Poisson" — a Poisson goal-scoring model derived from the CUSTOM model's
own weighted_gap signal (wc_predictor (1).py's compute_gap), rather than a
separately-fit attack/defense system like dixon_coles.py:

    lambda_A = exp(ALPHA + BETA * weighted_gap)
    lambda_B = exp(ALPHA - BETA * weighted_gap)

weighted_gap already blends FIFA rank, historical form, tactics, H2H, and
relative-GD into one signal (see wc_predictor (1).py), so this is a 2-
parameter translation of that existing signal into goals-space, fit via
genuine Poisson maximum likelihood (not a linear-regression proxy) on real
regulation-time goals (reg_gf/reg_gd — see fetch_wc_data.py's penalty-
shootout handling, and patch_reg_scores.py for how the historical data was
corrected). Despite being ~75x fewer parameters than Dixon-Coles
(2 vs ~150), it landed within noise of it on win/loss Brier and close on
goals R^2 in backtesting — see implied_poisson.py for the original
exploration.

ALPHA/BETA fit once on the WC train years (2002-2018, n=320) using real
reg_gf/reg_gd; holdout-checked (2022+2026) in the same conversation that
produced these values. Not re-fit at runtime — same reasoning as
dixon_coles.DEFAULT_XI being a checked-in constant, not a live parameter.
"""
import math

ALPHA = 0.1656
BETA = 0.3045

MAX_GOALS = 10


def _poisson_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))


def team_lambdas(weighted_gap):
    lam_a = math.exp(ALPHA + BETA * weighted_gap)
    lam_b = math.exp(ALPHA - BETA * weighted_gap)
    return lam_a, lam_b


def predict_scoreline_grid(weighted_gap, max_goals=MAX_GOALS):
    """Full P(team_a scores x, team_b scores y) grid — no Dixon-Coles-style
    low-score tau correction here (this model never fit one; the two
    scores are independent Poissons), renormalized to sum to 1 after
    truncation at max_goals."""
    lam_a, lam_b = team_lambdas(weighted_gap)
    grid = [[_poisson_pmf(x, lam_a) * _poisson_pmf(y, lam_b) for y in range(max_goals + 1)]
            for x in range(max_goals + 1)]
    total = sum(sum(row) for row in grid)
    return [[p / total for p in row] for row in grid]


def most_likely_scoreline(weighted_gap, max_goals=MAX_GOALS):
    """The single highest-probability exact scoreline (x, y) — a point
    estimate, not the win/draw/loss aggregate."""
    grid = predict_scoreline_grid(weighted_gap, max_goals)
    best, best_p = (0, 0), -1.0
    for x, row in enumerate(grid):
        for y, p in enumerate(row):
            if p > best_p:
                best_p, best = p, (x, y)
    return best


def predict_outcome_probs(weighted_gap, max_goals=MAX_GOALS):
    """Returns (prob_a_win, prob_draw, prob_b_win) for a matchup, given the
    custom model's own weighted_gap for it (positive = team A favored)."""
    grid = predict_scoreline_grid(weighted_gap, max_goals)
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
