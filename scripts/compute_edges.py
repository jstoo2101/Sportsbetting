#!/usr/bin/env python3
"""Join our projections against the best-price odds CSV (from fetch_odds.py)
and print every candidate pick that crosses the edge threshold.

This does NOT write to tips_log — it's a review step. Picks you want to
paper-trade for real go into the immutable ledger via scripts/log_pick.py,
after you've checked the edge agrees with an actual matchup/role thesis
(see project brief: threshold alone isn't sufficient).

Usage:
    python scripts/compute_edges.py --odds data/odds_cache/best_prices_latest.csv \\
        --player "Dalton Schultz" --team HOU --opponent DAL \\
        --stat receiving_yards --season 2026 --week 4
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from betting import config, edges, projections  # noqa: E402


def load_odds_by_side(odds_csv: Path, player: str, market: str) -> tuple[float | None, dict]:
    """Returns (book_line, {side: best-price-row}) for one player/market from
    the best-price CSV that fetch_odds.py writes."""
    odds_by_side: dict[str, dict] = {}
    book_line = None
    with odds_csv.open() as f:
        for row in csv.DictReader(f):
            if row["player"] != player or row["market"] != market:
                continue
            book_line = float(row["line"])
            odds_by_side[row["side"]] = {
                "best_bookmaker": row["best_bookmaker"],
                "best_price_decimal": float(row["best_price_decimal"]),
            }
    return book_line, odds_by_side


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--odds", required=True, type=Path, help="best-price CSV from fetch_odds.py")
    parser.add_argument("--player", required=True)
    parser.add_argument("--team", required=True)
    parser.add_argument("--opponent", required=True)
    parser.add_argument("--stat", required=True, choices=list(projections.STAT_TO_PLAY_COLS))
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--week", required=True, type=int)
    parser.add_argument("--role-adj", type=float, default=1.0, help="manual role/target-share nudge, e.g. 1.1")
    parser.add_argument("--weather-adj", type=float, default=1.0, help="manual weather knockdown, e.g. 0.85")
    args = parser.parse_args()

    # The Odds API uses its own market key naming (e.g. player_reception_yds);
    # our stat naming matches nflverse columns (receiving_yards). Map here.
    market_key_map = {
        "receiving_yards": "player_reception_yds",
        "rushing_yards": "player_rush_yds",
        "receptions": "player_receptions",
    }
    book_line, odds_by_side = load_odds_by_side(args.odds, args.player, market_key_map[args.stat])
    if book_line is None:
        print(f"No odds found for {args.player} / {args.stat} in {args.odds}")
        return

    player_stats = pd.read_csv(config.NFLVERSE_DIR / "player_stats.csv")
    proj = projections.project(
        player_stats,
        player_display_name=args.player,
        team=args.team,
        opponent=args.opponent,
        stat=args.stat,
        season=args.season,
        week=args.week,
        role_adj=args.role_adj,
        weather_adj=args.weather_adj,
    )
    print(proj)

    pick = edges.evaluate_pick(proj, book_line, odds_by_side)
    if pick is None:
        edge = edges.compute_edge(proj.projection, book_line)
        print(f"No pick: edge {edge.edge_pct:.1%} does not cross the {config.EDGE_THRESHOLD:.0%} threshold "
              f"(or no price available for the {edge.side} side).")
        return

    print("\nCANDIDATE PICK (review before logging):")
    for k, v in pick.items():
        print(f"  {k}: {v}")
    print(
        "\nIf the direction agrees with your matchup/role thesis, log it with:\n"
        f"  python scripts/log_pick.py --player \"{pick['player']}\" --team {pick['team']} "
        f"--season {pick['season']} --week {pick['week']} --market {pick['market']} "
        f"--side {pick['side']} --book-line {pick['book_line']} --projection {pick['projection']:.2f} "
        f"--best-bookmaker {pick['best_bookmaker']} --best-price {pick['best_price_decimal']} "
        f"--thesis \"...\""
    )


if __name__ == "__main__":
    main()
