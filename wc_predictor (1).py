"""
World Cup Predictor Model
=========================
Full implementation of the two-layer architecture with Monte Carlo simulation.
All weights and constants are configurable variables at the top.
Load real data via init_from_csv(data_dir, year) before predicting anything.
"""

import csv
import math
import os
import random
from copy import deepcopy
from datetime import date


# =============================================================================
# CONFIGURABLE WEIGHTS & CONSTANTS
# =============================================================================

# --- Confederation Calibration Coefficients ---
# Multiplied into raw FIFA ranking to correct cross-confederation distortion.
# Values < 1.0 mean the confederation's rankings overstate quality.
# Values > 1.0 mean rankings understate quality.
CONF_COEFFICIENTS = {
    "UEFA":     1.00,
    "CONMEBOL": 1.00,
    "CONCACAF": 0.92,
    "CAF":      0.90,
    "AFC":      0.88,
    "OFC":      0.85,
}

# --- Static GD: Piecewise Linear Multiplier Anchor Points ---
# (adjusted_rank, multiplier) pairs. Interpolate between them.
STATIC_GD_ANCHORS = [
    (1,  2.0),
    (5,  1.8),
    (10, 1.5),
    (15, 1.4),
    (25, 1.1),
    (30, 1.0),
    (45, 0.7),
    (60, 0.6),
]

# --- Current Tournament: Static GD vs Player Performance Split ---
WEIGHT_STATIC_GD = 0.45
WEIGHT_PLAYER_PERF = 0.55

# --- Historical vs Current Weighting Curve ---
# Index = number of games played this tournament
HIST_WEIGHTS = [1.00, 0.92, 0.83, 0.73, 0.62, 0.49, 0.34, 0.15]
CURR_WEIGHTS = [0.00, 0.08, 0.17, 0.27, 0.38, 0.51, 0.66, 0.85]

# --- Historical Score: recency weighting across the last 3 World Cups ---
# Same decay shape as H2H (see recency_weight()), but scoped to ~4 WC
# cycles so the 3rd-most-recent included tournament still carries real
# weight instead of being cut off like H2H's hard 5-year window.
HIST_DECAY_MAX_YEARS = 16
HIST_DECAY_POWER = 1.5

# --- Player Performance: Recency Weights ---
# Key = number of games played, Value = list of weights (most recent first)
RECENCY_WEIGHTS = {
    1: [0.50],  # + 0.50 * prev_tournament_avg (handled in code)
    2: [0.50, 0.50],
    3: [0.35, 0.35, 0.30],
    4: [0.35, 0.35, 0.15, 0.15],
    5: [0.30, 0.30, 0.14, 0.13, 0.13],
    6: [0.30, 0.30, 0.10, 0.10, 0.10, 0.10],
    7: [0.30, 0.30, 0.08, 0.08, 0.08, 0.08, 0.08],
}

# --- Tactical Importance ---
TAU_MIN_CAPS = 5            # Minimum caps before tau kicks in
TAU_DEFAULT = 1.0           # Default multiplier for players below cap threshold

# --- Squad Depth Decay ---
# How much thin rotation penalises player performance.
# Applied as: 1.0 - DEPTH_DECAY_RATE * (1 - rotation_ratio) * games_played
# where rotation_ratio = unique_players_used / squad_size
DEPTH_DECAY_RATE = 0.02

# --- Layer 2a ---
ALPHA_HOME = 0.09           # Home advantage boost magnitude
ALPHA_STAKES = 0.05         # Stakes/motivation adjustment magnitude

# --- Layer 2b ---
# Tactical matchup matrix (halved values — gap subtraction produces full effect)
# Order: possession, counter, high_press, direct, low_block
STYLES = ["possession", "counter", "high_press", "direct", "low_block"]

MATCHUP_MATRIX = {
    #                        vs poss    vs counter  vs press   vs direct  vs low_block
    "possession":  {"possession":  0.000, "counter": -0.020, "high_press": -0.040, "direct":  0.020, "low_block": -0.020},
    "counter":     {"possession":  0.020, "counter":  0.000, "high_press":  0.020, "direct": -0.020, "low_block": -0.020},
    "high_press":  {"possession":  0.040, "counter": -0.020, "high_press":  0.000, "direct": -0.040, "low_block":  0.020},
    "direct":      {"possession": -0.020, "counter":  0.020, "high_press":  0.040, "direct":  0.000, "low_block":  0.040},
    "low_block":   {"possession":  0.020, "counter":  0.020, "high_press": -0.020, "direct": -0.040, "low_block":  0.000},
}

H2H_MAX_AGE_YEARS = 5       # Meetings older than this are excluded entirely
H2H_DECAY_POWER = 1.5       # Shape of the recency falloff within the window (see recency_weight())

# Per-meeting competition-tier multiplier. Order per project decision: World
# Cup > other competitive (qualifiers, continental cups, Nations League,
# etc.) > friendlies — "more weight, but not too different" (placeholder
# magnitudes, open for backtest tuning like K_SIG was).
H2H_TIER_WEIGHTS = {
    "world_cup": 1.3,
    "other": 1.0,
    "friendly": 0.7,
}

# --- Relative GD Comparison ---
# Built as a running, sequentially-updated rating (see
# compute_sequential_relative_gd()), not a snapshot aggregate — each team's
# relative_gd is updated match-by-match, in true chronological order. Each
# match's weight uses the opponent's EFFECTIVE rank: their static rank
# adjusted by how much they've been over/underperforming it so far
# (relative_gd immediately before this match), then ONE log-ratio — not two
# separately-signed terms multiplied together, which can silently flip
# sign when both go negative. A team's rating is therefore built partly
# from its opponents' ratings, which were themselves built from THEIR
# opponents' ratings before that, one step at a time as the tournament
# unfolds — not recursive in the sense of solving a circular system
# (strict chronological order means there's no cycle), just a chain of
# dependencies through time.
K_REL = 0.4                 # Log compression sensitivity (same formula used everywhere else)
K_FORM = 0.5                 # How much an opponent's own relative_gd shifts the match
                             # weight. Combined with K_REL's rank-gap term INSIDE an exp()
                             # rather than added to a "1 + ..." base — see
                             # compute_sequential_relative_gd for why this matters
                             # (naturally bounded above 0, no hard clamp needed). Self-
                             # bootstraps: relative_gd starts at 0.0 for everyone, so the
                             # form term is 0 for anyone's first match.
RGD_PRIOR_GAMES = 2          # Bayesian-style shrinkage: every team's running relative_gd
                             # average is computed as if they already had this many
                             # "neutral" (0.0) games before their first real one. Without
                             # this, a single early blowout result — with no averaging yet
                             # to soften it — can swing relative_gd to an extreme value
                             # (verified: Iraq's opening 1-4 loss alone put their rating
                             # past -4 with no shrinkage), which then distorts every
                             # opponent's form-term calculation downstream too.

# --- Relative GD: pre-tournament seed from the full international corpus ---
# relative_gd used to always start at 0.0 for every team at the beginning of
# every tournament, built from nothing but that tournament's ~7 games. This
# seeds it instead from an Elo-style rating built across the full
# international match corpus (h2h_matches.csv, 1998-2026, ~10k rows) —
# EXPERIMENTAL, being tested against the always-0.0 baseline (see
# test_elo_seed.py). Unlike relative_gd's in-tournament update (a shrinking
# running average — fine over ~7 games, but each new match's influence
# shrinks toward zero once too many games have accumulated, which would
# make a multi-year rating stubbornly slow to reflect squad turnover), the
# seed uses a FIXED step size per match (real Elo's mechanism), so recent
# results always carry meaningful weight no matter how much history exists.
USE_ELO_SEED = False         # toggle for A/B testing against the always-0.0 baseline
ELO_SEED_K = 0.15            # Fixed per-match step size (before tier scaling)
ELO_MAX_AGE_YEARS = H2H_MAX_AGE_YEARS   # reuse the same window as H2H, not a new cutoff

# Real-world World Cup start dates — used ONLY to decide which corpus
# matches count as "before this tournament" when computing the seed. 2022
# was Nov-Dec (Qatar, moved for climate); every other year is the usual
# June kickoff.
WC_START_DATES = {
    2002: "2002-05-31", 2006: "2006-06-09", 2010: "2010-06-11",
    2014: "2014-06-12", 2018: "2018-06-14", 2022: "2022-11-20",
    2026: "2026-06-11",
}

# --- International Form: pre-tournament signal from real player ratings
# across ALL competitions, not just World Cups (data/intl_player_ratings.csv,
# ~2,000 matches back to 2002 — separately scraped since fetch_wc_data.py
# only covers World Cup squads). Validated on its own (train_intl_ratings.py,
# 1,882 real matches with genuine as-of prior-form features): holdout
# improvement of +0.0227 Brier, 95% CI [+0.0174, +0.0280] — clearly
# significant, the first result in this whole data-expansion effort that
# didn't land in noise. K_FORM there was fit to 2.2817; WEIGHT_INTL_FORM
# here is a SEPARATE coefficient controlling how much this (normalized)
# signal nudges the WC model's own historical_score, tuned against the
# actual WC train/holdout backtest (4 random restarts converged identically
# to 0.4395; train 0.1744->0.1725, holdout 0.1590->0.1559 — holdout moved
# more than train, the healthy direction). Not independently significant on
# the WC-specific holdout alone (163 matches, CI [-0.0019,+0.0083]) — small
# sample and uneven year-coverage (0% for 2002, partial 2006-2014, full
# 2018+) dilute it there — but adopted anyway given the robust, consistent
# WC-backtest behavior plus the much larger corpus already proving the
# underlying signal is real, not noise.
USE_INTL_FORM = True         # toggle for A/B testing against the baseline
FORM_MAX_AGE_YEARS = 2.0     # shorter than H2H's 5-year window on purpose —
                             # a player's rating from 2 years ago says much
                             # less about current squad form than one from
                             # last month; recency matters more here.
FORM_DECAY_POWER = 1.0
WEIGHT_INTL_FORM = 0.4395    # additive nudge on normalized historical_score

