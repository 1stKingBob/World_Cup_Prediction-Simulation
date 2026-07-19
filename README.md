# World Cup Predictor

A win-probability model for the 2026 World Cup, backed by real scraped tournament and player data, with a React frontend that visualizes group standings, bracket predictions, and lets you rewind the tournament to see how predictions evolve as results come in.

## Architecture

The model scores each team with a layered scoring system, then converts the gap between two teams into a win probability.

**Layer 1 — Base Team Score**
- Historical performance across a team's last 3 World Cups, recency-weighted so the most recent one counts more.
- Static goal-difference performance in the current tournament, anchored against FIFA-ranking bands.
- Player-level squad ratings, weighted toward more recent matches within the tournament.

These three combine into one base score via `WEIGHT_STATIC_GD` / `WEIGHT_PLAYER_PERF`, blended with the historical score according to how many matches the team has played so far this tournament (early on, historical performance dominates; by the later rounds, current form takes over).

**Layer 2a — Per-team match adjustments**
- Home advantage (`ALPHA_HOME`) for host nations.
- Stakes/motivation adjustment (`ALPHA_STAKES`) for high-importance matches.

**Layer 2b — Relational terms** (only exist as a comparison between two specific teams)
- **Tactical matchup**: a style-vs-style matrix (possession, counter, high-press, direct, low-block) capturing classic tactical advantages/disadvantages.
- **Head-to-head record**: real per-match international history between the two teams (not just prior World Cups — continental championships, qualifiers, and friendlies all count, weighted by competition tier and recency).
- **Relative GD (`Context(A,B)`)**: see below — a team's over/underperformance relative to its rank, adjusted for the strength of the opposition it was earned against.

All four gap components (base, tactical, H2H, relative GD) are combined via a weighted sum (`W_BASE`, `W_TAC`, `W_H2H`, `W_REL_GD` — must sum to 1) and passed through a sigmoid (`K_SIG`) to produce a win probability.

## Relative GD — sequential, opponent-aware rating

Rather than a flat "how much has this team over/underperformed" number, Relative GD is built as a **running rating updated match-by-match, in true chronological order**. After every real match, each team's rating shifts based on the goal difference *and* how strong the opponent was playing at that moment — not just their static rank.

The per-match weight combines the rank gap and the opponent's current form **inside a single `exp()`**, rather than adding them to a linear base and clamping the result:

```
weight_for_A = exp(K_REL * ln(rank_A / rank_B) + K_FORM * confidence(B) * relative_gd[B])
```

This is deliberate: an earlier version added these two terms to a `1 + ...` base and clamped negative results at a floor, but that clamp collapsed many different blowout results down to the same flat value, losing information. Wrapping both terms in `exp()` instead keeps the weight a smooth, continuously-varying multiplier that's always positive by construction — no clamp needed, and a win can never mathematically subtract from a team's rating (a real bug an earlier formulation had). `confidence(X)` ramps up over a team's first few matches, so an early single-game result can't swing the rating to an extreme value before there's enough evidence to trust it.

Each team's rating is therefore built partly from its opponents' ratings, which were themselves built the same way from *their* opponents before that — a chain through time, not a circular dependency, since strict chronological order means a rating is always fully settled before it's used to inform another one.

## As-of prediction & the anchor slider

Every prediction is made "as-of" a specific point in time — using only real results that happened strictly before it, never the outcome of the match being predicted or anything after it. This is what prevents lookahead bias: a Round of 16 prediction only sees real group-stage results, not the R16 match's own outcome or anything from the quarterfinals onward.

The frontend exposes this directly: moving the tournament-stage slider re-predicts every match using only the information that would have been available at that point, rather than showing one frozen probability regardless of when you're looking from. Every match is precomputed at all 8 possible anchor points (pre-tournament through each real match's own natural cutoff), so moving the slider is an instant client-side re-selection, not a live recomputation.

## Validation methodology

