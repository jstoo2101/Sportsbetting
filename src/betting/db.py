"""SQLite schema and connection helpers.

tips_log is append-only by design: a trigger blocks UPDATE and DELETE at the
database level so the paper-trading track record can't be edited after the
fact, no matter what tool touches the file. Corrections go in as a new row
referencing the original via `corrects_pick_id`, never as an edit.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pulled_at TEXT NOT NULL,           -- ISO 8601 UTC, when we hit the API
    sport_key TEXT NOT NULL,
    event_id TEXT NOT NULL,
    commence_time TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    market TEXT NOT NULL,              -- e.g. player_receiving_yds
    player TEXT,                       -- NULL for game-line markets
    line REAL,
    side TEXT NOT NULL,                -- 'Over'/'Under' or 'Home'/'Away'
    bookmaker TEXT NOT NULL,
    price_decimal REAL NOT NULL,
    raw_json TEXT                      -- full API record, for audit
);

CREATE TABLE IF NOT EXISTS projections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_at TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    player TEXT NOT NULL,
    team TEXT NOT NULL,
    opponent TEXT NOT NULL,
    stat TEXT NOT NULL,                 -- rushing_yards / receiving_yards / receptions
    recent3_avg REAL NOT NULL,
    opponent_adj REAL NOT NULL,
    pace_adj REAL NOT NULL,
    role_adj REAL NOT NULL,
    weather_adj REAL NOT NULL,
    projection REAL NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS tips_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at TEXT NOT NULL,            -- ISO 8601 UTC, immutable once written
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    player TEXT NOT NULL,
    team TEXT,
    market TEXT NOT NULL,
    side TEXT NOT NULL,                 -- Over/Under
    book_line REAL NOT NULL,
    projection REAL NOT NULL,
    edge_pct REAL NOT NULL,
    best_bookmaker TEXT NOT NULL,
    best_price_decimal REAL NOT NULL,
    stake_aud REAL NOT NULL,
    thesis TEXT,                        -- the human-readable reasoning
    status TEXT NOT NULL DEFAULT 'pending', -- pending/won/lost/push/void
    settled_at TEXT,
    actual_result REAL,
    corrects_pick_id INTEGER REFERENCES tips_log(id),
    source TEXT NOT NULL DEFAULT 'model' -- 'model' or 'manual' (analyst override)
);

-- Enforce append-only-except-settlement at the DB layer. Everything except
-- status/settled_at/actual_result is frozen once written; those three fields
-- exist purely to record the outcome of a pick already made, not to change
-- the pick itself.
CREATE TRIGGER IF NOT EXISTS tips_log_no_delete
BEFORE DELETE ON tips_log
BEGIN
    SELECT RAISE(ABORT, 'tips_log is append-only: deletes are not permitted');
END;

CREATE TRIGGER IF NOT EXISTS tips_log_settlement_only
BEFORE UPDATE ON tips_log
WHEN
    OLD.logged_at IS NOT NEW.logged_at OR
    OLD.season IS NOT NEW.season OR
    OLD.week IS NOT NEW.week OR
    OLD.player IS NOT NEW.player OR
    OLD.market IS NOT NEW.market OR
    OLD.side IS NOT NEW.side OR
    OLD.book_line IS NOT NEW.book_line OR
    OLD.projection IS NOT NEW.projection OR
    OLD.edge_pct IS NOT NEW.edge_pct OR
    OLD.best_bookmaker IS NOT NEW.best_bookmaker OR
    OLD.best_price_decimal IS NOT NEW.best_price_decimal OR
    OLD.stake_aud IS NOT NEW.stake_aud OR
    OLD.thesis IS NOT NEW.thesis
BEGIN
    SELECT RAISE(ABORT, 'tips_log picks are immutable: only status/settled_at/actual_result may be updated, via settle_pick()');
END;
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def settle_pick(conn: sqlite3.Connection, pick_id: int, status: str, actual_result: float | None, settled_at: str) -> None:
    """The only sanctioned way to touch an existing tips_log row."""
    if status not in {"won", "lost", "push", "void"}:
        raise ValueError(f"invalid settlement status: {status}")
    conn.execute(
        "UPDATE tips_log SET status = ?, actual_result = ?, settled_at = ? WHERE id = ?",
        (status, actual_result, settled_at, pick_id),
    )
    conn.commit()
