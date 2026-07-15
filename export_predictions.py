#!/usr/bin/env python3.10
"""
Export Predictions — bridges wc_predictor.py to the React frontend
====================================================================
Reads real scraped WC 2026 data (data/*.csv), runs the prediction model,
and writes two things:

1. predictions.json, into BOTH frontend projects' public/ folders —
   "World Cup Prediction Simulator" (original) and "World Cup Prediction
   Simulator (1)" (the one actually wired up/attached going forward, since
   it has the UI being used). The dynamic overlay (advanceProb, match
   probabilities, actual results, nested per anchor stage) that each
   frontend merges on top of its own static tournament2026 structure in
   src/data/defaultData.ts at runtime (see App.tsx's useEffect fetch).

2. /tmp/tournament2026_structure.json (scratch)
   The real team/group/bracket *structure* (names, codes, group assignment,
   R32/R16/QF/SF/Final pairings) — used once to hand-correct
   defaultData.ts's tournament2026 entry, which was hardcoded before the
   real December 2025 draw happened and no longer matches reality.

Rerun this anytime after re-scraping (fetch_wc_data.py --years 2026) to
refresh predictions.json with the latest results/forecasts. The structure
file only needs regenerating if team/group composition changes (it won't,
post-draw) or the knockout bracket advances past what defaultData.ts encodes.
"""

import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
YEAR = 2026

# --- Load wc_predictor (1).py as a module (space/paren in filename) ---
spec = importlib.util.spec_from_file_location("wc_predictor", os.path.join(HERE, "wc_predictor (1).py"))
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

# "As-of" snapshot machinery (chronological_key, build_teams_asof) now lives
# in wc_predictor (1).py itself — shared with the backtest/weight-search tooling.

COUNTRY_CODES = {
    "Canada": "CA", "Mexico": "MX", "USA": "US",
    "Australia": "AU", "Iraq": "IQ", "Iran": "IR", "Japan": "JP", "Jordan": "JO",
    "South Korea": "KR", "Qatar": "QA", "Saudi Arabia": "SA", "Uzbekistan": "UZ",
    "Algeria": "DZ", "Cape Verde": "CV", "DR Congo": "CD", "Ivory Coast": "CI",
    "Egypt": "EG", "Ghana": "GH", "Morocco": "MA", "Senegal": "SN",
    "South Africa": "ZA", "Tunisia": "TN",
    "Curacao": "CW", "Haiti": "HT", "Panama": "PA",
    "Argentina": "AR", "Brazil": "BR", "Colombia": "CO", "Ecuador": "EC",
    "Paraguay": "PY", "Uruguay": "UY",
    "New Zealand": "NZ",
    "Austria": "AT", "Belgium": "BE", "Bosnia and Herzegovina": "BA", "Croatia": "HR",
    "Czech Republic": "CZ", "England": "GB", "France": "FR", "Germany": "DE",
    "Netherlands": "NL", "Norway": "NO", "Portugal": "PT", "Scotland": "GB",
    "Spain": "ES", "Sweden": "SE", "Switzerland": "CH", "Turkey": "TR",
}