# EXPERIMENTAL: intl_form's corpus (intl_player_ratings.csv) has real
# calendar dates — same as Dixon-Coles' corpus — so it doesn't strictly
# need FORM_MAX_AGE_YEARS's hard cutoff + power-law shape; an exact per-day
# exponential decay (exp(-xi*days), no hard cutoff, matching
# dixon_coles.py's own DEFAULT_XI on the same underlying question) is worth
# testing as a straight swap-in. FORM_DECAY_XI is a placeholder pending its
# own tuning pass — see optimize_form_decay.py.
USE_EXPONENTIAL_FORM_DECAY = False
FORM_DECAY_XI = 0.0018

# EXPERIMENTAL: fold the CURRENT tournament's own matches into the form
# signal too (instead of leaving them to a separate static_gd/player_perf
# "current" layer), so there's one continuously-updating signal instead of
# two mechanisms glued together by the HIST_WEIGHTS/CURR_WEIGHTS curve.
# WC matches don't carry real calendar dates in this dataset — only
# stage/round_num — so within-tournament recency is measured in GAMES AGO
# (this team's own match count back from the as-of cutoff), reusing the
# same general-purpose recency_weight() already used for calendar-based
# decay everywhere else, just fed a different unit. Two separate effects,
# both real: (a) any current-tournament match should count for more than
# an equally-recent broader-corpus one (TIER_CURRENT_TOURNAMENT_MULT), and
# (b) WITHIN the tournament, the most recent 1-2 matches specifically
# should count for even more than that flat boost alone would give them —
# an unexpected loss last match should dent a team's momentum more than
# the same loss three rounds ago would. (b) is CURRENT_MOMENTUM_* below,
# layered on top of (a), not a replacement for it.
USE_UNIFIED_FORM = False              # toggle — see build_teams_asof/compute_base_score
TIER_CURRENT_TOURNAMENT_MULT = 5.0    # flat baseline every current-tournament match gets
MOMENTUM_BOOST_MULT = 5.0             # ADDITIONAL bonus for the most recent games specifically,
                                       # stacked on top of the flat tier boost above, not
                                       # instead of it — placeholder pending tuning
# Momentum window is a fixed design choice ("previous 2 matches"), not a fit
# target — letting the window/decay shape float during tuning let the
# optimizer chase train-set noise (5-param search overfit badly: holdout
# got significantly worse). Only TIER/MOMENTUM/WEIGHT below are tuned.
CURRENT_MOMENTUM_MAX_GAMES = 2.0
CURRENT_MOMENTUM_DECAY_POWER = 1.0
WEIGHT_UNIFIED_FORM = 0.4395          # additive nudge on normalized historical_score — separate
                                       # from WEIGHT_INTL_FORM since this signal's statistical
                                       # properties differ once heavily-boosted in-tournament
                                       # matches are mixed in; the two paths are mutually
                                       # exclusive (see compute_base_score), starting from the
                                       # old intl_form-only value pending its own re-tuning.

# --- FIFA Rank Signal: raw FIFA ranking used as DIRECT evidence of team
# quality, not just as a relative baseline. Rank already appears elsewhere
# in the model (static_gd compares real performance against a rank-implied
# expectation; relative_gd uses it as a weighting factor) but nowhere said
# "this team's rank alone is evidence of quality" — a real gap, given a
# pure rank-only baseline (baseline_rank_only.py) beat the FULL model on
# holdout (0.1440 vs 0.1590) earlier this session. Tuned (not hand-set to
# 50/50) against the actual WC train/holdout backtest: 4 random restarts
# converged identically to 1.3401, comfortably interior to its [0,3] bounds
# (no boundary-hugging); train 0.1725->0.1671, holdout 0.1559->0.1501,
# holdout improving slightly more than train. Independently significant on
# the WC-specific 163-match holdout alone (95% CI [+0.0008,+0.0106],
# excludes zero) — cleaner than intl_form, which needed the larger
# international corpus to prove itself. Adopted.
USE_FIFA_RANK_SIGNAL = True    # toggle for A/B testing against the baseline
WEIGHT_FIFA_RANK = 1.3401      # additive nudge on normalized historical_score

# --- Gap Combination Weights ---
# Must sum to 1.0
# Originally jointly optimized via scipy.optimize (optimize_gap_weights.py),
# giving W_BASE=0.573/W_TAC=0.087/W_H2H=0.079/W_REL_GD=0.261/K_SIG=1.192.
# After intl_form and fifa_rank_signal were added (both strengthening the
# base/historical signal), H2H was re-tested via a deliberate drop ablation
# (test_drop_components.py) — not the model roaming to an arbitrary bound,
# a controlled "with vs without" comparison with bootstrap significance —
# and dropping it entirely proved a real, significant improvement: holdout
# 0.1501->0.1451, 95% CI [+0.0006,+0.0092] (current-dropped), clearly
# excludes zero. 4 random restarts converged identically. H2H's weight had
# already been the smallest in the original fit, and a separate test
# (train_reduced_corpus.py, 1,882 international matches) found it added
# nothing on top of a form-based signal even there — this is consistent
# with that, not a surprise. W_TAC was ALSO re-tested the same way and held
# its ground (not significant, CI [-0.0035,+0.0083]) — kept as-is.
W_BASE = 0.641              # Layer 1 + Layer 2a (base + match adjustments)
W_TAC = 0.104                # Tactical matchup
W_H2H = 0.0                  # Head-to-head — dropped; see note above
W_REL_GD = 0.255             # Relative GD comparison

# --- Sigmoid ---
# Refit alongside the W_H2H drop above (same optimization run) — K_SIG's
# effective steepness depends on the gap scale the W_* combination
# produces, so it moves whenever they do.
K_SIG = 1.037                 # Steepness constant
                              # Set for post-normalization gap scale where typical gaps ~0.5-1.5

# --- Monte Carlo ---
MC_SIMULATIONS = 10000      # Number of tournament simulations


# =============================================================================
# TEAMS / H2H_MATCHES — populated at runtime via init_from_csv(data_dir, year)
# =============================================================================
# No hardcoded placeholder roster — every prediction in this project now
# runs on real scraped SofaScore data (see fetch_wc_data.py / data/*.csv).
# These start empty and are only ever read after init_from_csv() has run.

TEAMS = {}

# Global precomputed adjusted FIFA rankings (populated by init_adjusted_ranks())
ADJUSTED_RANKS = {}

# Real per-match international history (all competitions, 2020+ — see
# fetch_h2h_data.py / data/h2h_matches.csv), two rows per match (one per
# team's perspective): {"team", "opponent", "gd", "year", "competition",
# "is_friendly"}. Populated by load_h2h_matches_csv() / init_from_csv().
H2H_MATCHES = []

# (team, opponent) -> [matching rows]. A flat scan of H2H_MATCHES per
# lookup is O(1724) and gets called for every team pair in the O(n^2)
# normalization loop for every single as-of match snapshot — this index
# turns that into an O(few) dict lookup. Always kept in sync with
# H2H_MATCHES via set_h2h_matches(); never assign H2H_MATCHES directly.
H2H_INDEX = {}


def set_h2h_matches(matches, index=None):
    """Set H2H_MATCHES and its lookup index together. Pass a precomputed
    `index` (e.g. from load_backtest_dataset()) to skip rebuilding it."""
    global H2H_MATCHES, H2H_INDEX
    H2H_MATCHES = matches
    if index is not None:
        H2H_INDEX = index
        return
    H2H_INDEX = {}
    for row in matches:
        H2H_INDEX.setdefault((row["team"], row["opponent"]), []).append(row)

# The tournament year predictions are currently being made "as of" — H2H age
# decay is measured against this, not real-world wall-clock time. Set by
# init_from_csv()/evaluate_brier() before any predictions for that year.
PREDICTION_YEAR = None

# event_id of the specific match currently being predicted, if any — excluded
# from its own H2H evidence. Without this, a match played this same calendar
# year (PREDICTION_YEAR granularity can't tell "before" from "after" within
# a year) would count its OWN real outcome as a "prior" H2H data point,
# since h2h_matches.csv is built from each team's *entire* history and
# naturally includes the tournament being predicted itself. Set/restored
# per-match by predict_match_asof(); leave None for direct predict_match()
# calls with no specific real event behind them.
EXCLUDE_H2H_EVENT_ID = None


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def recency_weight(years_since, max_years, power=1.5):
    """Weight in [0, 1] for something that happened `years_since` years ago:
    1.0 at years_since=0, decaying to 0.0 at years_since>=max_years. Used to
    fade out both individual H2H meetings and past-World-Cup historical
    performance the further back they are from the match being predicted."""
    if years_since >= max_years:
        return 0.0
    if years_since <= 0:
        return 1.0
    return 1.0 - (years_since / max_years) ** power


def init_adjusted_ranks():
    """Precompute adjusted FIFA rankings for all tournament teams.
    Must be called before any ranking-dependent computation."""
    global ADJUSTED_RANKS
    for name, data in TEAMS.items():
        ADJUSTED_RANKS[name] = data["raw_rank"] * CONF_COEFFICIENTS[data["confederation"]]


def get_adjusted_rank(team_data):
    """Step 0: Apply confederation calibration to raw FIFA ranking."""
    return team_data["raw_rank"] * CONF_COEFFICIENTS[team_data["confederation"]]


def piecewise_linear_multiplier(rank):
    """Interpolate the Static GD multiplier from anchor points."""
    anchors = STATIC_GD_ANCHORS

    # Clamp to anchor range
    if rank <= anchors[0][0]:
        return anchors[0][1]
    if rank >= anchors[-1][0]:
        return anchors[-1][1]

    # Find surrounding anchors and interpolate
    for i in range(len(anchors) - 1):
        r_low, m_low = anchors[i]
        r_high, m_high = anchors[i + 1]
        if r_low <= rank <= r_high:
            t = (rank - r_low) / (r_high - r_low)
            return m_low + t * (m_high - m_low)

    return 1.0  # fallback


