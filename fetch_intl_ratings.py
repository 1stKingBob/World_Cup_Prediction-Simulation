#!/usr/bin/env python3.10
"""
International Player Ratings Collector
=======================================
Scrapes player ratings (from SofaScore) for every real match already in
h2h_matches.csv within a given year range — not just World Cup matches.
Reuses fetch_wc_data.py's browser/API machinery (get_event_by_id,
get_lineups, normalize_name) rather than rebuilding it, since h2h_matches.csv
was already scraped from the same source.

Two API calls per match are needed, not one: get_lineups() gives player
ratings keyed by "home"/"away", but doesn't say which real team is which —
that comes from a separate get_event_by_id() call. Skipping that and
guessing from h2h_matches.csv's own team/opponent columns would risk
silently mislabeling which team a player's rating belongs to (those columns
just reflect "whichever team's perspective this row represents" — both
directions are already stored as separate rows for the same match).

Resumable: writes each match's rows immediately and flushes, and skips any
event_id already present in the output file on restart — this is a multi-
hour scrape, so losing partial progress on an interruption would be costly.

Usage:
    python3.10 fetch_intl_ratings.py --start-year 2002 --end-year 2026
"""
import argparse
import csv
import os
import time

import fetch_wc_data as fwc

OUTPUT_FIELDS = ["event_id", "date", "team", "opponent", "competition",
                  "is_friendly", "player_name", "sofascore_id", "rating", "minutes_played"]


def load_h2h_events(data_dir, start_year, end_year):
    """One entry per unique event_id (both team/opponent rows collapse to
    the same event), scoped to [start_year, end_year] by real match date."""
    path = os.path.join(data_dir, "h2h_matches.csv")
    events = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yr = int(row["date"][:4])
            if not (start_year <= yr <= end_year):
                continue
            eid = row["event_id"]
            if eid not in events:
                events[eid] = {
                    "date": row["date"],
                    "competition": row["competition"],
                    "is_friendly": row["is_friendly"],
                }
    return events


def load_done_event_ids(out_path, skip_log_path):
    """Both successfully-written AND previously-skipped (no lineup data)
    event_ids count as "done" on resume — otherwise a restart wastes ~1.2s
    per event re-discovering the same 404s all over again."""
    done = set()
    if os.path.exists(out_path):
        with open(out_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add(row["event_id"])
    if os.path.exists(skip_log_path):
        with open(skip_log_path, encoding="utf-8") as f:
            done.update(line.strip() for line in f if line.strip())
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output", default="data/intl_player_ratings.csv")
    args = parser.parse_args()

    skip_log_path = args.output + ".skipped"

    events = load_h2h_events(args.data_dir, args.start_year, args.end_year)
    ordered_ids = sorted(events.keys(), key=lambda eid: events[eid]["date"])
    print(f"{len(ordered_ids)} unique matches in [{args.start_year}, {args.end_year}]")

    done = load_done_event_ids(args.output, skip_log_path)
    remaining = [eid for eid in ordered_ids if eid not in done]
    print(f"{len(done)} already done, {len(remaining)} remaining")

    skip_f = open(skip_log_path, "a", encoding="utf-8")

    write_header = not os.path.exists(args.output)
    out_f = open(args.output, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=OUTPUT_FIELDS)
    if write_header:
        writer.writeheader()
        out_f.flush()

    fwc.init_browser()
    t0 = time.time()
    n_written = 0
    n_skipped = 0

    def mark_skipped(eid):
        nonlocal n_skipped
        n_skipped += 1
        skip_f.write(eid + "\n")
        skip_f.flush()

    try:
        for i, eid in enumerate(remaining):
            meta = events[eid]
            try:
                event = fwc.get_event_by_id(eid)
                if not event:
                    mark_skipped(eid)
                    continue
                home_name = fwc.normalize_name(event["homeTeam"]["name"])
                away_name = fwc.normalize_name(event["awayTeam"]["name"])

                lineups = fwc.get_lineups(eid)
                if not lineups:
                    mark_skipped(eid)
                    continue
            except Exception as e:
                # Browser/page context can die on a long-running session
                # (observed: "Execution context was destroyed" after ~100
                # minutes). Reinit and retry this ONE event once before
                # giving up on it — better than losing the whole run.
                print(f"    Browser error on {eid}: {e}  — reiniting browser and retrying once")
                try:
                    fwc.close_browser()
                except Exception:
                    pass
                fwc.init_browser()
                try:
                    event = fwc.get_event_by_id(eid)
                    lineups = fwc.get_lineups(eid) if event else None
                    if not event or not lineups:
                        mark_skipped(eid)
                        continue
                    home_name = fwc.normalize_name(event["homeTeam"]["name"])
                    away_name = fwc.normalize_name(event["awayTeam"]["name"])
                except Exception as e2:
                    print(f"    Retry also failed on {eid}: {e2}  — skipping")
                    mark_skipped(eid)
                    continue

            rows_this_match = 0
            for side, team_name, opp_name in [("home", home_name, away_name),
                                               ("away", away_name, home_name)]:
                for p in lineups.get(side, {}).get("players", []):
                    player = p.get("player", {})
                    stats = p.get("statistics", {})
                    rating = stats.get("rating")
                    if rating is None:
                        continue
                    try:
                        rating = float(rating)
                    except (ValueError, TypeError):
                        continue
                    writer.writerow({
                        "event_id": eid, "date": meta["date"],
                        "team": team_name, "opponent": opp_name,
                        "competition": meta["competition"], "is_friendly": meta["is_friendly"],
                        "player_name": player.get("name", ""),
                        "sofascore_id": player.get("id", ""),
                        "rating": round(rating, 2),
                        "minutes_played": stats.get("minutesPlayed", 0),
                    })
                    rows_this_match += 1
            out_f.flush()
            if rows_this_match > 0:
                n_written += 1
            else:
                mark_skipped(eid)

            if (i + 1) % 25 == 0 or (i + 1) == len(remaining):
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta_min = (len(remaining) - (i + 1)) / rate / 60 if rate > 0 else float("nan")
                print(f"  [{i+1}/{len(remaining)}] written={n_written} skipped={n_skipped}  "
                      f"elapsed={elapsed/60:.1f}m  eta={eta_min:.1f}m")
    finally:
        out_f.close()
        skip_f.close()
        try:
            fwc.close_browser()
        except Exception:
            pass

    print(f"\nDone. {n_written} matches written, {n_skipped} skipped. Output: {args.output}")


if __name__ == "__main__":
    main()