def build_groups(all_rows, teams_played_r32):
    """Real group standings + the 6 real group-stage matches per group."""
    group_rows = [r for r in all_rows if r["stage"] == "group_stage"]

    # Standings: aggregate one row per (team) from the "team" perspective rows.
    stats = {}
    for r in group_rows:
        team = r["team"]
        st = stats.setdefault(team, {
            "group": r["group"], "played": 0, "won": 0, "drawn": 0, "lost": 0,
            "gf": 0, "ga": 0,
        })
        gd = int(r["gd"])
        gf = int(r["gf"])
        st["played"] += 1
        st["gf"] += gf
        st["ga"] += gf - gd
        if gd > 0:
            st["won"] += 1
        elif gd == 0:
            st["drawn"] += 1
        else:
            st["lost"] += 1

    groups = {}
    for team, st in stats.items():
        gid = st["group"]
        groups.setdefault(gid, []).append(team)

    result = {}
    for gid, teams in groups.items():
        ranked = sorted(
            teams,
            key=lambda t: (-(3 * stats[t]["won"] + stats[t]["drawn"]),
                           -(stats[t]["gf"] - stats[t]["ga"]),
                           -stats[t]["gf"], t),
        )
        team_entries = []
        for t in ranked:
            st = stats[t]
            pts = 3 * st["won"] + st["drawn"]
            team_entries.append({
                "name": t, "code": COUNTRY_CODES.get(t, ""),
                "played": st["played"], "won": st["won"], "drawn": st["drawn"],
                "lost": st["lost"], "gf": st["gf"], "ga": st["ga"], "points": pts,
                "advanceProb": 1.0 if t in teams_played_r32 else 0.0,
            })

        # 6 real matches, in matchday (round_num) order, natural encounter order.
        seen_events = set()
        matches = []
        rows_for_group = [r for r in group_rows if r["group"] == gid]
        rows_for_group.sort(key=lambda r: (int(r["round_num"]), r["event_id"]))
        for r in rows_for_group:
            eid = r["event_id"]
            if eid in seen_events:
                continue
            seen_events.add(eid)
            team1, team2 = r["team"], r["opponent"]
            gf1 = int(r["gf"])
            gd1 = int(r["gd"])
            gf2 = gf1 - gd1
            probs = match_probs_by_anchor(team1, team2, event_id=eid)
            p1, p2 = probs["Final"]   # most-informed cutoff, used as the static/legacy default
            matches.append({
                "id": f"{gid}_{r['round_num']}_{eid}",
                "team1": team1, "team2": team2,
                "score1": gf1, "score2": gf2,
                "prob1": p1, "prob2": p2,
                "probs_by_anchor": probs,
            })

        result[gid] = {"teams": team_entries, "matches": matches}

    return result


def dedupe_events(rows, stage):
    """One row per real event_id for a given stage, in file-encounter order
    (== SofaScore bracket order), keeping the 'team' perspective as team1."""
    seen = set()
    out = []
    for r in rows:
        if r["stage"] != stage:
            continue
        eid = r["event_id"]
        if eid in seen:
            continue
        seen.add(eid)
        out.append(r)
    return out


BASE_TEAMS = None    # set in main(): full-season team metadata (rank/conf/style/etc.)
MATCH_ROWS = None    # set in main(): every 2026 matches.csv row
RATING_ROWS = None   # set in main(): every 2026 player_ratings.csv row

# The frontend's "anchor point" stage selector (buildStageOrder in App.tsx)
# lets a viewer rewind to any of these 8 points and see EVERY match at or
# after it re-predicted using only data available up to that point — not
# just each match's own natural cutoff. ANCHOR_CUTOFFS gives the
# (stage, round_num) to pass to predict_match_asof for each one: "predict
# this anchor and everything after it, using only real results strictly
# before this cutoff." GR1's cutoff is round_num=1 (not 0) because
# chronological_key/build_teams_asof exclude anything >= the cutoff, and
# group_stage's own round_num IS the matchday — so cutoff=1 means "nothing
# from matchday 1 onward counts yet," a genuine pre-tournament prediction.
ANCHOR_STAGES = ["GR1", "GR2", "GR3", "R32", "R16", "QF", "SF", "Final"]
ANCHOR_CUTOFFS = {
    "GR1": ("group_stage", 1),
    "GR2": ("group_stage", 2),
    "GR3": ("group_stage", 3),
    "R32": ("round_of_32", 0),
    "R16": ("round_of_16", 0),
    "QF": ("quarter_final", 0),
    "SF": ("semi_final", 0),
    "Final": ("final", 0),
}