def compute_static_gd(team_data):
    """Step 1a: Compute average quality-weighted goal difference."""
    matches = team_data["matches"]
    if not matches:
        return 0.0

    total = 0.0
    for match in matches:
        opp_adj_rank = ADJUSTED_RANKS.get(
            match["opponent"],
            match["opponent_raw_rank"] * CONF_COEFFICIENTS[match["opponent_conf"]]
        )
        multiplier = piecewise_linear_multiplier(opp_adj_rank)
        total += match["gd"] * multiplier

    return total / len(matches)


def compute_player_rating(player, num_games):
    """Compute a single player's recency-weighted tournament rating."""
    ratings = player["ratings"]  # most recent first
    actual_games = min(num_games, len(ratings))

    if actual_games == 0:
        return player.get("prev_tournament_avg", 6.0)

    if actual_games == 1:
        # 50% current + 50% previous tournament
        prev_avg = player.get("prev_tournament_avg", 6.0)
        if prev_avg == 0.0:
            return ratings[0]  # no previous tournament data
        return 0.50 * ratings[0] + 0.50 * prev_avg

    weights = RECENCY_WEIGHTS.get(actual_games, RECENCY_WEIGHTS[7])
    weighted_sum = sum(w * r for w, r in zip(weights, ratings[:actual_games]))
    return weighted_sum


def compute_tactical_importance(player):
    """Get the tactical importance multiplier for a player."""
    if player.get("caps", 0) < TAU_MIN_CAPS:
        return TAU_DEFAULT
    return player.get("tau", TAU_DEFAULT)


def compute_squad_depth_decay(team_data):
    """Compute squad depth decay modifier."""
    games_played = len(team_data["matches"])
    if games_played == 0:
        return 1.0

    rotation_ratio = team_data["unique_players_used"] / team_data["squad_size"]
    decay = 1.0 - DEPTH_DECAY_RATE * (1.0 - rotation_ratio) * games_played
    return max(decay, 0.5)  # floor at 0.5 to prevent extreme decay


def compute_player_performance(team_data):
    """Step 1b: Compute team player performance score."""
    players = team_data["players"]
    num_games = len(team_data["matches"])
    depth_decay = compute_squad_depth_decay(team_data)

    total = 0.0
    for player in players:
        tau = compute_tactical_importance(player)
        rating = compute_player_rating(player, num_games)
        total += tau * rating

    avg = total / len(players)
    return depth_decay * avg


def compute_tactical_execution(team_data):
    """Compute how well a team can execute their tactical style right now.
    Based on current form of high-tau players vs their historical average."""
    players = team_data["players"]
    num_games = len(team_data["matches"])
    tau_threshold = 1.10  # only players above this are considered "key"

    key_players = [p for p in players if p.get("tau", 1.0) >= tau_threshold]

    if not key_players:
        return 1.0  # team doesn't depend on individual stars

    form_ratios = []
    for p in key_players:
        current_rating = compute_player_rating(p, num_games)
        historical_avg = p.get("prev_tournament_avg", current_rating)
        if historical_avg > 0:
            form_ratios.append(current_rating / historical_avg)
        else:
            form_ratios.append(1.0)

    return sum(form_ratios) / len(form_ratios)


def normalize_components(values):
    """Standardize a list of values (subtract mean, divide by std).
    Returns normalized values. If std is 0, returns all zeros."""
    if not values:
        return values

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance) if variance > 0 else 1.0

    return [(v - mean) / std for v in values]


def compute_norm_params(values):
    """Compute mean and std for a list of values."""
    if not values:
        return 0.0, 1.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance) if variance > 0 else 1.0
    return mean, std


def normalize_value(value, mean, std):
    """Normalize a single value using precomputed mean and std."""
    return (value - mean) / std


def build_normalization_context(teams_dict):
    """Precompute normalization parameters across all teams in two passes.

    Pass 1: Compute mean/std for Layer 1 inner components (historical,
    static_gd, player_perf, overperformance — a precomputed per-team
    relative-GD rating again, see compute_sequential_relative_gd(), not a
    per-matchup quantity) from raw values and store them in NORM_CONTEXT so
    compute_base_score can normalize internally.

    Pass 2: Recompute adjusted scores (now with normalized base scores)
    and relational terms, then add their params to NORM_CONTEXT.
    """
    global NORM_CONTEXT

    # --- Pass 1: Layer 1 inner components (raw) ---
    pass1 = {
        "historical": [],
        "static_gd": [],
        "player_perf": [],
        "overperformance": [],
        "intl_form": [],
        "fifa_rank_score": [],
        "unified_form": [],
    }
    for data in teams_dict.values():
        pass1["historical"].append(data["historical_score"])
        pass1["static_gd"].append(compute_static_gd(data))
        pass1["player_perf"].append(compute_player_performance(data))
        pass1["overperformance"].append(compute_overperformance(data))
        pass1["intl_form"].append(data.get("intl_form", 0.0))
        adjusted_rank = data["raw_rank"] * CONF_COEFFICIENTS[data["confederation"]]
        pass1["fifa_rank_score"].append(-math.log(max(adjusted_rank, 0.1)))
        pass1["unified_form"].append(data.get("unified_form", 0.0))

    NORM_CONTEXT = {k: compute_norm_params(v) for k, v in pass1.items()}

    # --- Pass 2: Adjusted scores + relational terms ---
    # compute_base_score now normalizes internally using pass 1 params
    pass2 = {"adjusted_score": [], "tactical": [], "h2h": []}
    team_names = list(teams_dict.keys())

    for data in teams_dict.values():
        pass2["adjusted_score"].append(compute_adjusted_score(data, False, False))

    for i, name_a in enumerate(team_names):
        for j, name_b in enumerate(team_names):
            if i != j:
                pass2["tactical"].append(
                    compute_tactical_matchup_per_team(teams_dict[name_a], teams_dict[name_b])
                )
                pass2["h2h"].append(compute_h2h_per_team(name_a, name_b))

    NORM_CONTEXT.update({k: compute_norm_params(v) for k, v in pass2.items()})


# Global normalization context — built once, used by all match predictions
NORM_CONTEXT = None


def init_normalization():
    """Initialize normalization context from current team data.
    Must be called before any match predictions."""
    build_normalization_context(TEAMS)


def compute_base_score(team_data):
    """Step 1: Compute complete Layer 1 base score for a team.

    Normalizes StaticGD, PlayerPerf, and Historical using precomputed
    tournament-wide params before combining, so the 0.45/0.55 and
    hist/curr weights reflect true relative contributions.
    Falls back to raw values during pass 1 of init (NORM_CONTEXT not yet set).
    """
    games_played = len(team_data["matches"])
    games_idx = min(games_played, len(HIST_WEIGHTS) - 1)

    historical  = team_data["historical_score"]
    static_gd   = compute_static_gd(team_data)
    player_perf = compute_player_performance(team_data)
    intl_form   = team_data.get("intl_form", 0.0)
    unified_form = team_data.get("unified_form", 0.0)
    adjusted_rank = team_data["raw_rank"] * CONF_COEFFICIENTS[team_data["confederation"]]
    fifa_rank_score = -math.log(max(adjusted_rank, 0.1))

    if NORM_CONTEXT and "static_gd" in NORM_CONTEXT:
        mu_h, std_h = NORM_CONTEXT["historical"]
        mu_s, std_s = NORM_CONTEXT["static_gd"]
        mu_p, std_p = NORM_CONTEXT["player_perf"]
        historical  = (historical  - mu_h) / std_h
        static_gd   = (static_gd   - mu_s) / std_s
        player_perf = (player_perf - mu_p) / std_p
        if USE_UNIFIED_FORM and "unified_form" in NORM_CONTEXT:
            # Supersedes intl_form AND the separate static_gd/player_perf
            # "current" layer below — this signal already blends the
            # broader corpus with the current tournament's own matches
            # (heavily tier-boosted), so there's nothing left for a
            # separate within-tournament term to add. Mutually exclusive
            # with USE_INTL_FORM by design (see WEIGHT_UNIFIED_FORM).
            mu_u, std_u = NORM_CONTEXT["unified_form"]
            historical += WEIGHT_UNIFIED_FORM * ((unified_form - mu_u) / std_u)
            if USE_FIFA_RANK_SIGNAL and "fifa_rank_score" in NORM_CONTEXT:
                mu_r, std_r = NORM_CONTEXT["fifa_rank_score"]
                historical += WEIGHT_FIFA_RANK * ((fifa_rank_score - mu_r) / std_r)
            return historical
        if USE_INTL_FORM and "intl_form" in NORM_CONTEXT:
            mu_f, std_f = NORM_CONTEXT["intl_form"]
            historical += WEIGHT_INTL_FORM * ((intl_form - mu_f) / std_f)
        if USE_FIFA_RANK_SIGNAL and "fifa_rank_score" in NORM_CONTEXT:
            mu_r, std_r = NORM_CONTEXT["fifa_rank_score"]
            historical += WEIGHT_FIFA_RANK * ((fifa_rank_score - mu_r) / std_r)

    current = WEIGHT_STATIC_GD * static_gd + WEIGHT_PLAYER_PERF * player_perf

    w_hist = HIST_WEIGHTS[games_idx]
    w_curr = CURR_WEIGHTS[games_idx]

    return w_hist * historical + w_curr * current


def compute_home_advantage(team_data):
    """Step 2: Layer 2a — Home advantage."""
    if team_data["is_host"]:
        return ALPHA_HOME
    return 0.0


def compute_stakes(team_data, is_third_group_match, already_qualified):
    """Step 2: Layer 2a — Stakes/motivation adjustment."""
    if not is_third_group_match:
        return 0.0
    if already_qualified:
        return -ALPHA_STAKES
    return 0.0


def compute_adjusted_score(team_data, is_third_group_match, already_qualified):
    """Step 2: Compute AdjustedScore(T) = BaseScore + HomeAdv + Stakes."""
    base = compute_base_score(team_data)
    home = compute_home_advantage(team_data)
    stakes = compute_stakes(team_data, is_third_group_match, already_qualified)
    return base + home + stakes


