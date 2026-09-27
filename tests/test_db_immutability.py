import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from betting import db


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    c = db.get_connection(db_path)
    c.execute(
        """INSERT INTO tips_log
           (logged_at, season, week, player, market, side, book_line, projection,
            edge_pct, best_bookmaker, best_price_decimal, stake_aud, thesis)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("2026-01-01T00:00:00Z", 2025, 4, "Test Player", "receiving_yards", "Over",
         50.0, 60.0, 0.2, "sportsbet", 1.9, 5.0, "test thesis"),
    )
    c.commit()
    yield c
    c.close()


def test_pick_fields_cannot_be_edited(conn):
    with pytest.raises(Exception, match="immutable"):
        conn.execute("UPDATE tips_log SET book_line = 999 WHERE id = 1")
        conn.commit()


def test_pick_cannot_be_deleted(conn):
    with pytest.raises(Exception, match="append-only"):
        conn.execute("DELETE FROM tips_log WHERE id = 1")
        conn.commit()


def test_settle_pick_is_permitted(conn):
    db.settle_pick(conn, 1, "won", 65.0, "2026-01-02T00:00:00Z")
    row = conn.execute("SELECT status, actual_result FROM tips_log WHERE id = 1").fetchone()
    assert row["status"] == "won"
    assert row["actual_result"] == 65.0


def test_settle_pick_rejects_invalid_status(conn):
    with pytest.raises(ValueError):
        db.settle_pick(conn, 1, "bogus", 65.0, "2026-01-02T00:00:00Z")