def match_probs_by_anchor(team1, team2, event_id=None):
    """Predict team1 vs team2 once per anchor stage (see ANCHOR_STAGES),
    each using only data available strictly before that anchor's cutoff —
    not each team's full season in hindsight, and not just this match's own
    natural position. That's what lets the frontend's anchor slider show a
    genuinely different, correctly-timed probability for the SAME match
    depending on which point in the tournament you're viewing from, rather
    than one frozen number regardless of the slider position.

    Pass `event_id` for a real scheduled/played match so it's excluded from
    its own H2H evidence at every anchor — h2h_matches.csv includes this
    tournament's own matches, so without this a played match would see its
    own real result counted as "prior" head-to-head history for itself.

    Returns {anchor_name: (prob1, prob2)}.
    """
    out = {}
    for anchor in ANCHOR_STAGES:
        stage, round_num = ANCHOR_CUTOFFS[anchor]
        result = wcp.predict_match_asof(team1, team2, stage, round_num,
                                        BASE_TEAMS, MATCH_ROWS, RATING_ROWS,
                                        event_id=event_id)
        out[anchor] = (result["prob_a"], result["prob_b"])
    return out


def match_prob(team1, team2, stage, round_num, event_id=None):
    """Single-cutoff prediction (this match's own real position) — kept for
    the static defaultData.ts fallback (render_ts), which shows one baseline
    number before predictions.json loads at runtime."""
    result = wcp.predict_match_asof(team1, team2, stage, round_num,
                                    BASE_TEAMS, MATCH_ROWS, RATING_ROWS,
                                    event_id=event_id)
    return result["prob_a"], result["prob_b"]


def build_knockouts(all_rows):
    rounds = {}

    for stage, short in [("round_of_32", "R32"), ("round_of_16", "R16")]:
        events = dedupe_events(all_rows, stage)
        matches = []
        for r in events:
            team1, team2 = r["team"], r["opponent"]
            gf1 = int(r["gf"]); gd1 = int(r["gd"]); gf2 = gf1 - gd1
            probs = match_probs_by_anchor(team1, team2, event_id=r["event_id"])
            p1, p2 = probs["Final"]
            matches.append({
                "team1": team1, "team2": team2, "played": True,
                "score1": gf1, "score2": gf2, "prob1": p1, "prob2": p2,
                "probs_by_anchor": probs,
            })
        rounds[short] = matches

    # Quarter-finals: 3 real results + QF4 (Argentina v Switzerland) pending
    qf_events = dedupe_events(all_rows, "quarter_final")
    qf_matches = []
    for r in qf_events:
        team1, team2 = r["team"], r["opponent"]
        probs = match_probs_by_anchor(team1, team2, event_id=r["event_id"])
        p1, p2 = probs["Final"]
        if r["gd"] == "":
            qf_matches.append({"team1": team1, "team2": team2, "played": False,
                               "prob1": p1, "prob2": p2, "probs_by_anchor": probs})
        else:
            gf1 = int(r["gf"]); gd1 = int(r["gd"]); gf2 = gf1 - gd1
            qf_matches.append({"team1": team1, "team2": team2, "played": True,
                               "score1": gf1, "score2": gf2, "prob1": p1, "prob2": p2,
                               "probs_by_anchor": probs})
    rounds["QF"] = qf_matches

    def projected_winner(mtc):
        """Actual winner if played; otherwise the model's favorite under the
        most-informed (Final) anchor — propagated forward so the bracket
        always shows a concrete projected path to the final, not a blank
        'TBD'. The projected OPPONENT for an undetermined slot doesn't vary
        by anchor (the real bracket pairing is fixed either way); only the
        probability shown for that fixed pairing varies by anchor."""
        if mtc["played"]:
            return mtc["team1"] if mtc["score1"] > mtc["score2"] else mtc["team2"]
        return mtc["team1"] if mtc["prob1"] >= mtc["prob2"] else mtc["team2"]

    # Semi-finals: SF1 France v Spain (pending).
    # SF2: England already confirmed via QF; the other slot depends on QF4
    # (Argentina v Switzerland, still unplayed) — project the model's
    # favorite forward as the placeholder opponent rather than "TBD".
    sf_events = dedupe_events(all_rows, "semi_final")
    sf1 = sf_events[0]
    team1, team2 = sf1["team"], sf1["opponent"]
    probs_sf1 = match_probs_by_anchor(team1, team2, event_id=sf1["event_id"])
    p1, p2 = probs_sf1["Final"]
    sf_matches = [{"team1": team1, "team2": team2, "played": False,
                   "prob1": p1, "prob2": p2, "probs_by_anchor": probs_sf1}]

    qf4 = next(m for m in qf_matches if not m["played"])
    qf4_projected = projected_winner(qf4)
    probs_sf2 = match_probs_by_anchor("England", qf4_projected)
    p_eng, p_opp = probs_sf2["Final"]
    sf_matches.append({"team1": "England", "team2": qf4_projected, "played": False,
                       "prob1": p_eng, "prob2": p_opp, "probs_by_anchor": probs_sf2})
    rounds["SF"] = sf_matches

    # Final: project both semifinal winners forward the same way.
    sf1_projected = projected_winner(sf_matches[0])
    sf2_projected = projected_winner(sf_matches[1])
    probs_final = match_probs_by_anchor(sf1_projected, sf2_projected)
    p1, p2 = probs_final["Final"]
    rounds["Final"] = [{"team1": sf1_projected, "team2": sf2_projected, "played": False,
                        "prob1": p1, "prob2": p2, "probs_by_anchor": probs_final}]

    return rounds