def classify_h2h_tier(competition, is_friendly):
    """World Cup > other competitive (qualifiers, continental cups, Nations
    League, ...) > friendlies. `competition` is SofaScore's free-text
    tournament name, e.g. "FIFA World Cup, Group J" vs "World Cup
    Qualification, CONMEBOL" — the qualifier explicitly isn't the real
    thing, so it must NOT match the World Cup tier."""
    if is_friendly:
        return "friendly"
    name = (competition or "").lower()
    # SofaScore abbreviates qualifiers inconsistently: CONMEBOL/AFC/CAF spell
    # out "Qualification" but CONCACAF/UEFA/CAF playoffs use "Qual." — match
    # both so e.g. "World Cup Qual. CONCACAF, R. 3" doesn't slip through.
    if "world cup" in name and "qual" not in name:
        return "world_cup"
    return "other"


def compute_h2h_per_team(team_name, opponent_name):
    """Step 3b: Compute per-team H2H value from real per-match international
    history (H2H_MATCHES — all competitions, not just past World Cups). Each
    qualifying meeting (within H2H_MAX_AGE_YEARS of PREDICTION_YEAR)
    contributes win/draw/loss weighted by recency_weight() x its competition
    tier, so a competitive match last year counts far more than a friendly
    from four years ago.

    Returns (ratio - 0.5): 0 for an even/absent record, up to +-0.5 for a
    always-won/always-lost one. There used to be an ALPHA_H2H scale factor
    here (raw = 2 * ALPHA_H2H * (ratio - 0.5), clipped to +-ALPHA_H2H) meant
    to cap this component's influence in the same absolute units as
    ALPHA_HOME/ALPHA_STAKES. It was removed after backtest-tuning it
    (optimize_h2h_weights.py) showed 4 random restarts converging to wildly
    different ALPHA_H2H values (0.026 to 0.148) with byte-identical output:
    this function is the team's ENTIRE h2h score with nothing else mixed in,
    so gap_h2h = h2h_a - h2h_b is exactly proportional to any such scale
    factor, and compute_gap's gap_h2h_n = gap_h2h / std_h2h divides that
    factor right back out — std_h2h is computed from that same
    proportionally-scaled set. The clip was also always a no-op regardless:
    ratio is a weighted average of outcomes in [0, 1], so (ratio - 0.5) is
    already confined to [-0.5, 0.5] by construction, well inside any
    positive cap. W_H2H is the only constant that actually controls how
    much this component influences the final prediction."""
    weighted_outcome = 0.0
    weight_total = 0.0

    for row in H2H_INDEX.get((team_name, opponent_name), ()):
        if EXCLUDE_H2H_EVENT_ID and row["event_id"] == EXCLUDE_H2H_EVENT_ID:
            continue  # this IS the match being predicted — not "prior" evidence
        years_since = PREDICTION_YEAR - row["year"]
        if years_since < 0:
            continue  # can't use a match that happens after the one being predicted
        recency = recency_weight(years_since, H2H_MAX_AGE_YEARS, H2H_DECAY_POWER)
        if recency <= 0.0:
            continue
        tier = classify_h2h_tier(row["competition"], row["is_friendly"])
        weight = recency * H2H_TIER_WEIGHTS[tier]

        outcome = 1.0 if row["gd"] > 0 else (0.5 if row["gd"] == 0 else 0.0)
        weighted_outcome += weight * outcome
        weight_total += weight

    if weight_total <= 0.0:
        return 0.0

    ratio = weighted_outcome / weight_total
    return ratio - 0.5


def compute_sequential_relative_gd(rows, team_names, adjusted_ranks, seed=None):
    """Build every team's relative-GD rating by processing each real match
    ONCE, in true chronological order (see chronological_key), updating
    both participants together after each one — the Context(A,B) function
    from the original design spec, done as a running rating instead of a
    per-comparison lookup.

    `seed`, if given, is a {team_name: value} dict used as each team's
    STARTING rating instead of 0.0 — see _compute_elo_seed, which builds one
    from the full international match corpus so a team doesn't start every
    tournament from a blank slate with only ~7 games to learn from.

    Each match's weight combines the static rank gap with the opponent's
    current form as two terms INSIDE a single exp(), rather than added to a
    "1 + ..." base and then clamped:
        confidence(X) = min(1, games_played[X] / 3)
        weight_for_A  = exp(K_REL * ln(rank_A / rank_B) + K_FORM * confidence(B) * relative_gd[B])
    Two earlier versions both broke on the same failure mode from different
    angles. The first divided rank_B by (1 + K_FORM * confidence(B) *
    relative_gd[B]) to get an "effective rank" and log-ratio'd that —
    division near its floor could multiply the opponent's rank by up to 5x,
    swinging the log-ratio arbitrarily. The second added the rank-gap and
    form terms to a "1 + ..." base directly — bounded better, but the sum
    could still land below zero for any lopsided-enough matchup, requiring
    a hard `max(weight, WEIGHT_FLOOR)` clamp that (verified concretely)
    ended up floor-clamping nearly every blowout result to the same flat
    0.15, regardless of how one-sided it actually was. Both let weight go
    negative before being rescued after the fact — meaning a WIN could
    subtract from the winner's relative_gd unless the clamp caught it
    (verified: France beating a struggling Iraq 3-1 produced weight=-0.717
    pre-clamp). Wrapping the same two terms in exp() instead removes the
    failure mode at its source: exp() of any real number is always > 0, so
    the weight is a smooth, continuously-varying multiplier in (0, +inf)
    with no clamp required and no flat floor collapsing distinct blowouts
    into an identical weight. confidence(X) still ramps from 0 (first
    match: form term is fully silenced, matching a hard bootstrap) to 1
    (from the 3rd match onward), so a team's rating only starts influencing
    opponents' weights once there's more than a single-game sample behind
    it. Each team's rating is therefore built partly from its opponents'
    ratings, which were themselves built the same way from THEIR opponents
    before that — a chain through time, not a cycle, since strict
    chronological order means a rating is always fully "settled" before
    it's ever used to inform another one.

    `rows` must be pre-filtered to real, played matches only (blank-gd
    pending fixtures excluded) and already scoped to whatever as-of cutoff
    applies. `adjusted_ranks` is a plain {team_name: adjusted_rank} dict
    computed by the caller — deliberately NOT the global ADJUSTED_RANKS,
    since this can run before that global is populated (load_teams_from_csv
    happens before init_adjusted_ranks() in the usual call order). Returns
    {team_name: relative_gd}.
    """
    seen_events = set()
    events = []
    for r in rows:
        if r["gd"] == "":
            continue
        eid = r["event_id"]
        if eid in seen_events:
            continue
        seen_events.add(eid)
        events.append(r)

    events.sort(key=lambda r: chronological_key(r["stage"], r["round_num"]))

    seed = seed or {}
    relative_gd = {name: seed.get(name, 0.0) for name in team_names}
    games_played = {name: 0 for name in team_names}

    for r in events:
        team_a, team_b = r["team"], r["opponent"]
        if team_a not in relative_gd or team_b not in relative_gd:
            continue
        gd_a = int(r["gd"])
        gd_b = -gd_a

        rank_a = adjusted_ranks.get(team_a, 50)
        rank_b = adjusted_ranks.get(team_b, 50)

        confidence_a = min(1.0, games_played[team_a] / 3)
        confidence_b = min(1.0, games_played[team_b] / 3)

        log_rank_gap = math.log(rank_a / rank_b) if rank_a > 0 and rank_b > 0 else 0.0
        # Clamp the exponent, not the weight: exp() has no natural upper
        # bound, and an extreme-enough relative_gd chain (verified: possible
        # with a low RGD_PRIOR_GAMES + high K_FORM during a parameter sweep)
        # can overflow math.exp and crash outright. exp(20) ~= 4.85e8, already
        # far past any meaningful weight magnitude, so this never affects
        # realistic values — it's a pure safety bound.
        exponent_a = K_REL * log_rank_gap + K_FORM * confidence_b * relative_gd[team_b]
        exponent_b = -K_REL * log_rank_gap + K_FORM * confidence_a * relative_gd[team_a]
        weight_a = math.exp(max(-20.0, min(20.0, exponent_a)))
        weight_b = math.exp(max(-20.0, min(20.0, exponent_b)))

        contrib_a = gd_a * weight_a
        contrib_b = gd_b * weight_b

        # Shrinkage toward the neutral (0.0) prior: treat each team as if it
        # already had RGD_PRIOR_GAMES "neutral" games before this real one,
        # so a single early result can't swing the average to an extreme.
        n_a = games_played[team_a] + RGD_PRIOR_GAMES
        n_b = games_played[team_b] + RGD_PRIOR_GAMES
        relative_gd[team_a] = (relative_gd[team_a] * n_a + contrib_a) / (n_a + 1)
        relative_gd[team_b] = (relative_gd[team_b] * n_b + contrib_b) / (n_b + 1)
        games_played[team_a] += 1
        games_played[team_b] += 1

    return relative_gd


def compute_overperformance(team_data):
    """Step 3c: team_data's relative-GD rating, precomputed by
    compute_sequential_relative_gd() and stashed on the team dict (by
    load_teams_from_csv()/build_teams_asof()) as "relative_gd". Falls back
    to 0.0 (neutral) if it was never attached, e.g. hand-built team dicts
    outside the normal CSV-loading paths."""
    return team_data.get("relative_gd", 0.0)


def compute_tactical_matchup_per_team(team_data, opponent_data):
    """Step 3a: Compute per-team tactical matchup value (halved for gap)."""
    style_self = team_data["style"]
    style_opp = opponent_data["style"]

    raw_value = MATCHUP_MATRIX[style_self][style_opp]
    execution = compute_tactical_execution(team_data)

    return raw_value * execution


