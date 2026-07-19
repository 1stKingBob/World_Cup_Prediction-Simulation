"""
Backtest the Dixon-Coles model against the same WC train/holdout years and
Brier convention used throughout this project, as a sanity check before
wiring it into the app — and to see whether its default xi (time-decay) is
remotely reasonable before trusting it.

Fits ONE Dixon-Coles snapshot per WC year, using only real international
matches strictly before that tournament's own real start date (derived from
h2h_matches.csv's dates for that year's group-stage event_ids) — the same
year-level granularity intl_form already uses elsewhere in this project, for
the same reason: computationally cheap, and no lookahead across that WC's
own timeline. Every match within that WC year is then scored using that one
frozen snapshot.
"""
import csv
import os
from datetime import date, timedelta

import numpy as np

import dixon_coles as dc

DATA_DIR = "data"
TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]


def tournament_start_date(year):
    """Earliest real date among that year's real WC group-stage matches,
    cross-referenced from matches.csv (event_id, stage, tournament_year)
    into h2h_matches.csv (event_id -> date)."""
    event_dates = {}
    with open(os.path.join(DATA_DIR, "h2h_matches.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            event_dates[row["event_id"]] = row["date"]

    min_date = None
    with open(os.path.join(DATA_DIR, "matches.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["tournament_year"] != str(year) or row["stage"] != "group_stage":
                continue
            d = event_dates.get(row["event_id"])
            if d and (min_date is None or d < min_date):
                min_date = d
    if min_date is None:
        raise ValueError(f"No group-stage dates found for {year}")
    return dc._parse_date(min_date)


def brier_for_year(year, matches_pool, xi):
    cutoff = tournament_start_date(year)
    model = dc.fit_dixon_coles(matches_pool, cutoff_date=cutoff, xi=xi)

    total_sq_error = 0.0
    n = 0
    seen = set()
    with open(os.path.join(DATA_DIR, "matches.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["tournament_year"] != str(year) or row["gd"] == "":
                continue
            eid = row["event_id"]
            if eid in seen:
                continue
            seen.add(eid)
            team1, team2 = row["team"], row["opponent"]
            gd = int(row["gd"])
            actual = 1.0 if gd > 0 else (0.0 if gd < 0 else 0.5)
            p_a, p_draw, p_b = dc.predict_dixon_coles(model, team1, team2)
            predicted = p_a + 0.5 * p_draw
            total_sq_error += (predicted - actual) ** 2
            n += 1
    return total_sq_error, n, cutoff, model["n_matches"]


def run(xi):
    matches_pool = dc.load_international_matches(DATA_DIR)
    print(f"\n=== xi={xi} ===")
    for label, years in [("TRAIN", TRAIN_YEARS), ("HOLDOUT", HOLDOUT_YEARS)]:
        total_err, total_n = 0.0, 0
        for year in years:
            err, n, cutoff, n_train = brier_for_year(year, matches_pool, xi)
            total_err += err
            total_n += n
            print(f"  {year}: cutoff={cutoff} train_matches={n_train} n_scored={n} brier={err/n:.4f}")
        print(f"  {label} overall: brier={total_err/total_n:.4f}  (n={total_n})")


if __name__ == "__main__":
    for xi in [0.0005, 0.0018, 0.005]:
        run(xi)
