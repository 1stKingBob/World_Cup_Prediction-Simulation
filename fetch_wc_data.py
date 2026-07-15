#!/usr/bin/env python3.10
"""
World Cup Data Collector
========================
Scrapes match results and player ratings from SofaScore for past World Cups.
Outputs CSV files consumed by wc_predictor.py.

Usage:
    python3.10 fetch_wc_data.py --years 2018 2022 --output data/
    python3.10 fetch_wc_data.py --years 2026 --output data/

Outputs (appended across runs, so clear data/ before re-fetching a year):
    matches.csv         — per-team match results (two rows per match)
    player_ratings.csv  — per-player per-match SofaScore ratings
    teams.csv           — team metadata per tournament
    historical_wc.csv   — stage reached per team per WC (used to compute historical_score)
"""

import csv
import time
import os
import argparse
from playwright.sync_api import sync_playwright

# =============================================================================
# SOFASCORE API
# =============================================================================

BASE = "https://api.sofascore.com/api/v1"
RATE_LIMIT = 1.2           # seconds between requests
WC_TOURNAMENT_ID = 16      # FIFA World Cup unique-tournament ID on SofaScore

# Known season IDs (from the seasons endpoint — stored to skip discovery)
KNOWN_SEASON_IDS = {
    1990: 17570,
    1994: 17571,
    1998: 1151,
    2002: 2636,
    2006: 16,
    2010: 2531,
    2014: 7528,
    2018: 15586,
    2022: 41087,
    2026: 58210,
}

# Active Playwright page — all API calls go through here so auth is automatic
_PAGE = None


def init_browser():
    """Launch a headless browser, navigate to SofaScore so Cloudflare clears,
    and store the page globally for all subsequent API calls."""
    global _PAGE, _PW, _BROWSER
    print("  Launching browser...")
    _PW      = sync_playwright().start()
    _BROWSER = _PW.chromium.launch(headless=True)
    _PAGE    = _BROWSER.new_page()
    _PAGE.goto("https://www.sofascore.com/", wait_until="networkidle", timeout=30000)
    time.sleep(2)
    print("  Browser ready.")


def close_browser():
    _BROWSER.close()
    _PW.stop()


def api_get(endpoint, retries=3):
    """Fetch a SofaScore API endpoint from inside the browser context."""
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
            print(f"    HTTP {result['__status']}: {endpoint}")
            if result["__status"] == 429:
                wait = 5 * (attempt + 1)
                print(f"    Rate limited — waiting {wait}s")
                time.sleep(wait)
            else:
                return None
        elif "__error" in result:
            print(f"    Fetch error: {result['__error']}")
            time.sleep(2)
        else:
            return result
    return None


# =============================================================================
# STATIC REFERENCE DATA
# =============================================================================

CONFEDERATIONS = {
    # UEFA
    "Germany": "UEFA", "France": "UEFA", "Spain": "UEFA", "Portugal": "UEFA",
    "England": "UEFA", "Netherlands": "UEFA", "Belgium": "UEFA", "Croatia": "UEFA",
    "Denmark": "UEFA", "Switzerland": "UEFA", "Serbia": "UEFA", "Poland": "UEFA",
    "Wales": "UEFA", "Austria": "UEFA", "Sweden": "UEFA", "Slovakia": "UEFA",
    "Hungary": "UEFA", "Ukraine": "UEFA", "Slovenia": "UEFA", "Albania": "UEFA",
    "Turkey": "UEFA", "Greece": "UEFA", "Romania": "UEFA", "Iceland": "UEFA",
    "Russia": "UEFA", "Bosnia and Herzegovina": "UEFA", "North Macedonia": "UEFA",
    "Czech Republic": "UEFA", "Norway": "UEFA", "Scotland": "UEFA",
    "Ireland": "UEFA",
    # CONMEBOL
    "Brazil": "CONMEBOL", "Argentina": "CONMEBOL", "Uruguay": "CONMEBOL",
    "Colombia": "CONMEBOL", "Chile": "CONMEBOL", "Peru": "CONMEBOL",
    "Ecuador": "CONMEBOL", "Paraguay": "CONMEBOL",
    # CONCACAF
    "USA": "CONCACAF", "Mexico": "CONCACAF", "Canada": "CONCACAF",
    "Costa Rica": "CONCACAF", "Honduras": "CONCACAF", "Panama": "CONCACAF",
    "El Salvador": "CONCACAF", "Jamaica": "CONCACAF", "Curacao": "CONCACAF",
    "Haiti": "CONCACAF", "Trinidad and Tobago": "CONCACAF",
    # AFC
    "Japan": "AFC", "South Korea": "AFC", "Australia": "AFC", "Iran": "AFC",
    "Saudi Arabia": "AFC", "Qatar": "AFC", "UAE": "AFC", "Iraq": "AFC",
    "China": "AFC", "Jordan": "AFC", "North Korea": "AFC", "Uzbekistan": "AFC",
    # CAF
    "Morocco": "CAF", "Senegal": "CAF", "Nigeria": "CAF", "Ghana": "CAF",
    "Cameroon": "CAF", "Ivory Coast": "CAF", "Tunisia": "CAF", "Algeria": "CAF",
    "Egypt": "CAF", "South Africa": "CAF", "DR Congo": "CAF", "Mali": "CAF",
    "Cape Verde": "CAF", "Togo": "CAF", "Angola": "CAF",
    # OFC
    "New Zealand": "OFC",
}