def compute_full_score(team_name, opponent_name, is_third_group_match=False,
                       already_qualified=False):
    """Compute complete Score(T) including all layers."""
    team_data = TEAMS[team_name]
    opponent_data = TEAMS[opponent_name]

    adjusted = compute_adjusted_score(team_data, is_third_group_match, already_qualified)
    tac = compute_tactical_matchup_per_team(team_data, opponent_data)
    h2h = compute_h2h_per_team(team_name, opponent_name)
    overperf = compute_overperformance(team_data)

    return {
        "adjusted_score": adjusted,
        "tactical": tac,
        "h2h": h2h,
        "overperformance": overperf,
        "total": adjusted + tac + h2h + overperf,
    }


def compute_gap(score_a, score_b):
    """Step 5: Compute weighted gap from two team scores.

    Each component gap is normalized using precomputed parameters
    so all components contribute on comparable scales regardless
    of their natural magnitudes.
    """
    gap_base = score_a["adjusted_score"] - score_b["adjusted_score"]
    gap_tac = score_a["tactical"] - score_b["tactical"]
    gap_h2h = score_a["h2h"] - score_b["h2h"]
    gap_overperf = score_a["overperformance"] - score_b["overperformance"]

    # Normalize each gap component using tournament-wide parameters
    if NORM_CONTEXT:
        # For gaps, we normalize by the std of the underlying component
        # (mean of gaps is ~0 by construction, so we just scale by std)
        _, std_base = NORM_CONTEXT["adjusted_score"]
        _, std_tac = NORM_CONTEXT["tactical"]
        _, std_h2h = NORM_CONTEXT["h2h"]
        _, std_overperf = NORM_CONTEXT["overperformance"]

        gap_base_n = gap_base / std_base if std_base > 0 else gap_base
        gap_tac_n = gap_tac / std_tac if std_tac > 0 else gap_tac
        gap_h2h_n = gap_h2h / std_h2h if std_h2h > 0 else gap_h2h
        gap_overperf_n = gap_overperf / std_overperf if std_overperf > 0 else gap_overperf
    else:
        gap_base_n = gap_base
        gap_tac_n = gap_tac
        gap_h2h_n = gap_h2h
        gap_overperf_n = gap_overperf

    weighted_gap = (
        W_BASE * gap_base_n
        + W_TAC * gap_tac_n
        + W_H2H * gap_h2h_n
        + W_REL_GD * gap_overperf_n
    )

    return {
        "gap_base": gap_base,
        "gap_tactical": gap_tac,
        "gap_h2h": gap_h2h,
        "gap_overperf": gap_overperf,
        "gap_base_norm": gap_base_n,
        "gap_tac_norm": gap_tac_n,
        "gap_h2h_norm": gap_h2h_n,
        "gap_overperf_norm": gap_overperf_n,
        "weighted_gap": weighted_gap,
    }


def sigmoid(gap):
    """Step 6: Convert gap to win probability via sigmoid."""
    exponent = -gap / K_SIG
    # Clamp to avoid overflow
    exponent = max(-500, min(500, exponent))
    return 1.0 / (1.0 + math.exp(exponent))


def predict_match(team_a_name, team_b_name, is_third_group_match=False,
                  a_qualified=False, b_qualified=False, verbose=True):
    """Full pipeline: predict a single match between two teams."""
    score_a = compute_full_score(team_a_name, team_b_name,
                                 is_third_group_match, a_qualified)
    score_b = compute_full_score(team_b_name, team_a_name,
                                 is_third_group_match, b_qualified)

    gap_info = compute_gap(score_a, score_b)
    prob_a = sigmoid(gap_info["weighted_gap"])
    prob_b = 1.0 - prob_a

    if verbose:
        print(f"\n{'='*60}")
        print(f"  {team_a_name} vs {team_b_name}")
        print(f"{'='*60}")
        print(f"\n  Layer 1+2a (Adjusted Scores):")
        print(f"    {team_a_name:>15}: {score_a['adjusted_score']:+.4f}")
        print(f"    {team_b_name:>15}: {score_b['adjusted_score']:+.4f}")
        print(f"\n  Layer 2b (Relational — per-team values):")
        print(f"    Tactical:   {team_a_name}: {score_a['tactical']:+.4f}  |  {team_b_name}: {score_b['tactical']:+.4f}")
        print(f"    H2H:        {team_a_name}: {score_a['h2h']:+.4f}  |  {team_b_name}: {score_b['h2h']:+.4f}")
        print(f"    OverPerf:   {team_a_name}: {score_a['overperformance']:+.4f}  |  {team_b_name}: {score_b['overperformance']:+.4f}")
        print(f"\n  Gap Breakdown (raw → normalized → weighted):")
        print(f"    Base:     {gap_info['gap_base']:+.4f} → {gap_info['gap_base_norm']:+.4f} × {W_BASE} = {W_BASE * gap_info['gap_base_norm']:+.4f}")
        print(f"    Tactical: {gap_info['gap_tactical']:+.4f} → {gap_info['gap_tac_norm']:+.4f} × {W_TAC} = {W_TAC * gap_info['gap_tac_norm']:+.4f}")
        print(f"    H2H:      {gap_info['gap_h2h']:+.4f} → {gap_info['gap_h2h_norm']:+.4f} × {W_H2H} = {W_H2H * gap_info['gap_h2h_norm']:+.4f}")
        print(f"    OverPerf: {gap_info['gap_overperf']:+.4f} → {gap_info['gap_overperf_norm']:+.4f} × {W_REL_GD} = {W_REL_GD * gap_info['gap_overperf_norm']:+.4f}")
        print(f"    Weighted total gap: {gap_info['weighted_gap']:+.4f}")
        print(f"\n  Result:")
        print(f"    {team_a_name:>15}:  {prob_a*100:5.1f}%")
        print(f"    {team_b_name:>15}:  {prob_b*100:5.1f}%")
        print(f"    Predicted winner: {team_a_name if prob_a > prob_b else team_b_name}")

    return {
        "team_a": team_a_name,
        "team_b": team_b_name,
        "prob_a": prob_a,
        "prob_b": prob_b,
        "gap": gap_info,
        "score_a": score_a,
        "score_b": score_b,
    }


def simulate_match(team_a_name, team_b_name, **kwargs):
    """Simulate a single match — sample a winner from the probability."""
    result = predict_match(team_a_name, team_b_name, verbose=False, **kwargs)
    if random.random() < result["prob_a"]:
        return team_a_name, result
    return team_b_name, result


def monte_carlo_tournament(bracket, n_simulations=MC_SIMULATIONS):
    """Run Monte Carlo simulation across a knockout bracket.

    Args:
        bracket: List of (team_a, team_b) tuples for the first round.
                 Winners are paired in order for subsequent rounds.
        n_simulations: Number of full tournament simulations.

    Returns:
        Dict of {team_name: {"champion": count, "rounds_won": {round: count}}}
    """
    team_names = set()
    for a, b in bracket:
        team_names.add(a)
        team_names.add(b)

    results = {name: {"champion": 0, "rounds_reached": {}} for name in team_names}

    for sim in range(n_simulations):
        current_round = list(bracket)
        round_num = 1

        while len(current_round) > 0:
            winners = []
            for team_a, team_b in current_round:
                winner, _ = simulate_match(team_a, team_b)
                winners.append(winner)

                # Track round reached
                round_key = f"Round {round_num}"
                results[winner].setdefault("rounds_reached", {})
                results[winner]["rounds_reached"][round_key] = \
                    results[winner]["rounds_reached"].get(round_key, 0) + 1

            if len(winners) == 1:
                results[winners[0]]["champion"] += 1
                break

            # Pair winners for next round
            current_round = []
            for i in range(0, len(winners), 2):
                if i + 1 < len(winners):
                    current_round.append((winners[i], winners[i + 1]))
                else:
                    # Bye (odd number of teams — shouldn't happen in proper bracket)
                    current_round.append((winners[i], winners[i]))

            round_num += 1

    return results


# =============================================================================
# CSV DATA LOADERS
# =============================================================================

# WC years in order — used to find the 3 most recent WCs before a target year
_WC_YEARS = [2002, 2006, 2010, 2014, 2018, 2022, 2026]


