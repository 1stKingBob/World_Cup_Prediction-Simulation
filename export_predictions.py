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

import csv
import importlib.util
import json
import os
from datetime import date

import dixon_coles as dc
import my_poisson as mp

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
            p1, p2, _ = probs["Final"]   # most-informed cutoff, used as the static/legacy default
            dc_probs = dc_probs_by_anchor(team1, team2, is_group=True)
            mp_probs = mp_probs_by_anchor(probs)
            dc_scorelines = dc_scoreline_by_anchor(team1, team2)
            mp_scorelines = mp_scoreline_by_anchor(probs)
            matches.append({
                "id": f"{gid}_{r['round_num']}_{eid}",
                "team1": team1, "team2": team2,
                "score1": gf1, "score2": gf2,
                "prob1": p1, "prob2": p2,
                "probs_by_anchor": probs,
                "dc_probs_by_anchor": dc_probs,
                "mp_probs_by_anchor": mp_probs,
                "dc_scoreline_by_anchor": dc_scorelines,
                "mp_scoreline_by_anchor": mp_scorelines,
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
DC_MODELS = None      # set in main(): one fitted Dixon-Coles model per anchor stage


def dc_anchor_cutoff_dates():
    """Real calendar date to use as Dixon-Coles' as-of cutoff for each
    anchor stage — the earliest real date among that anchor's own matches,
    cross-referenced from matches.csv (event_id, stage, round_num) into
    h2h_matches.csv (event_id -> date), since matches.csv itself has no
    real dates for WC fixtures (only stage/round_num — see
    ANCHOR_CUTOFFS above), but this project's international corpus does.
    Falls back to today's real date for any stage that hasn't happened yet
    (no real date recorded for it) — e.g. the Final before it's played."""
    event_dates = {}
    with open(os.path.join(DATA_DIR, "h2h_matches.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            event_dates[row["event_id"]] = row["date"]

    def earliest(pred):
        dates = [event_dates[r["event_id"]] for r in MATCH_ROWS
                 if pred(r) and r["event_id"] in event_dates]
        return min(dates) if dates else None

    cutoffs = {}
    for md in (1, 2, 3):
        cutoffs[f"GR{md}"] = earliest(
            lambda r, md=md: r["stage"] == "group_stage" and int(r["round_num"]) == md)
    for stage, short in [("round_of_32", "R32"), ("round_of_16", "R16"),
                         ("quarter_final", "QF"), ("semi_final", "SF"), ("final", "Final")]:
        cutoffs[short] = earliest(lambda r, stage=stage: r["stage"] == stage)

    today_str = str(date.today())
    last_known = None
    for anchor in ANCHOR_STAGES:
        if cutoffs.get(anchor) is None:
            cutoffs[anchor] = today_str if last_known is None else last_known
        else:
            last_known = cutoffs[anchor]
    return {a: dc._parse_date(d) for a, d in cutoffs.items()}


def build_dc_models():
    """One Dixon-Coles snapshot per anchor stage — same idea as the custom
    model's per-anchor as-of predictions, just using real calendar dates
    (this corpus has them) instead of the WC-only stage/round_num cutoff."""
    intl_matches = dc.load_international_matches(DATA_DIR)
    cutoffs = dc_anchor_cutoff_dates()
    return {a: dc.fit_dixon_coles(intl_matches, cutoff_date=cutoffs[a]) for a in ANCHOR_STAGES}


def dc_probs_by_anchor(team1, team2, is_group):
    """Dixon-Coles' own {anchor: (prob1, probDraw, prob2)} for a matchup.
    Group matches keep the genuine 3-way split (Dixon-Coles natively models
    draws, unlike the custom model's win-probability-only architecture).
    Knockout matches can't really end in a draw (extra time/penalties
    always produce a winner), so their draw mass is redistributed
    proportionally between the two win probabilities instead of just being
    discarded — the natural way to convert a 3-way forecast into a 2-way
    one for a fixture that structurally can't draw."""
    out = {}
    for anchor in ANCHOR_STAGES:
        p_a, p_draw, p_b = dc.predict_dixon_coles(DC_MODELS[anchor], team1, team2)
        if is_group:
            out[anchor] = (p_a, p_draw, p_b)
        else:
            total = p_a + p_b
            out[anchor] = (p_a / total, 0.0, p_b / total) if total > 0 else (0.5, 0.0, 0.5)
    return out


def mp_probs_by_anchor(probs):
    """my_poisson.py's own {anchor: (prob1, probDraw, prob2)} for a group
    match — group matches always keep the genuine 3-way split, same
    reasoning as dc_probs_by_anchor. Takes the ALREADY-computed
    match_probs_by_anchor() result (which already carries weighted_gap per
    anchor) instead of recomputing predict_match_asof a second time —
    my_poisson is purely a translation of the custom model's own signal, so
    it never needs its own fresh model call."""
    out = {}
    for anchor in ANCHOR_STAGES:
        _, _, weighted_gap = probs[anchor]
        out[anchor] = mp.predict_outcome_probs(weighted_gap)
    return out


def dc_scoreline_by_anchor(team1, team2):
    """Dixon-Coles' single most-likely exact scoreline per anchor — a point
    estimate on top of the win/draw/loss aggregate in dc_probs_by_anchor,
    for display (e.g. "88% (3)") rather than for scoring."""
    return {a: dc.most_likely_scoreline(DC_MODELS[a], team1, team2) for a in ANCHOR_STAGES}


def mp_scoreline_by_anchor(probs):
    """my_poisson.py's most-likely exact scoreline per anchor — same
    already-computed-gap reuse as mp_probs_by_anchor."""
    out = {}
    for anchor in ANCHOR_STAGES:
        _, _, weighted_gap = probs[anchor]
        out[anchor] = mp.most_likely_scoreline(weighted_gap)
    return out

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

    Returns {anchor_name: (prob1, prob2, weighted_gap)} — weighted_gap (the
    custom model's own pre-sigmoid signal) is included so my_poisson.py can
    translate the SAME per-anchor signal into a goals-based forecast
    without a second predict_match_asof call.
    """
    out = {}
    for anchor in ANCHOR_STAGES:
        stage, round_num = ANCHOR_CUTOFFS[anchor]
        result = wcp.predict_match_asof(team1, team2, stage, round_num,
                                        BASE_TEAMS, MATCH_ROWS, RATING_ROWS,
                                        event_id=event_id)
        out[anchor] = (result["prob_a"], result["prob_b"], result["gap"]["weighted_gap"])
    return out


def match_prob(team1, team2, stage, round_num, event_id=None):
    """Single-cutoff prediction (this match's own real position) — kept for
    the static defaultData.ts fallback (render_ts), which shows one baseline
    number before predictions.json loads at runtime. Returns
    (prob1, prob2, weighted_gap) — see match_probs_by_anchor."""
    result = wcp.predict_match_asof(team1, team2, stage, round_num,
                                    BASE_TEAMS, MATCH_ROWS, RATING_ROWS,
                                    event_id=event_id)
    return result["prob_a"], result["prob_b"], result["gap"]["weighted_gap"]


ROUND_CHAIN = ["R32", "R16", "QF", "SF", "Final"]   # ThirdPlace sourced separately (SF losers)


def build_knockouts(all_rows):
    """Real, fixed bracket data only — one row per round with the REAL team
    pairing (SofaScore only publishes a round's fixture once the feeding
    round is fully decided) and the REAL result if the match itself has
    been played. No probabilities here anymore: see build_anchor_bracket(),
    which computes a probability — and, for any round not yet decided AS OF
    a given anchor, an anchor-projected pairing instead of the real one —
    fresh per anchor. Splitting it out this way is what fixes a real bug:
    previously every round always showed the REAL eventual pairing even
    when displayed in 'prediction' styling for an early anchor, so e.g. an
    early-round upset the model correctly favored (team A over team B)
    would still show team B (the real winner) advancing in the next round
    — internally contradicting the very prediction just shown."""
    rounds = {}
    for stage, short in [("round_of_32", "R32"), ("round_of_16", "R16"),
                         ("quarter_final", "QF"), ("semi_final", "SF"),
                         ("final", "Final"), ("third_place", "ThirdPlace")]:
        events = dedupe_events(all_rows, stage)
        matches = []
        for r in events:
            team1, team2 = r["team"], r["opponent"]
            if r["gd"] == "":
                matches.append({"team1": team1, "team2": team2, "played": False,
                                "event_id": r["event_id"]})
            else:
                gf1 = int(r["gf"]); gd1 = int(r["gd"]); gf2 = gf1 - gd1
                matches.append({"team1": team1, "team2": team2, "played": True,
                                "score1": gf1, "score2": gf2, "event_id": r["event_id"]})
        rounds[short] = matches

    # SofaScore only publishes Final/ThirdPlace fixtures once both
    # semifinals are decided in reality. If that hasn't happened yet,
    # project the two REAL semifinal results forward (winners -> Final,
    # losers -> ThirdPlace) so the site never shows a blank 'TBD' even
    # before the real fixture exists. This is a one-time fallback based on
    # REAL SF facts, not an anchor-aware projection — build_anchor_bracket
    # below is what makes the EARLY-anchor views of these rounds honest.
    sf = rounds.get("SF", [])
    if not rounds["Final"] and len(sf) == 2 and sf[0]["played"] and sf[1]["played"]:
        w1 = sf[0]["team1"] if sf[0]["score1"] > sf[0]["score2"] else sf[0]["team2"]
        w2 = sf[1]["team1"] if sf[1]["score1"] > sf[1]["score2"] else sf[1]["team2"]
        rounds["Final"] = [{"team1": w1, "team2": w2, "played": False}]
    if not rounds["ThirdPlace"] and len(sf) == 2 and sf[0]["played"] and sf[1]["played"]:
        l1 = sf[0]["team2"] if sf[0]["score1"] > sf[0]["score2"] else sf[0]["team1"]
        l2 = sf[1]["team2"] if sf[1]["score1"] > sf[1]["score2"] else sf[1]["team1"]
        rounds["ThirdPlace"] = [{"team1": l1, "team2": l2, "played": False}]

    return rounds


def build_topology(rounds):
    """The fixed BRACKET SLOT structure: for every match beyond R32, which
    earlier-round match produced each of its two participants (matched by
    real team name). This is independent of any prediction — it's just
    'who feeds into this slot' — so build_anchor_bracket can walk it and
    substitute in a hypothetically-projected participant for anchors
    before that earlier match's own natural cutoff."""
    def find_source(team, prev_matches):
        for idx, m in enumerate(prev_matches):
            if team in (m["team1"], m["team2"]):
                return idx
        return None

    topo = {}
    for ci in range(1, len(ROUND_CHAIN)):
        prev_short, cur_short = ROUND_CHAIN[ci - 1], ROUND_CHAIN[ci]
        prev_matches = rounds[prev_short]
        for mi, m in enumerate(rounds[cur_short]):
            topo[(cur_short, mi, "team1")] = (prev_short, find_source(m["team1"], prev_matches))
            topo[(cur_short, mi, "team2")] = (prev_short, find_source(m["team2"], prev_matches))
    for mi, m in enumerate(rounds.get("ThirdPlace", [])):
        topo[("ThirdPlace", mi, "team1")] = ("SF", find_source(m["team1"], rounds["SF"]))
        topo[("ThirdPlace", mi, "team2")] = ("SF", find_source(m["team2"], rounds["SF"]))
    return topo


def build_anchor_bracket(anchor, rounds, topo):
    """The bracket as it would genuinely look from THIS anchor's own
    vantage point. A round strictly before the anchor uses the REAL
    (already-known-by-then) result to decide who advanced; a round at or
    after the anchor uses THIS anchor's own model prediction — recursively,
    so a hypothetical upset several rounds back correctly changes every
    downstream pairing too, instead of silently snapping back to the real
    eventual bracket (see build_knockouts's docstring for why that was a
    real bug, not just a styling quirk).

    Returns {round_short: [match, ...]} for R32/R16/QF/SF/Final/ThirdPlace,
    each match a dict with team1/team2/prob1/prob2/played(/score1/score2).
    """
    anchor_idx = ANCHOR_STAGES.index(anchor)

    def is_predicted(round_short):
        # ThirdPlace isn't its own anchor stage — it happens alongside the
        # Final, so it's predicted/decided exactly when the Final is.
        stage_for_index = "Final" if round_short == "ThirdPlace" else round_short
        return ANCHOR_STAGES.index(stage_for_index) >= anchor_idx

    stage, round_num = ANCHOR_CUTOFFS[anchor]
    cache = {}

    def resolve(round_short, match_idx, side):
        key = (round_short, match_idx, side)
        if key in cache:
            return cache[key]
        if round_short == "R32":
            result = rounds["R32"][match_idx][side]
            cache[key] = result
            return result
        src_round, src_idx = topo.get((round_short, match_idx, side), (None, None))
        if src_idx is None:
            # No earlier real match found yet to trace back to (e.g. a
            # still-fallback-projected Final/ThirdPlace slot) — just use
            # whatever real team is already on record for this slot.
            result = rounds[round_short][match_idx][side]
            cache[key] = result
            return result
        p1 = resolve(src_round, src_idx, "team1")
        p2 = resolve(src_round, src_idx, "team2")
        src_match = rounds[src_round][src_idx]
        if (not is_predicted(src_round)) and src_match["played"]:
            winner = p1 if src_match["score1"] > src_match["score2"] else p2
        else:
            prob1, prob2, _ = match_prob(p1, p2, stage, round_num)
            winner = p1 if prob1 >= prob2 else p2
        # ThirdPlace is contested by the source match's LOSER, not winner —
        # every other round advances the winner.
        result = (p2 if winner == p1 else p1) if round_short == "ThirdPlace" else winner
        cache[key] = result
        return result

    result = {}
    for round_short in ROUND_CHAIN + ["ThirdPlace"]:
        out_matches = []
        for mi, m in enumerate(rounds[round_short]):
            if round_short == "R32":
                rp1, rp2 = m["team1"], m["team2"]
            else:
                rp1 = resolve(round_short, mi, "team1")
                rp2 = resolve(round_short, mi, "team2")

            is_real_pairing = (rp1, rp2) in [(m.get("team1"), m.get("team2")), (m.get("team2"), m.get("team1"))]
            real_decided = (not is_predicted(round_short)) and m["played"] and is_real_pairing
            event_id = m.get("event_id") if is_real_pairing else None

            prob1, prob2, weighted_gap = match_prob(rp1, rp2, stage, round_num, event_id=event_id)
            dc_p1, _, dc_p2 = dc.predict_dixon_coles(DC_MODELS[anchor], rp1, rp2)
            dc_total = dc_p1 + dc_p2
            dc_p1, dc_p2 = (dc_p1 / dc_total, dc_p2 / dc_total) if dc_total > 0 else (0.5, 0.5)
            # my_poisson: knockout matches can't really end in a draw
            # (extra time/penalties always produce a winner), so redistribute
            # its draw mass into the two win probabilities — same treatment
            # dc_probs_by_anchor gives Dixon-Coles for knockout matches.
            mp_p1, mp_pd, mp_p2 = mp.predict_outcome_probs(weighted_gap)
            mp_total = mp_p1 + mp_p2
            mp_p1, mp_p2 = (mp_p1 / mp_total, mp_p2 / mp_total) if mp_total > 0 else (0.5, 0.5)
            dc_sl1, dc_sl2 = dc.most_likely_scoreline(DC_MODELS[anchor], rp1, rp2)
            mp_sl1, mp_sl2 = mp.most_likely_scoreline(weighted_gap)
            entry = {"team1": rp1, "team2": rp2, "prob1": prob1, "prob2": prob2,
                    "dc_prob1": dc_p1, "dc_prob2": dc_p2,
                    "mp_prob1": mp_p1, "mp_prob2": mp_p2,
                    "dc_score1": dc_sl1, "dc_score2": dc_sl2,
                    "mp_score1": mp_sl1, "mp_score2": mp_sl2}
            if real_decided:
                entry["played"] = True
                entry["score1"] = m["score1"]
                entry["score2"] = m["score2"]
            else:
                entry["played"] = False
            out_matches.append(entry)
        result[round_short] = out_matches
    return result


def main():
    global BASE_TEAMS, MATCH_ROWS, RATING_ROWS, DC_MODELS

    wcp.init_from_csv(DATA_DIR, YEAR)
    wcp.init_adjusted_ranks()   # depends only on raw_rank/confederation — fixed, computed once

    BASE_TEAMS = wcp.TEAMS
    MATCH_ROWS = wcp.read_matches_csv(DATA_DIR, YEAR)
    RATING_ROWS = wcp.read_ratings_csv(DATA_DIR, YEAR)

    print("Fitting Dixon-Coles models (one per anchor stage)...")
    DC_MODELS = build_dc_models()

    all_rows = MATCH_ROWS
    r32_rows = [r for r in all_rows if r["stage"] == "round_of_32"]
    teams_played_r32 = {r["team"] for r in r32_rows}

    groups = build_groups(all_rows, teams_played_r32)
    knockouts = build_knockouts(all_rows)
    topology = build_topology(knockouts)
    # One fully-resolved bracket per anchor — team pairings AND probabilities
    # both computed fresh from that anchor's own vantage point (see
    # build_anchor_bracket's docstring). Computed once here and reused both
    # for predictions.json and for render_ts's static fallback below.
    anchor_brackets = {a: build_anchor_bracket(a, knockouts, topology) for a in ANCHOR_STAGES}

    # ---- predictions.json ----
    # Nested by anchor stage: overlay["anchors"][anchor] holds the SAME
    # shape the frontend used to merge flatly, but with team1/team2/prob1/
    # prob2 all drawn from that anchor's own resolved bracket instead of a
    # single frozen (Final-anchor) pairing — see build_anchor_bracket's
    # docstring for why this exists: without it, the frontend's anchor
    # slider changed which matches were STYLED as predictions vs results,
    # but a round downstream of an early-anchor "prediction" always showed
    # the real eventual winner advancing regardless, contradicting the
    # prediction just shown one round earlier.
    # Every match carries a top-level prob1/probDraw/prob2 (the custom
    # model — unchanged shape, so anything not yet toggle-aware keeps
    # working) PLUS a "models" dict with both engines' numbers side by
    # side, for the frontend's model-switch toggle to pick from.
    def build_anchor_overlay(anchor):
        ov = {"year": YEAR, "groups": {}, "knockoutRounds": {}}
        for gid, g in groups.items():
            ov["groups"][gid] = {
                "teams": [{"advanceProb": t["advanceProb"]} for t in g["teams"]],
                "matches": [
                    {"prob1": m["probs_by_anchor"][anchor][0], "probDraw": 0.0,
                     "prob2": m["probs_by_anchor"][anchor][1],
                     "played": True, "result": {"score1": m["score1"], "score2": m["score2"]},
                     "models": {
                         "custom": {"prob1": m["probs_by_anchor"][anchor][0], "probDraw": 0.0,
                                    "prob2": m["probs_by_anchor"][anchor][1]},
                         "poisson": {"prob1": m["dc_probs_by_anchor"][anchor][0],
                                     "probDraw": m["dc_probs_by_anchor"][anchor][1],
                                     "prob2": m["dc_probs_by_anchor"][anchor][2],
                                     "predScore1": m["dc_scoreline_by_anchor"][anchor][0],
                                     "predScore2": m["dc_scoreline_by_anchor"][anchor][1]},
                         "my_poisson": {"prob1": m["mp_probs_by_anchor"][anchor][0],
                                        "probDraw": m["mp_probs_by_anchor"][anchor][1],
                                        "prob2": m["mp_probs_by_anchor"][anchor][2],
                                        "predScore1": m["mp_scoreline_by_anchor"][anchor][0],
                                        "predScore2": m["mp_scoreline_by_anchor"][anchor][1]},
                     }}
                    for m in g["matches"]
                ],
            }
        for short, matches in anchor_brackets[anchor].items():
            ov["knockoutRounds"][short] = [
                {"team1": {"name": m["team1"], "code": COUNTRY_CODES.get(m["team1"], "")},
                 "team2": {"name": m["team2"], "code": COUNTRY_CODES.get(m["team2"], "")},
                 "prob1": m["prob1"], "probDraw": 0.0, "prob2": m["prob2"],
                 "played": m["played"],
                 **({"result": {"score1": m["score1"], "score2": m["score2"]}} if m["played"] else {}),
                 "models": {
                     "custom": {"prob1": m["prob1"], "probDraw": 0.0, "prob2": m["prob2"]},
                     "poisson": {"prob1": m["dc_prob1"], "probDraw": 0.0, "prob2": m["dc_prob2"],
                                 "predScore1": m["dc_score1"], "predScore2": m["dc_score2"]},
                     "my_poisson": {"prob1": m["mp_prob1"], "probDraw": 0.0, "prob2": m["mp_prob2"],
                                    "predScore1": m["mp_score1"], "predScore2": m["mp_score2"]},
                 }}
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
    # Uses the "Final" anchor's resolved bracket (most-informed cutoff) —
    # the static one-time snapshot shown before predictions.json loads.
    ts_path = "/tmp/tournament2026.ts"
    with open(ts_path, "w", encoding="utf-8") as f:
        f.write(render_ts(groups, anchor_brackets["Final"]))
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
                   ("QF", "Quarter-finals"), ("SF", "Semi-finals"), ("Final", "Final"),
                   ("ThirdPlace", "Third Place")]
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