# FIFA Rankings at tournament start date (last published ranking before each WC)
FIFA_RANKINGS = {
    # 17 Oct 2001 (last published ranking before the 2002 WC)
    2002: {
        "Argentina": 3, "Belgium": 33, "Brazil": 2, "Cameroon": 38,
        "China": 55, "Costa Rica": 29, "Croatia": 16, "Denmark": 17,
        "Ecuador": 39, "England": 9, "France": 1, "Germany": 14,
        "Ireland": 20, "Italy": 4, "Japan": 26, "Mexico": 11,
        "Nigeria": 42, "Paraguay": 13, "Poland": 28, "Portugal": 5,
        "Russia": 21, "Saudi Arabia": 30, "Senegal": 65, "Slovenia": 27,
        "South Africa": 32, "South Korea": 43, "Spain": 6, "Sweden": 18,
        "Tunisia": 25, "Turkey": 34, "USA": 19, "Uruguay": 23,
    },
    # 17 May 2006 (last published ranking before the 2006 WC)
    2006: {
        "Brazil": 1, "Czech Republic": 2, "Netherlands": 3, "Mexico": 4,
        "USA": 5, "Spain": 6, "Portugal": 7, "France": 8, "Argentina": 9,
        "England": 10, "Italy": 13, "Japan": 18, "Germany": 19, "Iran": 23,
        "Croatia": 24, "Costa Rica": 26, "Poland": 29, "South Korea": 30,
        "Ivory Coast": 32, "Paraguay": 33, "Saudi Arabia": 34, "Switzerland": 35,
        "Ecuador": 39, "Serbia": 44, "Ukraine": 45,
        "Trinidad and Tobago": 47, "Ghana": 48, "Sweden": 56, "Angola": 59,
        "Togo": 61, "Tunisia": 62, "Australia": 69,
    },
    2022: {
        "Brazil": 1, "Belgium": 2, "Argentina": 3, "France": 4, "England": 5,
        "Spain": 6, "Portugal": 7, "Netherlands": 8, "Denmark": 10, "Germany": 11,
        "Mexico": 13, "USA": 14, "Uruguay": 14, "Croatia": 15, "Switzerland": 15,
        "Iran": 20, "Morocco": 22, "Japan": 24, "Poland": 26, "Australia": 38,
        "South Korea": 28, "Serbia": 21, "Senegal": 18, "Wales": 19,
        "Canada": 41, "Cameroon": 43, "Ecuador": 44, "Qatar": 51,
        "Saudi Arabia": 51, "Ghana": 60, "Tunisia": 30, "Costa Rica": 31,
    },
    2018: {
        "Germany": 1, "Brazil": 2, "Belgium": 3, "Portugal": 4, "Argentina": 5,
        "Switzerland": 6, "France": 7, "Poland": 8, "Chile": 9, "Spain": 10,
        "Peru": 11, "Denmark": 12, "England": 13, "Mexico": 15, "Colombia": 16,
        "Uruguay": 17, "Croatia": 18, "Iceland": 22, "Costa Rica": 23,
        "Sweden": 24, "Senegal": 27, "Tunsia": 28, "Iran": 37, "Egypt": 45,
        "Morocco": 42, "Japan": 61, "South Korea": 62, "Nigeria": 48,
        "Serbia": 38, "Russia": 66, "Saudi Arabia": 67, "Australia": 40,
        "Panama": 55,
    },
    2010: {
        "Spain": 1, "Brazil": 2, "Netherlands": 3, "Italy": 4, "Germany": 5,
        "Argentina": 6, "England": 7, "Portugal": 8, "France": 9, "Chile": 16,
        "USA": 14, "Mexico": 17, "Uruguay": 18, "Greece": 12, "Serbia": 15,
        "Ghana": 33, "Australia": 20, "Denmark": 26, "Japan": 45,
        "Cameroon": 19, "Slovakia": 37, "Paraguay": 30, "New Zealand": 78,
        "Nigeria": 21, "South Korea": 47, "Algeria": 28, "Slovenia": 25,
        "Honduras": 38, "Ivory Coast": 25, "North Korea": 105,
        "Switzerland": 22, "South Africa": 83,
    },
    2014: {
        "Spain": 1, "Germany": 2, "Argentina": 3, "Colombia": 4, "Belgium": 5,
        "Uruguay": 6, "Switzerland": 7, "Italy": 8, "Netherlands": 9, "Chile": 11,
        "Brazil": 10, "England": 10, "Portugal": 4, "France": 17, "Greece": 12,
        "USA": 14, "Ecuador": 22, "Costa Rica": 28, "Algeria": 25, "Ivory Coast": 18,
        "Japan": 46, "South Korea": 57, "Ghana": 37, "Nigeria": 44,
        "Bosnia and Herzegovina": 16, "Cameroon": 56, "Mexico": 20,
        "Croatia": 19, "Iran": 43, "Honduras": 33, "Russia": 19, "Australia": 59,
    },
    # Live FIFA ranking as of 12 July 2026 (scraped mid-tournament from
    # inside.fifa.com — the official pre-tournament 11 June snapshot wasn't
    # reachable through the site's filter UI, so this reflects in-progress
    # movement for teams still alive in the tournament).
    2026: {
        "France": 1, "Spain": 2, "Argentina": 3, "England": 4, "Brazil": 5,
        "Morocco": 6, "Portugal": 7, "Belgium": 8, "Netherlands": 9, "Mexico": 10,
        "Colombia": 11, "Germany": 12, "Croatia": 13, "Switzerland": 14,
        "USA": 16, "Japan": 17, "Norway": 18, "Senegal": 19, "Uruguay": 20,
        "Iran": 22, "Austria": 23, "Egypt": 24, "Ecuador": 25, "Turkey": 27,
        "Australia": 28, "Algeria": 29, "Canada": 30, "Ivory Coast": 31,
        "South Korea": 32, "Paraguay": 34, "Sweden": 37, "DR Congo": 41,
        "Scotland": 42, "Panama": 44, "Czech Republic": 48, "South Africa": 54,
        "Tunisia": 57, "Saudi Arabia": 58, "Qatar": 59, "Uzbekistan": 60,
        "Bosnia and Herzegovina": 61, "Iraq": 63, "Cape Verde": 64, "Ghana": 65,
        "Jordan": 73, "Curacao": 82, "New Zealand": 86, "Haiti": 88,
    },
}

