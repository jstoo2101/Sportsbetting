import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from betting import odds_api

SAMPLE_EVENT_PROPS = {
    "id": "evt123",
    "sport_key": "americanfootball_nfl",
    "commence_time": "2026-10-04T17:00:00Z",
    "home_team": "Dallas Cowboys",
    "away_team": "Houston Texans",
    "bookmakers": [
        {
            "key": "sportsbet",
            "markets": [
                {
                    "key": "player_reception_yds",
                    "outcomes": [
                        {"name": "Over", "description": "Dalton Schultz", "point": 34.5, "price": 1.85},
                        {"name": "Under", "description": "Dalton Schultz", "point": 34.5, "price": 1.95},
                    ],
                }
            ],
        },
        {
            "key": "tab",
            "markets": [
                {
                    "key": "player_reception_yds",
                    "outcomes": [
                        {"name": "Over", "description": "Dalton Schultz", "point": 34.5, "price": 1.91},
                        {"name": "Under", "description": "Dalton Schultz", "point": 34.5, "price": 1.90},
                    ],
                }
            ],
        },
    ],
}


def test_parse_player_props_flattens_all_bookmakers():
    rows = odds_api.parse_player_props(SAMPLE_EVENT_PROPS)
    assert len(rows) == 4
    assert {r.bookmaker for r in rows} == {"sportsbet", "tab"}
    assert all(r.player == "Dalton Schultz" for r in rows)


def test_best_price_picks_highest_decimal_odds_per_side():
    rows = odds_api.parse_player_props(SAMPLE_EVENT_PROPS)
    best = odds_api.best_price(rows)
    over = next(b for b in best if b["side"] == "Over")
    under = next(b for b in best if b["side"] == "Under")
    assert over["best_bookmaker"] == "tab"
    assert over["best_price_decimal"] == 1.91
    assert under["best_bookmaker"] == "sportsbet"
    assert under["best_price_decimal"] == 1.95


def test_parse_player_props_empty_when_no_bookmakers():
    empty = {**SAMPLE_EVENT_PROPS, "bookmakers": []}
    assert odds_api.parse_player_props(empty) == []
