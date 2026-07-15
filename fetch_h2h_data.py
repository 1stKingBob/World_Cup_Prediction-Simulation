#!/usr/bin/env python3.10
"""
H2H Data Collector
==================
Scrapes each requested tournament's teams' full international match history
(ALL competitions — World Cup, qualifiers, continental cups, friendlies —
not just past World Cups) from SofaScore, for real head-to-head records
instead of the World-Cup-only ones in matches.csv (which turned out too
sparse: only 1 of 128 backtested 2018+2022 matches had a qualifying
WC-only H2H pair).

Usage:
    python3.10 fetch_h2h_data.py --since 2020-01-01 --output data/                     # 2026 field only
    python3.10 fetch_h2h_data.py --since 1997-01-01 --years 2002 2006 2010 2014 2018 2022 2026 --output data/

Outputs data/h2h_matches.csv (two rows per match, one per team's
perspective, matching the matches.csv convention):
    date, team, opponent, gd, gf, competition, is_friendly, event_id

Only matches where BOTH teams are in the requested team set are kept —
that's who might actually face each other in a backtested/predicted match,
no point tracking e.g. Argentina vs a team that never appears in our data.
"""

import argparse
import csv
import os
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

BASE = "https://api.sofascore.com/api/v1"
RATE_LIMIT = 1.0

# SofaScore's exact team names differ from ours for some entries — same
# quirks as fetch_wc_data.py's NAME_OVERRIDES.
NAME_OVERRIDES = {
    "United States": "USA",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic",
    "Cabo Verde": "Cape Verde",
    "Türkiye": "Turkey",
    "Congo DR": "DR Congo",
    "Curaçao": "Curacao",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}

# SofaScore's search doesn't fuzzy-match some of our internal names at all
# (returns zero results) — use its own spelling as the query for these.
SEARCH_TERM_OVERRIDES = {
    "Bosnia and Herzegovina": "Bosnia",
    "Turkey": "Turkiye",
    "Ivory Coast": "Cote d'Ivoire",
}

_PAGE = None
_PW = None
_BROWSER = None


def init_browser():
    global _PAGE, _PW, _BROWSER
    print("  Launching browser...")
    _PW = sync_playwright().start()
    _BROWSER = _PW.chromium.launch(headless=True)
    _PAGE = _BROWSER.new_page()
    _PAGE.goto("https://www.sofascore.com/", wait_until="networkidle", timeout=45000)
    time.sleep(2)
    print("  Browser ready.")


def close_browser():
    _BROWSER.close()
    _PW.stop()


def api_get(endpoint, retries=3):
    url = f"{BASE}{endpoint}"
    for attempt in range(retries):
        result = _PAGE.evaluate(f"""
            async () => {{
                try {{
                    const resp = await fetch("{url}");
                    if (!resp.ok) return {{"__status": resp.status}};
                    return await resp.json();
                }} catch(e) {{
                    return {{"__error": e.toString()}};
                }}
            }}
        """)
        if "__status" in result:
            if result["__status"] == 429:
                wait = 5 * (attempt + 1)
                print(f"    Rate limited — waiting {wait}s")
                time.sleep(wait)
                continue
            return None
        if "__error" in result:
            time.sleep(2)
            continue
        return result
    return None


def normalize_name(raw):
    return NAME_OVERRIDES.get(raw, raw)


def resolve_team_id(name):
    """Search SofaScore for `name`, return the id of the best national men's
    senior football team match. SofaScore has duplicate entity records for
    some countries across multiple sports and even multiple football
    entries (stale/reserve records) — the real senior team is reliably the
    one with by far the highest userCount, so pick that instead of trusting
    result order."""
    query = SEARCH_TERM_OVERRIDES.get(name, name)
    data = api_get(f"/search/all?q={query}")
    if not data:
        return None
    candidates = []
    for result in data.get("results", []):
        if result.get("type") != "team":
            continue
        entity = result["entity"]
        if not entity.get("national"):
            continue
        if entity.get("sport", {}).get("slug") != "football":
            continue
        # Skip youth/women's sides that also match on name
        if any(tag in entity.get("name", "") for tag in ["U15", "U16", "U17", "U18", "U19",
                                                          "U20", "U21", "U23", "Women"]):
            continue
        candidates.append(entity)
    if not candidates:
        return None
    best = max(candidates, key=lambda e: e.get("userCount", 0))
    return best["id"], best["name"]