HOST_NATIONS = {
    2002: {"South Korea", "Japan"},
    2006: {"Germany"},
    2010: {"South Africa"},
    2014: {"Brazil"},
    2018: {"Russia"},
    2022: {"Qatar"},
    2026: {"USA", "Mexico", "Canada"},
}

# Tactical style assignments per tournament (manual — Phase 4)
STYLES = {
    2002: {
        "Argentina": "possession", "Belgium": "counter", "Brazil": "possession",
        "Cameroon": "direct", "China": "low_block", "Costa Rica": "counter",
        "Croatia": "counter", "Denmark": "direct", "Ecuador": "low_block",
        "England": "direct", "France": "possession", "Germany": "high_press",
        "Ireland": "direct", "Italy": "low_block", "Japan": "possession",
        "Mexico": "counter", "Nigeria": "direct", "Paraguay": "low_block",
        "Poland": "direct", "Portugal": "possession", "Russia": "direct",
        "Saudi Arabia": "low_block", "Senegal": "direct", "Slovenia": "low_block",
        "South Africa": "direct", "South Korea": "high_press", "Spain": "possession",
        "Sweden": "direct", "Tunisia": "low_block", "Turkey": "counter",
        "USA": "high_press", "Uruguay": "low_block",
    },
    2006: {
        "Angola": "low_block", "Argentina": "possession", "Australia": "direct",
        "Brazil": "possession", "Costa Rica": "low_block", "Croatia": "counter",
        "Czech Republic": "direct", "Ivory Coast": "direct", "Ecuador": "low_block",
        "England": "direct", "France": "counter", "Germany": "high_press",
        "Ghana": "counter", "Iran": "low_block", "Italy": "low_block",
        "Japan": "possession", "Mexico": "counter", "Netherlands": "possession",
        "Paraguay": "low_block", "Poland": "direct", "Portugal": "possession",
        "Saudi Arabia": "low_block", "Serbia": "direct",
        "South Korea": "high_press", "Spain": "possession", "Sweden": "direct",
        "Switzerland": "low_block", "Togo": "direct", "Trinidad and Tobago": "low_block",
        "Tunisia": "low_block", "USA": "high_press", "Ukraine": "direct",
    },
    2022: {
        "Brazil": "possession", "Argentina": "possession", "France": "counter",
        "Germany": "high_press", "Spain": "possession", "England": "high_press",
        "Portugal": "possession", "Netherlands": "direct", "Belgium": "counter",
        "Uruguay": "low_block", "Mexico": "low_block", "USA": "high_press",
        "Japan": "high_press", "South Korea": "high_press", "Croatia": "low_block",
        "Denmark": "direct", "Switzerland": "low_block", "Morocco": "low_block",
        "Senegal": "direct", "Poland": "low_block", "Australia": "direct",
        "Canada": "high_press", "Qatar": "possession", "Saudi Arabia": "counter",
        "Iran": "low_block", "Serbia": "direct", "Ecuador": "counter",
        "Wales": "low_block", "Cameroon": "counter", "Ghana": "counter",
        "Tunisia": "low_block", "Costa Rica": "low_block",
    },
    2018: {
        "France": "counter", "Croatia": "counter", "Belgium": "high_press",
        "England": "direct", "Brazil": "possession", "Uruguay": "low_block",
        "Russia": "low_block", "Sweden": "direct", "Argentina": "possession",
        "Portugal": "counter", "Spain": "possession", "Germany": "high_press",
        "Mexico": "counter", "Japan": "low_block", "Colombia": "counter",
        "Switzerland": "low_block", "Denmark": "low_block", "Senegal": "direct",
        "South Korea": "high_press", "Iran": "low_block", "Nigeria": "direct",
        "Egypt": "counter", "Morocco": "low_block", "Costa Rica": "low_block",
        "Tunisia": "low_block", "Saudi Arabia": "counter", "Panama": "low_block",
        "Iceland": "direct", "Australia": "direct", "Peru": "possession",
        "Poland": "direct", "Serbia": "direct",
    },
    2010: {
        "Spain": "possession", "Brazil": "possession", "Netherlands": "counter",
        "Germany": "high_press", "Argentina": "possession", "England": "direct",
        "Portugal": "counter", "France": "counter", "Italy": "low_block",
        "Uruguay": "low_block", "Chile": "high_press", "USA": "high_press",
        "Mexico": "counter", "Greece": "low_block", "Serbia": "direct",
        "Ghana": "direct", "Australia": "direct", "Denmark": "direct",
        "Japan": "possession", "Cameroon": "direct", "Slovakia": "counter",
        "Paraguay": "low_block", "New Zealand": "direct", "Nigeria": "direct",
        "South Korea": "high_press", "Algeria": "low_block", "Slovenia": "low_block",
        "Honduras": "low_block", "Ivory Coast": "direct", "North Korea": "low_block",
        "Switzerland": "low_block", "South Africa": "direct",
    },
    2014: {
        "Germany": "high_press", "Argentina": "possession", "Netherlands": "direct",
        "Brazil": "possession", "France": "counter", "Colombia": "counter",
        "Belgium": "high_press", "Costa Rica": "low_block", "Algeria": "counter",
        "Switzerland": "low_block", "USA": "high_press", "Chile": "high_press",
        "Mexico": "low_block", "Greece": "low_block", "Uruguay": "low_block",
        "Nigeria": "direct", "Spain": "possession", "Italy": "counter",
        "Croatia": "counter", "Ivory Coast": "direct", "England": "direct",
        "Ecuador": "counter", "Honduras": "low_block", "Japan": "high_press",
        "South Korea": "high_press", "Bosnia and Herzegovina": "direct",
        "Iran": "low_block", "Ghana": "direct", "Cameroon": "direct",
        "Russia": "low_block", "Australia": "direct", "Portugal": "counter",
    },
    # Manual archetype assignment for the 2026 field (Phase 4 — not yet
    # stat-derived; best-effort judgment based on known team identities).
    2026: {
        "France": "counter", "Spain": "possession", "Argentina": "possession",
        "England": "high_press", "Brazil": "possession", "Morocco": "low_block",
        "Portugal": "possession", "Belgium": "counter", "Netherlands": "direct",
        "Mexico": "counter", "Colombia": "counter", "Germany": "high_press",
        "Croatia": "possession", "Switzerland": "low_block", "USA": "high_press",
        "Japan": "high_press", "Norway": "direct", "Senegal": "direct",
        "Uruguay": "low_block", "Iran": "low_block", "Austria": "high_press",
        "Egypt": "low_block", "Ecuador": "counter", "Turkey": "counter",
        "Australia": "direct", "Algeria": "low_block", "Canada": "counter",
        "Ivory Coast": "direct", "South Korea": "high_press", "Paraguay": "low_block",
        "Sweden": "direct", "DR Congo": "direct", "Scotland": "direct",
        "Panama": "low_block", "Czech Republic": "direct", "South Africa": "direct",
        "Tunisia": "low_block", "Saudi Arabia": "low_block", "Qatar": "possession",
        "Uzbekistan": "low_block", "Bosnia and Herzegovina": "direct", "Iraq": "low_block",
        "Cape Verde": "low_block", "Ghana": "direct", "Jordan": "low_block",
        "Curacao": "low_block", "New Zealand": "direct", "Haiti": "direct",
    },
}

