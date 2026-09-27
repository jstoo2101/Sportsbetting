#!/usr/bin/env python3
"""Pull current NFL game-line and player-prop odds from The Odds API,
filter to AU bookmakers, store every raw quote in odds_snapshots, and
write a best-price-per-market CSV for quick review.

Usage:
    python scripts/fetch_odds.py                 # game lines + all upcoming events' props
    python scripts/fetch_odds.py --game-lines-only
    python scripts/fetch_odds.py --event <event_id>   # props for one event only
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from betting import config, db, odds_api  # noqa: E402


def store_rows(conn, rows: list[odds_api.OddsRow]) -> None:
    conn.executemany(
        """INSERT INTO odds_snapshots
           (pulled_at, sport_key, event_id, commence_time, home_team, away_team,
            market, player, line, side, bookmaker, price_decimal, raw_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                r.pulled_at, r.sport_key, r.event_id, r.commence_time, r.home_team,
                r.away_team, r.market, r.player, r.line, r.side, r.bookmaker,
                r.price_decimal, None,
            )
            for r in rows
        ],
    )
    conn.commit()


def write_best_price_csv(rows: list[dict], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pulled_at", "event_id", "commence_time", "home_team", "away_team",
        "market", "player", "line", "side", "best_bookmaker", "best_price_decimal",
    ]
    with dest.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote {len(rows)} best-price rows -> {dest}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-lines-only", action="store_true")
    parser.add_argument("--event", help="fetch player props for a single event id")
    args = parser.parse_args()

    db.init_db()
    conn = db.get_connection()

    all_rows: list[odds_api.OddsRow] = []

    print("Fetching game lines...")
    game_lines_json = odds_api.get_game_lines()
    game_line_rows = odds_api.parse_game_lines(game_lines_json)
    all_rows.extend(game_line_rows)
    print(f"  {len(game_line_rows)} game-line quotes across {len(game_lines_json)} events")

    if not args.game_lines_only:
        if args.event:
            event_ids = [args.event]
        else:
            events = odds_api.list_events()
            event_ids = [e["id"] for e in events]
            print(f"Found {len(events)} upcoming events; fetching player props for each...")

        for event_id in event_ids:
            try:
                props_json = odds_api.get_event_player_props(event_id)
            except odds_api.OddsAPIError as e:
                print(f"  event {event_id}: {e}")
                continue
            prop_rows = odds_api.parse_player_props(props_json)
            if not prop_rows:
                print(f"  event {event_id}: no AU player-prop coverage yet")
            all_rows.extend(prop_rows)

    if not all_rows:
        print("No odds data returned. Nothing stored — check ODDS_API_KEY and quota.")
        return

    store_rows(conn, all_rows)
    best = odds_api.best_price(all_rows)
    write_best_price_csv(best, config.DATA_DIR / "odds_cache" / "best_prices_latest.csv")
    print(f"Stored {len(all_rows)} raw quotes in {config.DB_PATH}")


if __name__ == "__main__":
    main()
