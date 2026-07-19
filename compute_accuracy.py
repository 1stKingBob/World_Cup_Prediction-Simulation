"""
Win/loss accuracy metrics for the CURRENT live (adopted) model config —
recomputed fresh since the data re-scrape + H2H drop + fifa_rank_signal
adoption changed the numbers from whatever was last quoted mid-session.

Two accuracy definitions:
  A) decisive-match accuracy: among real win/loss results only (draws
     excluded), did the model's implied winner (prob_a > 0.5 -> team1)
     match the actual winner?
  B) points-tiebreak accuracy: same, but draws are NOT excluded — a drawn
     match's "effective winner" is whichever team finished with more total
     tournament points (3/1/0 across all their matches that tournament),
     and the model is scored against that.
"""
import importlib.util

spec = importlib.util.spec_from_file_location("wc_predictor", "wc_predictor (1).py")
wcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcp)

TRAIN_YEARS = [2002, 2006, 2010, 2014, 2018]
HOLDOUT_YEARS = [2022, 2026]
ALL_YEARS = TRAIN_YEARS + HOLDOUT_YEARS


def tournament_points(match_rows, year):
    pts = {}
    seen = set()
    for r in match_rows:
        if r["gd"] == "" or r["tournament_year"] != str(year):
            continue
        eid = r["event_id"]
        team, opp = r["team"], r["opponent"]
        key = (eid, team)
        if key in seen:
            continue
        seen.add(key)
        gd = int(r["gd"])
        pts.setdefault(team, 0)
        pts.setdefault(opp, 0)
        if gd > 0:
            pts[team] += 3
        elif gd < 0:
            pts[opp] += 3
        else:
            pts[team] += 1
            pts[opp] += 1
    return pts


def run(years, label):
    dataset = wcp.load_backtest_dataset("data", years)
    decisive_correct = decisive_total = 0
    tiebreak_correct = tiebreak_total = 0
    brier_sum = 0.0

    for year in years:
        base_teams = dataset[year]["base_teams"]
        wcp.TEAMS = base_teams
        wcp.init_adjusted_ranks()
        wcp.set_h2h_matches(dataset[year]["h2h_matches"], index=dataset[year]["h2h_index"])
        wcp.PREDICTION_YEAR = year
        match_rows = dataset[year]["match_rows"]
        rating_rows = dataset[year]["rating_rows"]
        pts = tournament_points(match_rows, year)

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

            result = wcp.predict_match_asof(team1, team2, r["stage"], r["round_num"],
                                             base_teams, match_rows, rating_rows,
                                             event_id=r["event_id"])
            predicted = result["prob_a"]
            brier_sum += (predicted - actual) ** 2
            predicted_winner = team1 if predicted > 0.5 else team2

            if gd != 0:
                actual_winner = team1 if gd > 0 else team2
                decisive_total += 1
                if predicted_winner == actual_winner:
                    decisive_correct += 1
                tiebreak_total += 1
                if predicted_winner == actual_winner:
                    tiebreak_correct += 1
            else:
                tiebreak_total += 1
                p1, p2 = pts.get(team1, 0), pts.get(team2, 0)
                if p1 != p2:
                    effective_winner = team1 if p1 > p2 else team2
                    if predicted_winner == effective_winner:
                        tiebreak_correct += 1
                # if points also tied, no ground truth to check against -> skip (still counted in total? no)
                else:
                    tiebreak_total -= 1  # truly unresolvable, exclude

    n = decisive_total  # brier is computed over all scored matches (same n for decisive+draws)
    total_matches = sum(1 for y in years for r in dataset[y]["match_rows"]
                         if r["gd"] != "" ) # not deduped, rough count unused

    print(f"\n=== {label} ({years}) ===")
    print(f"  decisive-match accuracy:   {decisive_correct}/{decisive_total} = {100*decisive_correct/decisive_total:.1f}%")
    print(f"  points-tiebreak accuracy:  {tiebreak_correct}/{tiebreak_total} = {100*tiebreak_correct/tiebreak_total:.1f}%")


run(TRAIN_YEARS, "TRAIN")
run(HOLDOUT_YEARS, "HOLDOUT")
run(ALL_YEARS, "ALL (train+holdout combined)")