def load_teams_from_csv(data_dir, year, stages=None):
    """Build a TEAMS-format dict from the CSV files output by fetch_wc_data.py.

    stages: optional set of stage labels to include in match/rating data,
            e.g. {"group_stage"} for a pre-knockout backtest. None = all stages.
    """
    teams = {}

    # --- Team metadata ---
    teams_path = os.path.join(data_dir, "teams.csv")
    with open(teams_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["tournament_year"]) != year:
                continue
            name = row["name"]
            teams[name] = {
                "raw_rank":            int(row["raw_rank"]),
                "confederation":       row["confederation"],
                "style":               row["style"],
                "historical_score":    0.0,
                "is_host":             bool(int(row["is_host"])),
                "unique_players_used": 0,
                "squad_size":          int(row["squad_size"]),
                "players":             [],
                "matches":             [],
                "group":               "",
            }

    # --- Match results ---
    matches_path = os.path.join(data_dir, "matches.csv")
    raw_match_rows = []   # kept (with stage/round_num/event_id) for compute_sequential_relative_gd
    with open(matches_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["tournament_year"]) != year:
                continue
            if stages and row.get("stage") not in stages:
                continue
            team = row["team"]
            if team not in teams:
                continue
            if row["gd"] == "":
                continue   # pending fixture — not yet played, no result to learn from
            teams[team]["matches"].append({
                "opponent":          row["opponent"],
                "gd":                int(row["gd"]),
                "gf":                int(row["gf"]) if row.get("gf") else 0,
                "opponent_raw_rank": int(row["opponent_raw_rank"]),
                "opponent_conf":     row["opponent_conf"],
            })
            raw_match_rows.append(row)
            if row.get("group") and not teams[team]["group"]:
                teams[team]["group"] = row["group"]

    # --- Player ratings: group by (team, player_name), sort most-recent-first ---
    ratings_path = os.path.join(data_dir, "player_ratings.csv")
    player_games = {}
    if os.path.exists(ratings_path):
        with open(ratings_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if int(row["tournament_year"]) != year:
                    continue
                if stages and row.get("stage") not in stages:
                    continue
                key = (row["team"], row["player_name"])
                player_games.setdefault(key, []).append({
                    "round_num": int(row["round_num"]),
                    "rating":    float(row["rating"]),
                })

    for (team, player_name), games in player_games.items():
        if team not in teams:
            continue
        games.sort(key=lambda g: g["round_num"], reverse=True)
        teams[team]["players"].append({
            "name":                player_name,
            "ratings":             [g["rating"] for g in games],
            "tau":                 1.0,
            "prev_tournament_avg": 6.5,
            "caps":                20,
        })

    for data in teams.values():
        data["unique_players_used"] = len(data["players"])

    # --- Historical scores from past WC data ---
    historical = _compute_historical_scores(data_dir, year)
    for name, score in historical.items():
        if name in teams:
            teams[name]["historical_score"] = score

    # --- International form: pre-tournament signal from the broader
    # match corpus (see _compute_intl_form) ---
    intl_form = _compute_intl_form(data_dir, year, set(teams.keys())) if USE_INTL_FORM else {}
    for name in teams:
        teams[name]["intl_form"] = intl_form.get(name, 0.0)

    # --- Unified form: corpus partial sums, precomputed once here since they
    # don't depend on anything within-tournament (see _compute_unified_form,
    # which combines these with the CURRENT tournament's own matches fresh
    # at each as-of cutoff in build_teams_asof) ---
    corpus_partial = _compute_intl_form_corpus_partial(data_dir, year, set(teams.keys())) if USE_UNIFIED_FORM else {}
    for name in teams:
        teams[name]["intl_form_corpus_partial"] = corpus_partial.get(name, (0.0, 0.0))

    # --- Relative GD (Context(A,B)) — sequential rating, see compute_sequential_relative_gd ---
    local_adjusted_ranks = {
        name: data["raw_rank"] * CONF_COEFFICIENTS[data["confederation"]]
        for name, data in teams.items()
    }
    seed = _compute_elo_seed(data_dir, year, local_adjusted_ranks) if USE_ELO_SEED else {}
    relative_gd = compute_sequential_relative_gd(raw_match_rows, list(teams.keys()), local_adjusted_ranks, seed=seed)
    for name, value in relative_gd.items():
        teams[name]["relative_gd"] = value
        teams[name]["relative_gd_seed"] = seed.get(name, 0.0)

    return teams


def _compute_historical_scores(data_dir, target_year):
    """Compute historical_score for each team as a recency-weighted average
    of stage_points across their last 3 World Cups before target_year — the
    most recent of the 3 counts more than the oldest (see recency_weight()
    / HIST_DECAY_MAX_YEARS), rather than a flat unweighted mean."""
    hist_path = os.path.join(data_dir, "historical_wc.csv")
    if not os.path.exists(hist_path):
        return {}

    team_history = {}   # team -> {year: stage_points}
    with open(hist_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yr = int(row["tournament_year"])
            if yr >= target_year:
                continue
            team = row["team"]
            team_history.setdefault(team, {})[yr] = float(row["stage_points"])

    recent_wcs = [y for y in _WC_YEARS if y < target_year][-3:]

    scores = {}
    for team, history in team_history.items():
        weighted_sum = 0.0
        weight_total = 0.0
        for yr in recent_wcs:
            if yr not in history:
                continue
            w = recency_weight(target_year - yr, HIST_DECAY_MAX_YEARS, HIST_DECAY_POWER)
            weighted_sum += w * history[yr]
            weight_total += w
        scores[team] = weighted_sum / weight_total if weight_total > 0 else 0.10

    return scores


def _compute_elo_seed(data_dir, target_year, adjusted_ranks):
    """Pre-tournament Elo-style rating for every team, built from the full
    international match corpus (h2h_matches.csv) rather than just the
    current tournament's own games. See the ELO_SEED_K comment for why a
    fixed step size is used instead of relative_gd's in-tournament shrinking
    average. Returns {team_name: seed_value}, meant to be used as the
    STARTING point for compute_sequential_relative_gd's in-tournament
    sequence (same role historical_score plays: computed once here, then
    carried forward and never independently touched again this tournament).

    Only matches strictly before this tournament's real-world start date
    (WC_START_DATES) and within ELO_MAX_AGE_YEARS of it count — a team's
    rating shouldn't be dragged down by a squad that's mostly retired.
    Teams facing an opponent outside the current 48-team pool (e.g. a team
    that didn't qualify) still get a real update; the opponent's rank just
    falls back to a neutral default (50) since we have no better estimate
    for them and they're not this function's concern.
    """
    h2h_path = os.path.join(data_dir, "h2h_matches.csv")
    if not os.path.exists(h2h_path):
        return {}

    cutoff_date = WC_START_DATES.get(target_year, f"{target_year}-01-01")
    min_date = f"{int(cutoff_date[:4]) - ELO_MAX_AGE_YEARS}{cutoff_date[4:]}"

    seen_events = set()
    events = []
    with open(h2h_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            date = row["date"]
            if date >= cutoff_date or date < min_date:
                continue
            eid = row["event_id"]
            if eid in seen_events:
                continue
            seen_events.add(eid)
            events.append(row)

    events.sort(key=lambda r: r["date"])

    rating = {}
    games_played = {}

    def rank_of(team):
        return adjusted_ranks.get(team, 50)

    def sigmoid(x):
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))

    for r in events:
        team_a, team_b = r["team"], r["opponent"]
        gd_a = int(r["gd"])
        actual_a = 1.0 if gd_a > 0 else (0.5 if gd_a == 0 else 0.0)

        rating.setdefault(team_a, 0.0)
        rating.setdefault(team_b, 0.0)
        games_played.setdefault(team_a, 0)
        games_played.setdefault(team_b, 0)

        rank_a, rank_b = rank_of(team_a), rank_of(team_b)
        conf_a = min(1.0, games_played[team_a] / 3)
        conf_b = min(1.0, games_played[team_b] / 3)

        log_gap = math.log(rank_a / rank_b) if rank_a > 0 and rank_b > 0 else 0.0
        expected_a = sigmoid(-K_REL * log_gap + K_FORM * conf_b * rating[team_b])
        expected_b = sigmoid(K_REL * log_gap + K_FORM * conf_a * rating[team_a])

        tier = classify_h2h_tier(r["competition"], r["is_friendly"] == "1")
        step = ELO_SEED_K * H2H_TIER_WEIGHTS[tier]

        rating[team_a] += step * (actual_a - expected_a)
        rating[team_b] += step * ((1.0 - actual_a) - expected_b)
        games_played[team_a] += 1
        games_played[team_b] += 1

    return rating


def _compute_intl_form_corpus_partial(data_dir, target_year, team_names):
    """Broader-corpus half of the form signal, shared by both the standalone
    intl_form (pre-tournament only) and unified_form (also blends in the
    current tournament's own matches — see build_teams_asof). Returns
    {team: (weighted_sum, weight_total)} — UNDIVIDED partial sums, not a
    final average, so a caller can add more weighted contributions (e.g.
    current-tournament matches) before dividing once at the end.

    Recency-weighted average of each team's OWN match-level rating from
    real prior matches across all competitions (data/intl_player_ratings.csv),
    strictly before this tournament's start date. Each row in that CSV is a
    per-player rating for one match; team-level rating here is the minutes-
    weighted average of a team's own players in a given match, then those
    match-level averages are recency-weighted across a team's real match
    history (FORM_MAX_AGE_YEARS/FORM_DECAY_POWER — a much shorter window
    than historical_score's, since match-day squad ratings fade in
    relevance quickly compared to tournament stage-reached history).

    Coverage is real but uneven — full for 2018+, partial for 2006-2014,
    zero for 2002 (the scrape starts there, so there's no 2-year-prior
    window to draw on).
    """
    path = os.path.join(data_dir, "intl_player_ratings.csv")
    if not os.path.exists(path):
        return {}

    cutoff_date = WC_START_DATES.get(target_year, f"{target_year}-01-01")
    # No hard cutoff needed for the exponential path (it decays smoothly to
    # ~0 rather than needing a floor to stop reading) — read everything
    # strictly before cutoff_date instead of pre-filtering by age.
    min_date = ("0000-01-01" if USE_EXPONENTIAL_FORM_DECAY else
               f"{int(cutoff_date[:4]) - int(FORM_MAX_AGE_YEARS) - 1}{cutoff_date[4:]}")

    match_rating_sum = {}   # (event_id, team) -> minutes-weighted rating sum
    match_minutes_sum = {}
    match_date = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row_date = row["date"]
            if row_date >= cutoff_date or row_date < min_date:
                continue
            team = row["team"]
            if team not in team_names:
                continue
            minutes = float(row["minutes_played"] or 0)
            if minutes <= 0:
                continue
            key = (row["event_id"], team)
            match_rating_sum[key] = match_rating_sum.get(key, 0.0) + float(row["rating"]) * minutes
            match_minutes_sum[key] = match_minutes_sum.get(key, 0.0) + minutes
            match_date[key] = row_date

    team_history = {}   # team -> [(date, match_avg_rating), ...]
    for key, minutes in match_minutes_sum.items():
        _, team = key
        avg = match_rating_sum[key] / minutes
        team_history.setdefault(team, []).append((match_date[key], avg))

    target_dt = (int(cutoff_date[:4]), int(cutoff_date[5:7]), int(cutoff_date[8:10]))

    def years_before(date_str):
        y, m, d = int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10])
        return ((target_dt[0] - y) * 365.25 + (target_dt[1] - m) * 30.44 + (target_dt[2] - d)) / 365.25

    def days_before(date_str):
        y, m, d = int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10])
        return date(*target_dt) - date(y, m, d)

    partial = {}
    for team, history in team_history.items():
        weighted_sum, weight_total = 0.0, 0.0
        for date_str, rating in history:
            if USE_EXPONENTIAL_FORM_DECAY:
                days = days_before(date_str).days
                if days < 0:
                    continue
                w = math.exp(-FORM_DECAY_XI * days)
            else:
                age = years_before(date_str)
                if age < 0:
                    continue
                w = recency_weight(age, FORM_MAX_AGE_YEARS, FORM_DECAY_POWER)
            weighted_sum += w * rating
            weight_total += w
        partial[team] = (weighted_sum, weight_total)
    return partial


