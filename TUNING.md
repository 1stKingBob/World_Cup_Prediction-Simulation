# Tuning & training reference

Everything here exists to make the *next* tuning pass faster than the last
one — both by not re-discovering the same environment gotchas, and by not
re-running an experiment that's already been settled.

## Environment — read this first

`numpy`/`scipy` are **not** on the default `python3` on this machine (Homebrew's).
They're installed under a separate Python 3.10 framework install. Using the
wrong interpreter fails with `ModuleNotFoundError: No module named 'numpy'`
(and, worse, can silently eat a long time if a background job dies on this
before producing any output). Always run tuning/backtest scripts with:

```
/Library/Frameworks/Python.framework/Versions/3.10/bin/python3 <script>.py
```

`requirements.txt` lists the two packages if you ever need to set up a fresh
environment instead.

## The dataset-caching pattern

`evaluate_brier()` re-reads and re-parses every CSV from scratch unless you
hand it a pre-built `dataset`. Every tuning script should call
`load_backtest_dataset(data_dir, years)` **once** for train and once for
holdout (and once per year for CV folds, if used), then pass `dataset=` into
every subsequent `evaluate_brier()` call. Skipping this turns a tuning sweep
that should take seconds into one that re-parses the same CSVs hundreds of
times — this is what keeps a multi-restart Nelder-Mead search fast enough to
actually run interactively rather than needing to be backgrounded for
hours. Every `optimize_*.py`/`backtest_*.py` script here follows this
pattern; copy one as your starting point rather than writing the eval loop
from scratch.

## Current adopted baseline (what to beat)

As of the last tuning pass:

| | train (2002–2018, n=320) | holdout (2022+2026, n=163) |
|---|---|---|
| full model | 0.1662 | 0.1473 |
| rank-only baseline | 0.1772 | 0.1453 |

Note the full model is **not** yet significantly better than the rank-only
baseline on holdout (95% CI on the difference includes zero) — it is
significant on train. This is the honest current state, not a bug to fix
before tuning something else; see `bootstrap_ci.py` for how that
significance check is done, and reuse it for anything new before adopting it.

Adopted config (`wc_predictor (1).py`):
- `USE_INTL_FORM=True`, `WEIGHT_INTL_FORM=0.4395`
- `USE_FIFA_RANK_SIGNAL=True`, `WEIGHT_FIFA_RANK=1.3401`
- `W_BASE=0.641 W_TAC=0.104 W_H2H=0.0 W_REL_GD=0.255 K_SIG=1.037` (H2H
  dropped to 0 — significant improvement, see `test_drop_components.py`)
- `USE_UNIFIED_FORM=False`, `USE_ELO_SEED=False` — both rejected, kept as
  inert/gated code (see below), not deleted, so nobody re-derives them.

## Script inventory — what's already been tried

Rejected ideas are kept, not deleted — re-running a dead end costs more time
than reading why it died.

| Script | What it tests | Verdict |
|---|---|---|
| `optimize_gap_weights.py` | `W_BASE/W_TAC/W_H2H/W_REL_GD/K_SIG` via softmax-reparametrized Nelder-Mead | **Adopted** (current values above) |
| `optimize_h2h_weights.py`, `optimize_relative_gd_weights.py`, `optimize_layer_weights.py` | earlier/narrower weight sweeps | Superseded by `optimize_gap_weights.py` |
| `coordinate_descent_tuning.py` | one-weight-at-a-time hand tuning | Early-stage method, superseded by the joint Nelder-Mead approach |
| `test_drop_components.py`, `test_drop_tactical.py`, `test_drop_tactical_full.py` | ablation: does removing `W_TAC`/`W_H2H` help? | H2H: **dropped** (significant). Tactical: kept (not significant either way) |
| `test_elo_seed.py` | Elo-style fixed-K update instead of the shrinking-average Relative GD formula | **Rejected** — no improvement |
| `train_reduced_corpus.py` | re-tune `W_H2H`/`WEIGHT_INTL_FORM` on a WC-only-weighted subset of the international corpus | **Rejected** — null result |
| `optimize_static_gd_player_perf.py` | retune `WEIGHT_STATIC_GD`/`WEIGHT_PLAYER_PERF` jointly with gap weights | **Rejected** — boundary-hugging (overfit signature) |
| `optimize_unified_form.py` | fold current-tournament matches into `intl_form` (with momentum boost) instead of the separate current-layer blend | **Rejected** — even after reducing to 3 genuinely free params, holdout got significantly worse (overfits train) |
| `tune_form_window.py` | `FORM_MAX_AGE_YEARS`/`FORM_DECAY_POWER` for `intl_form` | Exploratory, not conclusively adopted or rejected |
| `optimize_form_decay.py` | swap `intl_form`'s power-law-with-cutoff decay for exact per-day exponential decay (`FORM_DECAY_XI`, matching `dixon_coles.py`'s own decay on the same real-dated corpus) | **Rejected** — grid search is nearly flat across the whole xi range (train Brier moves <0.0004), the refined optimum pins to the search boundary (classic overfit signature), and holdout improvement (-0.0008) isn't significant (95% CI [-0.0013, +0.0029]) |
| `train_intl_ratings.py` | early scaffolding for the international player-ratings corpus | Superseded by `fetch_intl_ratings.py` + `_compute_intl_form_corpus_partial` in the main model |
| `backtest_dixon_coles.py` | xi (time-decay) sweep for the Dixon-Coles model | **Settled**: `DEFAULT_XI=0.0003` in `dixon_coles.py`, flat/near-optimal across 0.0002–0.0005 |
| `evaluate_dixon_coles_full.py` | 3-class Brier + draw calibration + scoreline output for Dixon-Coles | Reference for its own reported capabilities, not a tuning script |

## Writing a new tuning script

Copy `optimize_gap_weights.py` (small, clean) or `optimize_unified_form.py`
(more recent, shows the "reduce free parameters when the search
boundary-hugs" pattern) as a template. The shape that's proven itself over
every experiment above:

1. Load `train_ds`/`holdout_ds` once via `load_backtest_dataset`.
2. Mutate the module-level constant(s) directly (`wcp.SOME_WEIGHT = x`),
   since `evaluate_brier` reads them fresh on every call — no need to
   rebuild datasets between candidates unless the parameter affects data
   *loading* rather than scoring (e.g. `FORM_MAX_AGE_YEARS` does, most gap
   weights don't).
3. Fit on train only, via `scipy.optimize.minimize(..., method="Nelder-Mead")`
   with **4+ random restarts** — a single-start result that isn't
   reproduced by other starts is usually overfitting, not a real optimum
   (see `optimize_unified_form.py`'s first, rejected 5-parameter version).
4. Check holdout *after* fitting, never during.
5. Run `bootstrap_ci.py`-style paired bootstrap on holdout before calling
   anything "adopted" — several apparent improvements this project found
   turned out to be noise once checked this way.
6. If the search pins parameters to their bounds or different restarts land
   in very different places, that's overfitting — reduce free parameters
   (fix some at a sensible design-intent value) rather than trusting the
   fit.