def is_friendly(tournament_name):
    return "friendly" in tournament_name.lower()


def fetch_team_history(team_id, since_ts, team_ids_set, seen_events, match_rows):
    """Paginate a team's past events back to since_ts, keep matches where
    the opponent is also in team_ids_set (someone in the 2026 field)."""
    page_num = 0
    while True:
        time.sleep(RATE_LIMIT)
        data = api_get(f"/team/{team_id}/events/last/{page_num}")
        if not data:
            break
        events = data.get("events", [])
        if not events:
            break

        oldest_ts = min(e.get("startTimestamp", since_ts) for e in events)

        for e in events:
            ts = e.get("startTimestamp")
            if ts is None or ts < since_ts:
                continue
            home = e.get("homeTeam", {})
            away = e.get("awayTeam", {})
            home_score = (e.get("homeScore") or {}).get("current")
            away_score = (e.get("awayScore") or {}).get("current")
            if home_score is None or away_score is None:
                continue  # not played yet
            if home.get("id") not in team_ids_set or away.get("id") not in team_ids_set:
                continue  # opponent isn't in the 2026 field

            eid = e.get("id")
            if eid in seen_events:
                continue
            seen_events.add(eid)

            home_name = normalize_name(home.get("name", ""))
            away_name = normalize_name(away.get("name", ""))
            tournament = e.get("tournament", {}).get("name", "")
            friendly = is_friendly(tournament)
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

            for team, opp, gf, gd in [
                (home_name, away_name, home_score, home_score - away_score),
                (away_name, home_name, away_score, away_score - home_score),
            ]:
                match_rows.append({
                    "date": date_str, "team": team, "opponent": opp,
                    "gd": gd, "gf": gf, "competition": tournament,
                    "is_friendly": int(friendly), "event_id": eid,
                })

        if not data.get("hasNextPage") or oldest_ts < since_ts:
            break
        page_num += 1


def main():
    parser = argparse.ArgumentParser(description="Fetch international H2H match history from SofaScore")
    parser.add_argument("--since", default="2020-01-01", help="Earliest match date to include (YYYY-MM-DD)")
    parser.add_argument("--output", default="data", help="Output directory")
    parser.add_argument("--teams-csv", default=None,
                        help="teams.csv to source team names from (default: <output>/teams.csv)")
    parser.add_argument("--years", nargs="+", type=int, default=[2026],
                        help="Which tournament_year rows in teams.csv to pull team names from "
                             "(e.g. --years 2002 2006 2010 2014 2018 2022 2026 for full backtest coverage)")
    args = parser.parse_args()

    teams_path = args.teams_csv or os.path.join(args.output, "teams.csv")
    years_wanted = set(args.years)
    team_names = []
    seen_names = set()
    with open(teams_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["tournament_year"]) in years_wanted and row["name"] not in seen_names:
                seen_names.add(row["name"])
                team_names.append(row["name"])
    print(f"Resolving SofaScore IDs for {len(team_names)} teams (years {sorted(years_wanted)})...")

    since_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    since_ts = int(since_dt.timestamp())

    init_browser()
    try:
        team_ids = {}
        for name in team_names:
            resolved = resolve_team_id(name)
            time.sleep(RATE_LIMIT)
            if resolved:
                tid, sofa_name = resolved
                team_ids[name] = tid
                print(f"  {name:>24} -> id {tid}  ({sofa_name})")
            else:
                print(f"  {name:>24} -> NOT FOUND")

        team_ids_set = set(team_ids.values())
        seen_events = set()
        match_rows = []

        print(f"\nFetching match history since {args.since}...")
        for name, tid in team_ids.items():
            before = len(seen_events)
            fetch_team_history(tid, since_ts, team_ids_set, seen_events, match_rows)
            print(f"  {name:>24}: +{len(seen_events) - before} new matches")

        out_path = os.path.join(args.output, "h2h_matches.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "date", "team", "opponent", "gd", "gf", "competition", "is_friendly", "event_id"
            ])
            writer.writeheader()
            writer.writerows(match_rows)
        print(f"\nWrote {out_path}: {len(match_rows)} rows ({len(seen_events)} unique matches)")
    finally:
        close_browser()


if __name__ == "__main__":
    main()