def _compute_intl_form(data_dir, target_year, team_names):
    """Standalone pre-tournament form signal (no current-tournament data) —
    see _compute_intl_form_corpus_partial for the shared computation. Teams
    with no qualifying prior matches get 0.0, which after normalization
    means "no adjustment" (same convention as historical_score's neutral
    default), not a penalty."""
    partial = _compute_intl_form_corpus_partial(data_dir, target_year, team_names)
    return {team: (ws / wt if wt > 0 else 0.0) for team, (ws, wt) in partial.items()}


def _current_tournament_match_ratings(cutoff_rows, rating_rows):
    """Team-level (minutes-weighted) rating per real match played so far
    this tournament, ordered most-recent-first per team, for
    unified_form's momentum weighting. Mirrors the broader corpus's
    match-level averaging (_compute_intl_form_corpus_partial) but keyed by
    chronological_key (stage/round_num) instead of a calendar date, since
    WC data doesn't carry real per-match dates.

    Returns {team: [(games_ago, rating), ...]} — games_ago=0 is that team's
    most recent real match as of this cutoff.
    """
    event_keys = {}   # event_id -> chronological_key, from cutoff_rows (already as-of filtered)
    for r in cutoff_rows:
        event_keys[r["event_id"]] = chronological_key(r["stage"], r["round_num"])

    rating_sum = {}    # (event_id, team) -> minutes-weighted sum
    minutes_sum = {}
    for r in rating_rows:
        eid = r["event_id"]
        if eid not in event_keys:
            continue   # not among this cutoff's real, played matches
        team = r["team"]
        minutes = float(r.get("minutes_played") or 0)
        if minutes <= 0:
            continue
        key = (eid, team)
        rating_sum[key] = rating_sum.get(key, 0.0) + float(r["rating"]) * minutes
        minutes_sum[key] = minutes_sum.get(key, 0.0) + minutes

    team_matches = {}   # team -> [(chronological_key, rating), ...]
    for key, minutes in minutes_sum.items():
        eid, team = key
        avg = rating_sum[key] / minutes
        team_matches.setdefault(team, []).append((event_keys[eid], avg))

    out = {}
    for team, matches in team_matches.items():
        matches.sort(key=lambda m: m[0], reverse=True)   # most recent first
        out[team] = [(i, rating) for i, (_, rating) in enumerate(matches)]
    return out


def _compute_unified_form(corpus_partial, current_tournament_ratings):
    """Combine the broader-corpus partial sums with the current tournament's
    own matches (see module docstring near USE_UNIFIED_FORM for the two
    separate effects this applies: a flat per-match tier boost for ANY
    current-tournament match, plus an additional momentum bonus for the
    most recent 1-2 specifically)."""
    result = {}
    teams = set(corpus_partial.keys()) | set(current_tournament_ratings.keys())
    for team in teams:
        weighted_sum, weight_total = corpus_partial.get(team, (0.0, 0.0))
        for games_ago, rating in current_tournament_ratings.get(team, []):
            momentum = recency_weight(games_ago, CURRENT_MOMENTUM_MAX_GAMES, CURRENT_MOMENTUM_DECAY_POWER)
            w = TIER_CURRENT_TOURNAMENT_MULT + MOMENTUM_BOOST_MULT * momentum
            weighted_sum += w * rating
            weight_total += w
        result[team] = weighted_sum / weight_total if weight_total > 0 else 0.0
    return result


def load_h2h_matches_csv(data_dir):
    """Load real per-match international history from h2h_matches.csv
    (fetch_h2h_data.py — all competitions since 2020, not just World Cups).
    Returns a flat list of row dicts; compute_h2h_per_team() filters/weights
    it per prediction rather than pre-aggregating, since the right weight
    for a meeting depends on how far it is from the specific match being
    predicted."""
    path = os.path.join(data_dir, "h2h_matches.csv")
    if not os.path.exists(path):
        return []

    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "team": row["team"], "opponent": row["opponent"],
                "gd": int(row["gd"]), "year": int(row["date"][:4]),
                "competition": row["competition"],
                "is_friendly": row["is_friendly"] == "1",
                "event_id": row.get("event_id", ""),
            })
    return rows


def init_from_csv(data_dir, year):
    """Populate global TEAMS and H2H_MATCHES with CSV-loaded data, and set
    PREDICTION_YEAR so H2H age decay is measured against the right year.
    Must be called before any prediction or backtesting."""
    global TEAMS, PREDICTION_YEAR
    TEAMS = load_teams_from_csv(data_dir, year)
    set_h2h_matches(load_h2h_matches_csv(data_dir))
    PREDICTION_YEAR = year
    print(f"Loaded {len(TEAMS)} teams from CSV  (WC {year})")
    print(f"Loaded {len(H2H_MATCHES)} H2H match rows from CSV")


# =============================================================================
# AS-OF SNAPSHOTS — predicting a match using only data available before it
# =============================================================================
# A plain load_teams_from_csv(data_dir, year) gives each team's FULL season
# (every match they ever played that year). Predicting match N with team data
# that includes matches N+1, N+2, ... is hindsight, not a forecast. These
# helpers truncate a team's matches/player-ratings to strictly before a given
# point in the tournament, so backtesting and the live 2026 export both
# predict each match the way a forecaster actually would have, in order.

# Stage tier for chronological ordering. NOT the scraped `round_num` field,
# which is a SofaScore-internal counter that does not increase monotonically
# across stages (e.g. round_of_16 can come back with a lower round_num than
# round_of_32). Within group_stage, round_num (1/2/3) IS the real matchday
# and is used for sub-ordering; every other stage collapses to tier-only
# ordering since all its matches are effectively simultaneous.
STAGE_RANK = {
    "group_stage": 0, "round_of_32": 1, "round_of_16": 2,
    "quarter_final": 3, "semi_final": 4, "final": 5, "third_place": 5,
}


def chronological_key(stage, round_num):
    if stage == "group_stage":
        return (STAGE_RANK[stage], int(round_num))
    return (STAGE_RANK[stage], 0)


