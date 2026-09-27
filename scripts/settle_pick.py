#!/usr/bin/env python3
"""Record the outcome of an already-logged pick. This is the only field
update the database permits on tips_log (see src/betting/db.py trigger) —
the pick itself (line, projection, edge, thesis) can never be edited.

Usage:
    python scripts/settle_pick.py --id 3 --status won --actual-result 71
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from betting import db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, type=int, dest="pick_id")
    parser.add_argument("--status", required=True, choices=["won", "lost", "push", "void"])
    parser.add_argument("--actual-result", type=float, default=None)
    args = parser.parse_args()

    conn = db.get_connection()
    db.settle_pick(conn, args.pick_id, args.status, args.actual_result, datetime.now(timezone.utc).isoformat())
    row = conn.execute("SELECT * FROM tips_log WHERE id = ?", (args.pick_id,)).fetchone()
    print(f"Settled pick {args.pick_id}: {dict(row)}")


if __name__ == "__main__":
    main()