# Stage → points mapping for computing historical_score (0–1 scale)
STAGE_POINTS = {
    "winner":        1.00,
    "runner_up":     0.87,
    "third_place":   0.75,
    "fourth_place":  0.62,
    "semi_final":    0.55,
    "quarter_final": 0.50,
    "round_of_16":   0.38,
    "round_of_32":   0.31,   # new in 2026 (48-team format)
    "group_stage":   0.25,
}

# SofaScore team name overrides → standard names used in this project
NAME_OVERRIDES = {
    "United States": "USA",
    "Korea Republic": "South Korea",
    "DPR Korea": "North Korea",
    "Korea DPR": "North Korea",
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic",
    "Cabo Verde": "Cape Verde",
    "Türkiye": "Turkey",
    "Congo DR": "DR Congo",
    "Curaçao": "Curacao",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    # SofaScore has no separate historical entity for the pre-2006-split
    # nation — its 2006 WC events resolve to the same team ID as modern
    # "Serbia", so treat them as one to keep teams.csv/matches.csv/
    # h2h_matches.csv lookups consistent.
    "Serbia & Montenegro": "Serbia",
}


def discover_season_id(year):
    if year in KNOWN_SEASON_IDS:
        return KNOWN_SEASON_IDS[year]
    print(f"  Discovering season ID for {year}...")
    data = api_get(f"/unique-tournament/{WC_TOURNAMENT_ID}/seasons")
    if not data:
        return None
    for season in data.get("seasons", []):
        if str(year) in season.get("name", ""):
            sid = season["id"]
            print(f"  Found season ID {sid} for {year}")
            return sid
    print(f"  Could not find season ID for {year}")
    return None


