import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from betting import edges
from betting.projections import Projection


def make_projection(projection_value: float, games_used: int) -> Projection:
    return Projection(
        player="Test Player", team="AAA", opponent="BBB", season=2026, week=3,
        stat="receiving_yards", recent3_avg=projection_value, opponent_adj=1.0,
        pace_adj=1.0, role_adj=1.0, weather_adj=1.0, projection=projection_value,
        games_used=games_used,
    )


def test_evaluate_pick_flags_a_real_edge_with_full_window():
    proj = make_projection(90.0, games_used=3)
    odds_by_side = {"Over": {"best_bookmaker": "sportsbet", "best_price_decimal": 1.9}}
    pick = edges.evaluate_pick(proj, book_line=70.0, odds_by_side=odds_by_side)
    assert pick is not None
    assert pick["side"] == "Over"


def test_evaluate_pick_rejects_thin_sample_even_with_huge_edge():
    # Same edge as above, but only 1 trailing game — should not be flagged
    # regardless of how large the percentage edge looks.
    proj = make_projection(90.0, games_used=1)
    odds_by_side = {"Over": {"best_bookmaker": "sportsbet", "best_price_decimal": 1.9}}
    pick = edges.evaluate_pick(proj, book_line=70.0, odds_by_side=odds_by_side)
    assert pick is None


def test_evaluate_pick_rejects_small_line_percentage_blowup_via_games_gate():
    # A near-zero line (e.g. 0.5 receptions) can make a tiny absolute miss
    # look like a massive percentage edge. The games_used gate is the
    # primary guard against treating that as real signal early in a season.
    proj = make_projection(5.0, games_used=2)
    odds_by_side = {"Over": {"best_bookmaker": "tab", "best_price_decimal": 2.35}}
    pick = edges.evaluate_pick(proj, book_line=0.5, odds_by_side=odds_by_side)
    assert pick is None