- **Train/holdout split**: 2002–2018 World Cups for fitting (320 real matches), 2022 and 2026 held out entirely (163 matches) and never touched during any tuning.
- **Metric**: Brier score — `mean((predicted_probability - actual_outcome)²)`, a proper scoring rule for probabilistic forecasts. Lower is better; a model that outputs 70% for something that happens 70% of the time scores well, regardless of whether any single prediction "looks right."
- **As a sanity floor**: a model with zero information — predicting 50/50 for every match — scores exactly **0.25** on this metric, always, by construction (`(0.5-1)² = (0.5-0)² = (0.5-0.5)² = 0.25` regardless of the actual outcome). The full model currently scores **0.174 on train and 0.159 on holdout** — clearly and substantially better than having no signal at all.
- **Statistical significance, not just point estimates**: bootstrap resampling is used to put confidence intervals around Brier scores and around the *difference* between two configurations, rather than trusting a single number. Several tuning attempts that looked like improvements in isolation (e.g. a wider historical-vs-current weighting curve) were tested this way and found to be fitting noise rather than a real, generalizable signal — so they were left at their original values rather than adopted.

## Weight optimization

Early tuning was done by hand-picking one weight at a time (coordinate descent). Later, the gap-combination weights (`W_BASE`, `W_TAC`, `W_H2H`, `W_REL_GD`, `K_SIG`) were jointly optimized via `scipy.optimize` (Nelder-Mead over a softmax-reparametrized simplex, so the four weights are always positive and sum to exactly 1 with no extra constraint needed). Fit exclusively on the training years, checked via leave-one-tournament-out cross-validation, and validated against the untouched holdout — the adopted values improved both train and holdout Brier score, with the holdout improving by more than train did (the opposite of the overfitting signature you'd worry about).

Not every parameter group was worth optimizing this way — with only a few hundred real World Cup matches available in total, a model with a dozen-plus free parameters is genuinely sample-constrained, and some parameter groups showed clear overfitting symptoms (values pinned to their search bounds, in-sample improvement with no holdout benefit) rather than a real signal. Those were deliberately left at their original hand-tuned values.

## Data

- `matches.csv` — every real 2026 World Cup match, group stage through final.
- `h2h_matches.csv` — 10,380 international matches since 1998 across all competitions (not just World Cups), tagged by competition tier and friendly/competitive status.
- `historical_wc.csv` — stage-reached performance across past World Cups.
- `player_ratings.csv` — per-match squad ratings.
- `teams.csv` — FIFA ranking, confederation, tactical style, and host-nation status per team.

## Project structure

```
wc_predictor (1).py          Core model
dixon_coles.py                Alternate model: Dixon-Coles Poisson goal-scoring, toggleable in the frontend
export_predictions.py        Bridges both models to the frontend (predictions.json)
fetch_wc_data.py             Scrapes match/team/ratings data
fetch_h2h_data.py            Scrapes head-to-head history
fetch_intl_ratings.py        Scrapes international player ratings (feeds intl_form)
data/                        CSVs consumed by both models
optimize_*.py, train_*.py,   Weight-tuning / experiment scripts (scipy-based,
  tune_*.py, test_drop_*.py  train/holdout disciplined) — see TUNING.md for what
                              each one found and how to write a new one
bootstrap_ci.py               Confidence intervals on Brier scores and score differences
backtest_dixon_coles.py,      Backtest/capability evaluation for the Dixon-Coles model
  evaluate_dixon_coles_full.py
test_model_invariants.py     Regression tests for bugs found during development
requirements.txt             numpy/scipy — see TUNING.md for which Python interpreter to use
World Cup Prediction Simulator (1)/   React + Vite + Tailwind frontend
```

See **[TUNING.md](TUNING.md)** before starting any new tuning work — it has
the correct Python interpreter to use, the current adopted baseline to beat,
and a table of every experiment already tried (so you don't re-run one
that's already been settled).

## Running it

```bash
# Regenerate predictions after any model/data change
python3 export_predictions.py

# Run the regression test suite
python3 test_model_invariants.py

# Start the frontend
cd "World Cup Prediction Simulator (1)"
npm install
npm run dev
```