def get_group_rounds(season_id):
    """Return unique group-stage round numbers (unnamed rounds only, deduped)."""
    data = api_get(f"/unique-tournament/{WC_TOURNAMENT_ID}/season/{season_id}/rounds")
    if not data:
        return []
    seen = set()
    result = []
    for r in data.get("rounds", []):
        n = r["round"]
        if not r.get("name") and n not in seen:   # unnamed = group stage
            seen.add(n)
            result.append(n)
    return sorted(result)


def get_round_events(season_id, round_num):
    time.sleep(RATE_LIMIT)
    data = api_get(
        f"/unique-tournament/{WC_TOURNAMENT_ID}/season/{season_id}/events/round/{round_num}"
    )
    if not data:
        return []
    return data.get("events", [])


def get_event_by_id(event_id):
    time.sleep(RATE_LIMIT)
    data = api_get(f"/event/{event_id}")
    if not data:
        return None
    return data.get("event", data)   # /event/{id} wraps in "event" key


def get_lineups(event_id):
    time.sleep(RATE_LIMIT)
    return api_get(f"/event/{event_id}/lineups")


def get_cuptree_knockout_events(season_id):
    """
    Return list of (event_id, stage_label) for all knockout matches
    found in the season's cup bracket.
    """
    data = api_get(f"/unique-tournament/{WC_TOURNAMENT_ID}/season/{season_id}/cuptrees")
    if not data:
        return []

    STAGE_FROM_DESC = {
        "Round of 32": "round_of_32",   # new in 2026 (48-team format)
        "1/16":        "round_of_32",
        "Round of 16": "round_of_16",
        "1/8":         "round_of_16",   # used in 2010/2014
        "Quarterfinal":  "quarter_final",
        "Quarterfinals": "quarter_final",
        "Semifinal":  "semi_final",
        "Semifinals": "semi_final",
        # "Final" is handled specially — contains both final + 3rd-place
    }

    result = []
    for tree in data.get("cupTrees", []):
        for rnd in tree.get("rounds", []):
            desc  = rnd.get("description", "")
            stage = STAGE_FROM_DESC.get(desc, "FINAL_ROUND")
            for block in rnd.get("blocks", []):
                for eid in block.get("events", []):
                    result.append((int(eid), stage))
    return result


