#!/usr/bin/env python3.10
"""
Rebuild data/historical_wc.csv from the already-scraped data/matches.csv,
fixing update_stage()'s group-stage-elimination bug (see fetch_wc_data.py)
without re-scraping anything from SofaScore.

For each (year, team): find their furthest stage reached. "final"/
"third_place" rows are split by gd sign into winner/runner_up and
third_place/fourth_place respectively, matching fetch_wc_data.py's own
knockout-loop logic.
"""

import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

STAGE_ORDER = {
    "group_stage": 0, "round_of_32": 1, "round_of_16": 2, "quarter_final": 3,
    "semi_final": 4, "fourth_place": 5, "third_place": 6,
    "runner_up": 7, "winner": 8,
}
STAGE_POINTS = {
    "winner": 1.00, "runner_up": 0.87, "third_place": 0.75, "fourth_place": 0.62,
    "semi_final": 0.55, "quarter_final": 0.50, "round_of_16": 0.38,
    "round_of_32": 0.31, "group_stage": 0.25,
}


def resolved_stage(row):
    stage = row["stage"]
    gd = int(row["gd"]) if row["gd"] != "" else None
    if stage == "final":
        return "winner" if (gd is not None and gd > 0) else "runner_up"
    if stage == "third_place":
        return "third_place" if (gd is not None and gd > 0) else "fourth_place"
    return stage


def main():
    matches_path = os.path.join(DATA_DIR, "matches.csv")
    with open(matches_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    best = {}  # (year, team) -> (rank, stage_label)
    for row in rows:
        if row["gd"] == "":
            continue  # pending fixture, not a real result
        year = int(row["tournament_year"])
        team = row["team"]
        stage = resolved_stage(row)
        rank = STAGE_ORDER.get(stage, 0)
        key = (year, team)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, stage)

    out_rows = [
        {"tournament_year": year, "team": team, "stage_reached": stage,
         "stage_points": STAGE_POINTS.get(stage, 0.25)}
        for (year, team), (rank, stage) in sorted(best.items())
    ]

    out_path = os.path.join(DATA_DIR, "historical_wc.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["tournament_year", "team", "stage_reached", "stage_points"])
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {out_path}: {len(out_rows)} rows")
    by_year = {}
    for (year, team) in best:
        by_year[year] = by_year.get(year, 0) + 1
    for year in sorted(by_year):
        print(f"  {year}: {by_year[year]} teams")


if __name__ == "__main__":
    main()
