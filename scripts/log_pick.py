#!/usr/bin/env python3
"""Append one pick to the immutable tips_log. This is the only sanctioned
way to add a pick — do it once you've confirmed the edge and the thesis
agree (see compute_edges.py output).

Rows are append-only: the database itself refuses UPDATE/DELETE on the
pick fields (see src/betting/db.py). Settling a pick's result later uses
scripts/settle_pick.py, which only touches status/actual_result.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from betting import config, db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--player", required=True)
    parser.add_argument("--team")
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--week", required=True, type=int)
    parser.add_argument("--market", required=True)
    parser.add_argument("--side", required=True, choices=["Over", "Under"])
    parser.add_argument("--book-line", required=True, type=float)
    parser.add_argument("--projection", required=True, type=float)
    parser.add_argument("--best-bookmaker", required=True)
    parser.add_argument("--best-price", required=True, type=float, dest="best_price")
    parser.add_argument("--stake", type=float, default=config.UNIT_SIZE_AUD)
    parser.add_argument("--thesis", required=True, help="the human-readable reasoning for this pick")
    parser.add_argument("--source", default="model", choices=["model", "manual"])
    parser.add_argument("--corrects-pick-id", type=int, default=None,
                         help="if this replaces an earlier mis-logged pick, reference its id instead of editing it")
    args = parser.parse_args()

    edge_pct = (args.projection - args.book_line) / args.book_line

    db.init_db()
    conn = db.get_connection()
    cur = conn.execute(
        """INSERT INTO tips_log
           (logged_at, season, week, player, team, market, side, book_line, projection,
            edge_pct, best_bookmaker, best_price_decimal, stake_aud, thesis, source, corrects_pick_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            datetime.now(timezone.utc).isoformat(),
            args.season, args.week, args.player, args.team, args.market, args.side,
            args.book_line, args.projection, edge_pct, args.best_bookmaker, args.best_price,
            args.stake, args.thesis, args.source, args.corrects_pick_id,
        ),
    )
    conn.commit()
    print(f"Logged pick id={cur.lastrowid}: {args.player} {args.market} {args.side} {args.book_line} "
          f"@ {args.best_price} ({args.best_bookmaker}), edge {edge_pct:.1%}")


if __name__ == "__main__":
    main()