def main():
    global BASE_TEAMS, MATCH_ROWS, RATING_ROWS

    wcp.init_from_csv(DATA_DIR, YEAR)
    wcp.init_adjusted_ranks()   # depends only on raw_rank/confederation — fixed, computed once

    BASE_TEAMS = wcp.TEAMS
    MATCH_ROWS = wcp.read_matches_csv(DATA_DIR, YEAR)
    RATING_ROWS = wcp.read_ratings_csv(DATA_DIR, YEAR)

    all_rows = MATCH_ROWS
    r32_rows = [r for r in all_rows if r["stage"] == "round_of_32"]
    teams_played_r32 = {r["team"] for r in r32_rows}

    groups = build_groups(all_rows, teams_played_r32)
    knockouts = build_knockouts(all_rows)

    # ---- predictions.json ----
    # Nested by anchor stage: overlay["anchors"][anchor] holds the SAME
    # shape the frontend used to merge flatly, but with prob1/prob2 drawn
    # from that anchor's own cutoff (m["probs_by_anchor"][anchor]) instead
    # of a single frozen (Final-anchor) number — see match_probs_by_anchor's
    # docstring and ANCHOR_STAGES/ANCHOR_CUTOFFS above for why this exists:
    # without it, the frontend's anchor slider changed which matches were
    # STYLED as predictions vs results, but never actually changed any
    # probability value.
    def build_anchor_overlay(anchor):
        ov = {"year": YEAR, "groups": {}, "knockoutRounds": {}}
        for gid, g in groups.items():
            ov["groups"][gid] = {
                "teams": [{"advanceProb": t["advanceProb"]} for t in g["teams"]],
                "matches": [
                    {"prob1": m["probs_by_anchor"][anchor][0], "probDraw": 0.0,
                     "prob2": m["probs_by_anchor"][anchor][1],
                     "played": True, "result": {"score1": m["score1"], "score2": m["score2"]}}
                    for m in g["matches"]
                ],
            }
        for short, matches in knockouts.items():
            ov["knockoutRounds"][short] = [
                ({"team1": {"name": m["team1"], "code": COUNTRY_CODES.get(m["team1"], "")},
                  "team2": {"name": m["team2"], "code": COUNTRY_CODES.get(m["team2"], "")},
                  "prob1": m["probs_by_anchor"][anchor][0], "probDraw": 0.0,
                  "prob2": m["probs_by_anchor"][anchor][1],
                  "played": True, "result": {"score1": m["score1"], "score2": m["score2"]}}
                 if m["played"] else
                 {"team1": {"name": m["team1"], "code": COUNTRY_CODES.get(m["team1"], "")},
                  "team2": {"name": m["team2"], "code": COUNTRY_CODES.get(m["team2"], "")},
                  "prob1": m["probs_by_anchor"][anchor][0], "probDraw": 0.0,
                  "prob2": m["probs_by_anchor"][anchor][1], "played": False})
                for m in matches
            ]
        return ov

    overlay = {"year": YEAR, "anchors": {a: build_anchor_overlay(a) for a in ANCHOR_STAGES}}

    for project_dir in ("World Cup Prediction Simulator", "World Cup Prediction Simulator (1)"):
        out_path = os.path.join(HERE, project_dir, "public", "predictions.json")
        if not os.path.isdir(os.path.dirname(out_path)):
            continue
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(overlay, f, indent=2)
        print(f"Wrote {out_path}")

    # ---- structure dump (team names/codes/groups/bracket shape) ----
    structure = {
        "year": YEAR,
        "groups": {
            gid: {
                "teams": [{"name": t["name"], "code": t["code"]} for t in g["teams"]],
                "matches": [{"team1": m["team1"], "team2": m["team2"]} for m in g["matches"]],
            }
            for gid, g in groups.items()
        },
        "knockoutRounds": {
            short: [{"team1": m["team1"], "team2": m["team2"]} for m in matches]
            for short, matches in knockouts.items()
        },
    }
    struct_path = "/tmp/tournament2026_structure.json"
    with open(struct_path, "w", encoding="utf-8") as f:
        json.dump(structure, f, indent=2)
    print(f"Wrote {struct_path}")

    # ---- TS source for defaultData.ts's tournament2026 block ----
    ts_path = "/tmp/tournament2026.ts"
    with open(ts_path, "w", encoding="utf-8") as f:
        f.write(render_ts(groups, knockouts))
    print(f"Wrote {ts_path}")