# =============================================================================
# DATA EXTRACTION
# =============================================================================

def normalize_name(raw):
    return NAME_OVERRIDES.get(raw, raw)



def extract_group(event):
    name = event.get("tournament", {}).get("name", "")
    if "Group" in name:
        part = name.split("Group")[-1].strip()
        return part[0] if part else ""
    return ""


STAGE_ORDER = {
    "group_stage": 0, "round_of_32": 1, "round_of_16": 2, "quarter_final": 3,
    "semi_final": 4, "fourth_place": 5, "third_place": 6,
    "runner_up": 7, "winner": 8,
}

# How to determine final vs 3rd-place from event roundInfo slug/name
_THIRD_PLACE_HINTS = {"3rd", "third", "place", "bronze"}


def _play_score(score_dict):
    """Goals from open play + ET, excluding penalty shootout goals."""
    if not score_dict:
        return None
    current = score_dict.get("current")
    if current is None:
        return None
    pens = int(score_dict.get("penalties") or 0)
    return int(current) - pens


def _is_third_place_event(event):
    ri = event.get("roundInfo") or {}
    slug = ri.get("slug", "").lower()
    name = ri.get("name", "").lower()
    return any(h in slug or h in name for h in _THIRD_PLACE_HINTS)


def _add_ratings(rating_rows, lineups, year, event_id, round_num, stage,
                 home_name, away_name):
    """Append player rating rows from lineups data."""
    if not lineups:
        return
    for side, team_name in [("home", home_name), ("away", away_name)]:
        for p in lineups.get(side, {}).get("players", []):
            player = p.get("player", {})
            stats  = p.get("statistics", {})
            rating = stats.get("rating")
            if rating is None:
                continue
            try:
                rating = float(rating)
            except (ValueError, TypeError):
                continue
            rating_rows.append({
                "tournament_year": year,
                "event_id":        event_id,
                "round_num":       round_num,
                "stage":           stage,
                "team":            team_name,
                "player_name":     player.get("name", ""),
                "sofascore_id":    player.get("id", ""),
                "rating":          round(rating, 2),
                "minutes_played":  stats.get("minutesPlayed", 0),
            })