def read_matches_csv(data_dir, year):
    path = os.path.join(data_dir, "matches.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if int(r["tournament_year"]) == year]


def read_ratings_csv(data_dir, year):
    path = os.path.join(data_dir, "player_ratings.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if int(r["tournament_year"]) == year]


def build_teams_asof(base_teams, match_rows, rating_rows, cutoff_key):
    """A deep-copied snapshot of every team's data truncated to only what
    happened strictly before cutoff_key. Historical (prior-WC) score is
    unaffected since it doesn't depend on the current tournament."""
    snap = {}
    for name, data in base_teams.items():
        snap[name] = {
            "raw_rank": data["raw_rank"], "confederation": data["confederation"],
            "style": data["style"], "historical_score": data["historical_score"],
            "is_host": data["is_host"], "squad_size": data["squad_size"],
            "group": data["group"], "matches": [], "players": [],
            "relative_gd_seed": data.get("relative_gd_seed", 0.0),
            "intl_form": data.get("intl_form", 0.0),
            "intl_form_corpus_partial": data.get("intl_form_corpus_partial", (0.0, 0.0)),
        }

    cutoff_rows = []   # kept (with stage/round_num/event_id) for compute_sequential_relative_gd
    for r in match_rows:
        if r["gd"] == "":
            continue   # not yet played
        if chronological_key(r["stage"], r["round_num"]) >= cutoff_key:
            continue
        team = r["team"]
        if team not in snap:
            continue
        snap[team]["matches"].append({
            "opponent": r["opponent"], "gd": int(r["gd"]), "gf": int(r.get("gf") or 0),
            "opponent_raw_rank": int(r["opponent_raw_rank"]),
            "opponent_conf": r["opponent_conf"],
        })
        cutoff_rows.append(r)

    player_games = {}
    for r in rating_rows:
        if chronological_key(r["stage"], r["round_num"]) >= cutoff_key:
            continue
        key = (r["team"], r["player_name"])
        player_games.setdefault(key, []).append(
            (chronological_key(r["stage"], r["round_num"]), float(r["rating"]))
        )
    for (team, player_name), games in player_games.items():
        if team not in snap:
            continue
        games.sort(key=lambda g: g[0], reverse=True)
        snap[team]["players"].append({
            "name": player_name, "ratings": [g[1] for g in games],
            "tau": 1.0, "prev_tournament_avg": 6.5, "caps": 20,
        })

    for data in snap.values():
        data["unique_players_used"] = len(data["players"])
        if not data["players"]:
            # No minutes yet — compute_player_performance divides by
            # len(players), so seed one neutral placeholder.
            data["players"] = [{"name": "_none", "ratings": [], "tau": 1.0,
                                "prev_tournament_avg": 6.5, "caps": 20}]

    # --- Relative GD (Context(A,B)) — sequential rating, as-of this cutoff ---
    local_adjusted_ranks = {
        name: data["raw_rank"] * CONF_COEFFICIENTS[data["confederation"]]
        for name, data in snap.items()
    }
    seed = {name: data["relative_gd_seed"] for name, data in snap.items()} if USE_ELO_SEED else {}
    relative_gd = compute_sequential_relative_gd(cutoff_rows, list(snap.keys()), local_adjusted_ranks, seed=seed)
    for name, value in relative_gd.items():
        snap[name]["relative_gd"] = value

    # --- Unified form: broader-corpus partial sums (precomputed once,
    # copied forward above) combined fresh with the CURRENT tournament's
    # own matches as-of this cutoff (see _compute_unified_form) ---
    if USE_UNIFIED_FORM:
        corpus_partial = {name: data["intl_form_corpus_partial"] for name, data in snap.items()}
        current_ratings = _current_tournament_match_ratings(cutoff_rows, rating_rows)
        unified_form = _compute_unified_form(corpus_partial, current_ratings)
        for name, value in unified_form.items():
            if name not in snap:
                continue   # e.g. a stray legacy name variant in rating_rows, not a real 2026-pool team
            snap[name]["unified_form"] = value

    return snap


def predict_match_asof(team_a, team_b, stage, round_num, base_teams, match_rows, rating_rows,
                       event_id=None):
    """predict_match(), but using only data available strictly before this
    match (stage/round_num) instead of each team's whole season.

    Pass `event_id` when it's known (e.g. backtesting a real historical
    match) so H2H_MATCHES excludes that exact event from its own evidence —
    h2h_matches.csv is built from each team's *entire* match history, so
    without this a match played this same calendar year would otherwise see
    its own real outcome as a "prior" H2H data point."""
    cutoff = chronological_key(stage, round_num)
    snapshot = build_teams_asof(base_teams, match_rows, rating_rows, cutoff)

    global TEAMS, NORM_CONTEXT, EXCLUDE_H2H_EVENT_ID
    original_teams, original_norm = TEAMS, NORM_CONTEXT
    original_exclude = EXCLUDE_H2H_EVENT_ID
    TEAMS = snapshot
    EXCLUDE_H2H_EVENT_ID = event_id
    try:
        init_normalization()
        result = predict_match(team_a, team_b, verbose=False)
    finally:
        TEAMS, NORM_CONTEXT = original_teams, original_norm
        EXCLUDE_H2H_EVENT_ID = original_exclude
    return result


def load_backtest_dataset(data_dir, years):
    """Load and parse everything evaluate_brier() needs, once. Reuse the
    returned object across many evaluate_brier() calls (e.g. a weight-tuning
    sweep) instead of re-reading/re-parsing the same CSVs from disk on every
    single candidate — the raw data doesn't change between weight configs,
    only the scoring does."""
    dataset = {}
    for year in years:
        h2h_matches = load_h2h_matches_csv(data_dir)
        h2h_index = {}
        for row in h2h_matches:
            h2h_index.setdefault((row["team"], row["opponent"]), []).append(row)
        dataset[year] = {
            "base_teams": load_teams_from_csv(data_dir, year),
            "h2h_matches": h2h_matches,
            "h2h_index": h2h_index,
            "match_rows": read_matches_csv(data_dir, year),
            "rating_rows": read_ratings_csv(data_dir, year),
        }
    return dataset


def evaluate_brier(data_dir, years, dataset=None, return_errors=False):
    """Predict every real match in `years` as-of just before it was played,
    and score the model's calibration with the Brier score:
        BS = mean((predicted_prob_team1_wins - actual_outcome)^2)
    actual_outcome is 1/0.5/0 for win/draw/loss from team1's perspective
    (the model only outputs a win probability, so draws are scored as a
    half-credit outcome — a standard convention for evaluating win-only
    models against real results that include draws).

    Pass a `dataset` from load_backtest_dataset() to skip re-reading CSVs —
    essential when calling this many times in a row (weight tuning), since
    only the weight constants change between calls, not the underlying data.

    Returns (brier_score, n_matches) normally. Pass return_errors=True to get
    a third element back — a list of (year, event_id, squared_error) for
    every match, in the same order every time for the same `years` — needed
    to bootstrap a confidence interval on the score, or a paired confidence
    interval on the DIFFERENCE between two weight configs (see
    bootstrap_ci.py): resampling the aggregate score alone can't distinguish
    "genuinely better" from "noise," and several apparent improvements this
    project found late (e.g. the H2H tier/decay sweep) turned out to be
    within noise once actually checked.
    """
    global TEAMS, PREDICTION_YEAR
    if dataset is None:
        dataset = load_backtest_dataset(data_dir, years)

    total_sq_error = 0.0
    n = 0
    errors = []

    for year in years:
        base_teams = dataset[year]["base_teams"]
        TEAMS = base_teams
        init_adjusted_ranks()
        # Real head-to-head history (all competitions — see
        # fetch_h2h_data.py). Without this, compute_h2h_per_team returns 0.0
        # for every match and W_H2H tunes against a component that does
        # nothing (h2h_matches.csv only goes back to 2020, so years before
        # that — e.g. a 2018 backtest — will still see effectively zero H2H
        # signal; that's a real data-coverage limit, not a bug).
        set_h2h_matches(dataset[year]["h2h_matches"], index=dataset[year]["h2h_index"])
        PREDICTION_YEAR = year
        match_rows = dataset[year]["match_rows"]
        rating_rows = dataset[year]["rating_rows"]

        seen_events = set()
        for r in match_rows:
            if r["gd"] == "":
                continue
            eid = r["event_id"]
            if eid in seen_events:
                continue
            seen_events.add(eid)

            team1, team2 = r["team"], r["opponent"]
            gd = int(r["gd"])
            actual = 1.0 if gd > 0 else (0.0 if gd < 0 else 0.5)

            result = predict_match_asof(team1, team2, r["stage"], r["round_num"],
                                        base_teams, match_rows, rating_rows,
                                        event_id=r["event_id"])
            predicted = result["prob_a"]

            sq_error = (predicted - actual) ** 2
            total_sq_error += sq_error
            n += 1
            if return_errors:
                errors.append((year, eid, sq_error))

    brier = total_sq_error / n if n else float("nan")
    if return_errors:
        return brier, n, errors
    return brier, n


# =============================================================================
# BACKTEST
# =============================================================================

# Actual 2022 WC knockout results (used for comparison only)
_WC2022_R16 = [
    ("Netherlands", "USA"),
    ("Argentina",   "Australia"),
    ("Japan",       "Croatia"),
    ("Brazil",      "South Korea"),
    ("England",     "Senegal"),
    ("France",      "Poland"),
    ("Morocco",     "Spain"),
    ("Portugal",    "Switzerland"),
]
_WC2022_ACTUAL = {
    "R16":     {"Netherlands", "Argentina", "Croatia", "Brazil",
                "England", "France", "Morocco", "Portugal"},
    "QF":      {"Argentina", "Croatia", "France", "Morocco"},
    "SF":      {"Argentina", "France"},
    "champion": "Argentina",
    "runner_up": "France",
    "third":    "Croatia",
    "fourth":   "Morocco",
}


def backtest_2022(data_dir):
    """Load 2022 group-stage data only, predict the knockout bracket,
    and compare predictions to what actually happened."""
    global TEAMS, PREDICTION_YEAR

    print("\n" + "=" * 62)
    print("  BACKTEST: WC 2022  — predicting knockouts from group stage")
    print("=" * 62)

    TEAMS = load_teams_from_csv(data_dir, 2022, stages={"group_stage"})
    set_h2h_matches(load_h2h_matches_csv(data_dir))
    PREDICTION_YEAR = 2022

    missing = [t for pair in _WC2022_R16 for t in pair if t not in TEAMS]
    if missing:
        print(f"\n  WARNING: teams not found in CSV: {missing}")
        print("  Check name spellings in fetch_wc_data.py NAME_OVERRIDES")
        return

    print(f"\n  Teams loaded: {len(TEAMS)}  |  H2H match rows: {len(H2H_MATCHES)}")

    init_adjusted_ranks()
    init_normalization()

    # ------------------------------------------------------------------ #
    # R16 match-by-match predictions                                      #
    # ------------------------------------------------------------------ #
    print("\n>>> R16 PREDICTIONS  (actual winner in brackets)")
    print("-" * 62)
    correct_r16 = 0
    for team_a, team_b in _WC2022_R16:
        res = predict_match(team_a, team_b, verbose=False)
        predicted = team_a if res["prob_a"] > res["prob_b"] else team_b
        actual    = team_a if team_a in _WC2022_ACTUAL["R16"] else team_b
        tick = "✓" if predicted == actual else "✗"
        if predicted == actual:
            correct_r16 += 1
        print(f"  {tick}  {team_a:>16} {res['prob_a']*100:5.1f}%  vs"
              f"  {team_b:<16} {res['prob_b']*100:5.1f}%"
              f"   → pred: {predicted}  [actual: {actual}]")

    print(f"\n  R16 accuracy: {correct_r16}/{len(_WC2022_R16)}")

    # ------------------------------------------------------------------ #
    # Full Monte Carlo from R16                                           #
    # ------------------------------------------------------------------ #
    print(f"\n>>> MONTE CARLO TOURNAMENT  ({MC_SIMULATIONS:,} simulations)")
    print("-" * 62)

    mc = monte_carlo_tournament(_WC2022_R16)

    actual_stage = {}
    for t in _WC2022_ACTUAL["R16"]:
        actual_stage[t] = "R16"
    for t in _WC2022_ACTUAL["QF"]:
        actual_stage[t] = "QF"
    for t in _WC2022_ACTUAL["SF"]:
        actual_stage[t] = "SF"
    actual_stage[_WC2022_ACTUAL["runner_up"]]  = "Final"
    actual_stage[_WC2022_ACTUAL["champion"]]   = "WINNER"

    all_teams = sorted(mc.items(),
                       key=lambda x: x[1]["champion"], reverse=True)

    print(f"\n  {'Team':>16}  Champion%   Actual reached")
    print("  " + "-" * 44)
    for name, data in all_teams:
        champ_pct = data["champion"] / MC_SIMULATIONS * 100
        actual_r  = actual_stage.get(name, "R16 exit")
        marker    = " ←" if name == _WC2022_ACTUAL["champion"] else ""
        print(f"  {name:>16}   {champ_pct:6.2f}%     {actual_r}{marker}")

    champ_rank = [n for n, _ in all_teams].index(_WC2022_ACTUAL["champion"]) + 1
    champ_pct  = mc[_WC2022_ACTUAL["champion"]]["champion"] / MC_SIMULATIONS * 100
    print(f"\n  Actual champion ({_WC2022_ACTUAL['champion']}) ranked "
          f"#{champ_rank} by model  ({champ_pct:.1f}% predicted)")


if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
    backtest_2022(DATA_DIR)