def render_ts(groups, knockouts):
    lines = []
    lines.append("export const tournament2026: TournamentData = {")
    lines.append("  year: 2026,")
    lines.append("  teamCount: 48,")
    lines.append("  groups: [")
    for gid in sorted(groups.keys()):
        g = groups[gid]
        lines.append("    {")
        lines.append(f'      id: "{gid}", name: "Group {gid}",')
        lines.append("      teams: [")
        for t in g["teams"]:
            lines.append(
                f'        ts("{t["name"]}", "{t["code"]}", {t["played"]}, {t["won"]}, '
                f'{t["drawn"]}, {t["lost"]}, {t["gf"]}, {t["ga"]}, '
                f'{3 * t["won"] + t["drawn"]}, {t["advanceProb"]}),'
            )
        lines.append("      ],")
        lines.append("      matches: [")
        for i, mtc in enumerate(g["matches"]):
            c1 = COUNTRY_CODES.get(mtc["team1"], "")
            c2 = COUNTRY_CODES.get(mtc["team2"], "")
            lines.append(
                f'        m("{mtc["id"]}", ["{mtc["team1"]}","{c1}"], ["{mtc["team2"]}","{c2}"], '
                f'{mtc["prob1"]:.4f}, 0, {mtc["prob2"]:.4f}, '
                f'{{ played: true, s1: {mtc["score1"]}, s2: {mtc["score2"]} }}),'
            )
        lines.append("      ],")
        lines.append("    },")
    lines.append("  ],")

    lines.append("  knockoutRounds: [")
    round_names = [("R32", "Round of 32"), ("R16", "Round of 16"),
                   ("QF", "Quarter-finals"), ("SF", "Semi-finals"), ("Final", "Final")]
    for short, full in round_names:
        lines.append("    {")
        lines.append(f'      name: "{full}", shortName: "{short}",')
        lines.append("      matches: [")
        for i, mtc in enumerate(knockouts[short]):
            c1 = COUNTRY_CODES.get(mtc["team1"], "")
            c2 = COUNTRY_CODES.get(mtc["team2"], "")
            mid = f"{short}_{i + 1}"
            if mtc["played"]:
                opts = f'{{ played: true, s1: {mtc["score1"]}, s2: {mtc["score2"]} }}'
            else:
                opts = "{}"
            lines.append(
                f'        m("{mid}", ["{mtc["team1"]}","{c1}"], ["{mtc["team2"]}","{c2}"], '
                f'{mtc["prob1"]:.4f}, 0, {mtc["prob2"]:.4f}, {opts}),'
            )
        lines.append("      ],")
        lines.append("    },")
    lines.append("  ],")
    lines.append("};")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