def fetch_year(year, output_dir, skip_ratings=False):
    """skip_ratings: for tournaments only needed for historical_wc.csv
    (stage-reached, used by the model's historical_score component further
    up the chain — e.g. 1990/1994/1998 feeding a 2002 backtest) there's no
    need to fetch per-match lineups/ratings at all, which is most of the
    API-call volume. Still writes matches.csv/teams.csv normally, just
    skips player_ratings.csv rows for this year."""
    print(f"\n{'='*55}")
    print(f"  Fetching WC {year}" + ("  [history-only, no ratings]" if skip_ratings else ""))
    print(f"{'='*55}")

    season_id = discover_season_id(year)
    if not season_id:
        print(f"  Skipping {year} — no season ID found.")
        return

    rankings = FIFA_RANKINGS.get(year, {})
    styles   = STYLES.get(year, {})
    hosts    = HOST_NATIONS.get(year, set())

    match_rows      = []
    rating_rows     = []
    team_info       = {}
    team_best_stage = {}   # team -> (stage_order, stage_label)

    def update_stage(team, stage):
        # group_stage has STAGE_ORDER rank 0, same as the "no entry yet"
        # floor used to have — that made `new > cur` false for every team
        # eliminated in the group stage, silently dropping them from
        # historical_wc.csv entirely (only Round-of-16+ teams ever got
        # recorded). -1 floor fixes it: 0 > -1 is true.
        cur = team_best_stage.get(team, (-1, "group_stage"))[0]
        new = STAGE_ORDER.get(stage, 0)
        if new > cur:
            team_best_stage[team] = (new, stage)

    def register_team(name, rank, conf):
        if name not in team_info:
            team_info[name] = {
                "tournament_year": year, "name": name,
                "confederation": conf, "raw_rank": rank,
                "is_host":  1 if name in hosts else 0,
                "style":    styles.get(name, "possession"),
                "squad_size": 26,
            }

    def append_match_rows(event_id, round_num, stage, group,
                          home_name, away_name, home_score, away_score):
        home_rank = rankings.get(home_name, 50)
        away_rank = rankings.get(away_name, 50)
        home_conf = CONFEDERATIONS.get(home_name, "UEFA")
        away_conf = CONFEDERATIONS.get(away_name, "UEFA")
        for team, opp, gd, gf, opp_rank, opp_conf in [
            (home_name, away_name, home_score - away_score, home_score, away_rank, away_conf),
            (away_name, home_name, away_score - home_score, away_score, home_rank, home_conf),
        ]:
            match_rows.append({
                "tournament_year":  year,
                "round_num":        round_num,
                "stage":            stage,
                "group":            group,
                "event_id":         event_id,
                "team":             team,
                "opponent":         opp,
                "gd":               gd,
                "gf":               gf,
                "opponent_raw_rank": opp_rank,
                "opponent_conf":    opp_conf,
            })
        register_team(home_name, rankings.get(home_name, 50),
                      CONFEDERATIONS.get(home_name, "UEFA"))
        register_team(away_name, rankings.get(away_name, 50),
                      CONFEDERATIONS.get(away_name, "UEFA"))

    def append_pending_fixture_rows(event_id, round_num, stage, group,
                                    home_name, away_name):
        """Record a not-yet-played fixture (real, known teams only — skips
        bracket placeholders like 'Winner of Match 99') with blank gd/gf so
        downstream consumers can still see who's playing whom next."""
        if home_name not in rankings or away_name not in rankings:
            return
        home_conf = CONFEDERATIONS.get(home_name, "UEFA")
        away_conf = CONFEDERATIONS.get(away_name, "UEFA")
        for team, opp, opp_rank, opp_conf in [
            (home_name, away_name, rankings.get(away_name, 50), away_conf),
            (away_name, home_name, rankings.get(home_name, 50), home_conf),
        ]:
            match_rows.append({
                "tournament_year":  year,
                "round_num":        round_num,
                "stage":            stage,
                "group":            group,
                "event_id":         event_id,
                "team":             team,
                "opponent":         opp,
                "gd":               "",
                "gf":               "",
                "opponent_raw_rank": opp_rank,
                "opponent_conf":    opp_conf,
            })

    # ------------------------------------------------------------------ #
    # PHASE 1 — Group stage (unnamed rounds, deduped)                     #
    # ------------------------------------------------------------------ #
    group_rounds = get_group_rounds(season_id)
    print(f"  Group-stage rounds: {group_rounds}")

    for round_num in group_rounds:
        print(f"\n  Round {round_num}  [group_stage]")
        events = get_round_events(season_id, round_num)
        if not events:
            print(f"    (no events)")
            continue

        for event in events:
            event_id  = event["id"]
            home_name = normalize_name(event["homeTeam"]["name"])
            away_name = normalize_name(event["awayTeam"]["name"])
            home_score = (event.get("homeScore") or {}).get("current")
            away_score = (event.get("awayScore") or {}).get("current")
            if home_score is None or away_score is None:
                print(f"    {home_name} vs {away_name}  (no score yet, skipping)")
                continue

            home_score = int(home_score)
            away_score = int(away_score)
            group = extract_group(event)
            print(f"    [{event_id}] {home_name} {home_score}–{away_score} {away_name}")

            append_match_rows(event_id, round_num, "group_stage", group,
                              home_name, away_name, home_score, away_score)
            update_stage(home_name, "group_stage")
            update_stage(away_name, "group_stage")

            if not skip_ratings:
                lineups = get_lineups(event_id)
                _add_ratings(rating_rows, lineups, year, event_id, round_num,
                             "group_stage", home_name, away_name)

    # ------------------------------------------------------------------ #
    # PHASE 2 — Knockout stage (from cup bracket)                         #
    # ------------------------------------------------------------------ #
    knockout_events = get_cuptree_knockout_events(season_id)
    if knockout_events:
        print(f"\n  Knockout events: {len(knockout_events)} matches found in bracket")
    else:
        print(f"\n  No knockout bracket found for season {season_id}")

    seen_event_ids = set()
    for event_id, stage_default in knockout_events:
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)

        event = get_event_by_id(event_id)
        if not event:
            continue

        home_name  = normalize_name(event["homeTeam"]["name"])
        away_name  = normalize_name(event["awayTeam"]["name"])
        home_score = _play_score(event.get("homeScore"))
        away_score = _play_score(event.get("awayScore"))
        round_num = (event.get("roundInfo") or {}).get("round", 0)
        if home_score is None or away_score is None:
            pending_stage = stage_default
            if pending_stage == "FINAL_ROUND":
                pending_stage = "third_place" if _is_third_place_event(event) else "final"
            print(f"    {home_name} vs {away_name}  [{pending_stage}]  (no score — recording as pending fixture)")
            append_pending_fixture_rows(event_id, round_num, pending_stage, "",
                                        home_name, away_name)
            continue

        wc = event.get("winnerCode", 0)

        # Penalty shootouts: treat as a narrow win (GD ±1) rather than a draw
        if home_score == away_score and wc in (1, 2):
            home_score, away_score = (1, 0) if wc == 1 else (0, 1)

        if stage_default == "FINAL_ROUND":
            is_third = _is_third_place_event(event)
            stage = "third_place" if is_third else "final"
            if wc == 1:
                home_stage = "third_place" if is_third else "winner"
                away_stage = "fourth_place" if is_third else "runner_up"
            else:
                home_stage = "fourth_place" if is_third else "runner_up"
                away_stage = "third_place" if is_third else "winner"
            update_stage(home_name, home_stage)
            update_stage(away_name, away_stage)
        else:
            stage = stage_default
            update_stage(home_name, stage)
            update_stage(away_name, stage)

        print(f"    [{event_id}] [{stage}] {home_name} {home_score}–{away_score} {away_name}")
        append_match_rows(event_id, round_num, stage, "",
                          home_name, away_name, home_score, away_score)

        if not skip_ratings:
            lineups = get_lineups(event_id)
            _add_ratings(rating_rows, lineups, year, event_id, round_num,
                         stage, home_name, away_name)

    # ------------------------------------------------------------------ #
    # Historical rows (stage reached per team)                            #
    # ------------------------------------------------------------------ #
    historical_rows = [
        {
            "tournament_year": year,
            "team":            team,
            "stage_reached":   stage_label,
            "stage_points":    STAGE_POINTS.get(stage_label, 0.25),
        }
        for team, (_, stage_label) in team_best_stage.items()
    ]

    # Write CSVs
    os.makedirs(output_dir, exist_ok=True)
    _append_csv(output_dir, "matches.csv",
        ["tournament_year", "round_num", "stage", "group", "event_id",
         "team", "opponent", "gd", "gf", "opponent_raw_rank", "opponent_conf"],
        match_rows)
    _append_csv(output_dir, "player_ratings.csv",
        ["tournament_year", "event_id", "round_num", "stage", "team",
         "player_name", "sofascore_id", "rating", "minutes_played"],
        rating_rows)
    _append_csv(output_dir, "teams.csv",
        ["tournament_year", "name", "confederation", "raw_rank",
         "is_host", "style", "squad_size"],
        list(team_info.values()))
    _append_csv(output_dir, "historical_wc.csv",
        ["tournament_year", "team", "stage_reached", "stage_points"],
        historical_rows)

    print(f"\n  Done: {len(match_rows)//2} matches, "
          f"{len(rating_rows)} player ratings, "
          f"{len(historical_rows)} teams tracked")


