"""
Full-capability evaluation of the Dixon-Coles model, beyond the single
half-credit Brier score used to compare it against the custom model:

1. Genuine 3-class Brier score (win/draw/loss each scored against a
   one-hot actual outcome) — tests draw calibration directly, unlike the
   2-outcome half-credit convention used everywhere else in this project.
2. Draw reliability check: bucket matches by predicted draw%, compare
   against the ACTUAL draw rate within each bucket — the real test of
   "when this model says 30% draw, does a draw actually happen ~30% of
   the time?"
3. Scoreline-level output for a handful of real matches — the custom
   model literally cannot produce this (it only ever outputs a single
   win probability); Dixon-Coles' native output is a full scoreline grid.
"""
import csv
import os
from collections import defaultdict
from datetime import date

import dixon_coles as dc
import backtest_dixon_coles as bt

DATA_DIR = "data"
TRAIN_YEARS = bt.TRAIN_YEARS
HOLDOUT_YEARS = bt.HOLDOUT_YEARS
ALL_YEARS = TRAIN_YEARS + HOLDOUT_YEARS


def collect_predictions(years, matches_pool, xi=dc.DEFAULT_XI):
    """One row per real WC match: (team1, team2, actual_outcome, p_a, p_draw, p_b)
    actual_outcome in {"win1","draw","win2"}."""
    rows = []
    for year in years:
        cutoff = bt.tournament_start_date(year)
        model = dc.fit_dixon_coles(matches_pool, cutoff_date=cutoff, xi=xi)
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
                outcome = "win1" if gd > 0 else ("win2" if gd < 0 else "draw")
                p_a, p_draw, p_b = dc.predict_dixon_coles(model, team1, team2)
                rows.append((year, team1, team2, outcome, p_a, p_draw, p_b))
    return rows


def three_way_brier(rows):
    total = 0.0
    for _, _, _, outcome, p_a, p_draw, p_b in rows:
        o_a = 1.0 if outcome == "win1" else 0.0
        o_d = 1.0 if outcome == "draw" else 0.0
        o_b = 1.0 if outcome == "win2" else 0.0
        total += (p_a - o_a) ** 2 + (p_draw - o_d) ** 2 + (p_b - o_b) ** 2
    return total / len(rows)


def draw_calibration(rows, n_buckets=5):
    sorted_rows = sorted(rows, key=lambda r: r[5])  # by p_draw
    n = len(sorted_rows)
    bucket_size = n // n_buckets
    print(f"\n  {'predicted draw%':>18}  {'actual draw rate':>18}  {'n':>5}")
    for i in range(n_buckets):
        start = i * bucket_size
        end = (i + 1) * bucket_size if i < n_buckets - 1 else n
        chunk = sorted_rows[start:end]
        mean_pred = sum(r[5] for r in chunk) / len(chunk)
        actual_rate = sum(1 for r in chunk if r[3] == "draw") / len(chunk)
        print(f"  {mean_pred*100:17.1f}%  {actual_rate*100:17.1f}%  {len(chunk):5d}")


def show_scorelines(matches_pool, examples, cutoff_date, xi=dc.DEFAULT_XI):
    model = dc.fit_dixon_coles(matches_pool, cutoff_date=cutoff_date, xi=xi)
    for team_a, team_b in examples:
        grid, lam_a, lam_b = dc.predict_scoreline_grid(model, team_a, team_b)
        p_a, p_draw, p_b = dc.predict_dixon_coles(model, team_a, team_b)
        print(f"\n  {team_a} (λ={lam_a:.2f}) vs {team_b} (λ={lam_b:.2f})"
              f"   [P(win)={p_a:.3f} draw={p_draw:.3f} P(win)={p_b:.3f}]")
        # top 5 most likely exact scorelines
        flat = [((x, y), grid[x][y]) for x in range(6) for y in range(6)]
        flat.sort(key=lambda t: -t[1])
        for (x, y), p in flat[:5]:
            tag = "  <- draw" if x == y else ""
            print(f"    {team_a} {x}-{y} {team_b}: {p*100:5.1f}%{tag}")


if __name__ == "__main__":
    matches_pool = dc.load_international_matches(DATA_DIR)

    print("=== 3-class Brier score (win/draw/loss, one-hot) ===")
    for label, years in [("TRAIN", TRAIN_YEARS), ("HOLDOUT", HOLDOUT_YEARS), ("ALL", ALL_YEARS)]:
        rows = collect_predictions(years, matches_pool)
        bs = three_way_brier(rows)
        print(f"  {label}: 3-class Brier = {bs:.4f}  (n={len(rows)})")
        # for reference: a "3-class Brier" ranges 0 (perfect) to 2 (maximally
        # wrong); always predicting the base rate [0.46, 0.24, 0.30] scores:
        base_rate = [
            sum(1 for r in rows if r[3] == "win1") / len(rows),
            sum(1 for r in rows if r[3] == "draw") / len(rows),
            sum(1 for r in rows if r[3] == "win2") / len(rows),
        ]
        naive_bs = sum(
            (base_rate[0] - (1.0 if r[3] == "win1" else 0.0)) ** 2 +
            (base_rate[1] - (1.0 if r[3] == "draw" else 0.0)) ** 2 +
            (base_rate[2] - (1.0 if r[3] == "win2" else 0.0)) ** 2
            for r in rows
        ) / len(rows)
        print(f"    (naive base-rate baseline {base_rate}: {naive_bs:.4f})")

    print("\n=== Draw calibration (ALL years, 5 buckets by predicted draw%) ===")
    rows_all = collect_predictions(ALL_YEARS, matches_pool)
    draw_calibration(rows_all)

    print("\n\n=== Scoreline-level predictions (native model output) ===")
    show_scorelines(matches_pool,
                    [("Spain", "Argentina"), ("France", "England"), ("Germany", "Paraguay")],
                    cutoff_date=date(2026, 7, 19))