# =============================================================================
# CSV WRITERS
# =============================================================================

def _append_csv(output_dir, filename, fieldnames, rows):
    path   = os.path.join(output_dir, filename)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
    print(f"  → {filename}: +{len(rows)} rows")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Fetch World Cup data from SofaScore → CSVs"
    )
    parser.add_argument(
        "--years", nargs="+", type=int, default=[2022],
        help="Tournament years to fetch (e.g. --years 2018 2022 2026)"
    )
    parser.add_argument(
        "--output", default="data",
        help="Output directory for CSV files (default: data/)"
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Delete existing CSVs in output dir before fetching"
    )
    parser.add_argument(
        "--history-only", action="store_true",
        help="Skip fetching lineups/player ratings — use for older WCs only "
             "needed to feed historical_wc.csv (e.g. --years 1990 1994 1998), "
             "much faster since it skips the per-match lineups API call"
    )
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if args.clear:
        for fname in ["matches.csv", "player_ratings.csv", "teams.csv", "historical_wc.csv"]:
            p = os.path.join(args.output, fname)
            if os.path.exists(p):
                os.remove(p)
                print(f"Cleared {p}")

    init_browser()
    try:
        for year in args.years:
            fetch_year(year, args.output, skip_ratings=args.history_only)
    finally:
        close_browser()

    print(f"\n{'='*55}")
    print(f"  All done. CSVs written to: {args.output}/")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
