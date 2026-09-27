"""Thin client for The Odds API (https://the-odds-api.com/), scoped to
Australian bookmakers and NFL player props + game lines.

Player props are not available on the bulk /odds endpoint — The Odds API
requires per-event calls via /events/{id}/odds for prop markets. This costs
more quota per pull (roughly 1 request per market per event), so callers
should be deliberate about which events/markets they fetch, not poll
continuously. Check https://the-odds-api.com/liveapi/guides/v4/ for current
quota costs and rate limits before automating this on a schedule.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from . import config

SPORT_KEY = "americanfootball_nfl"

GAME_LINE_MARKETS = ["h2h", "spreads", "totals"]

# The Odds API's NFL player prop market keys as of this build. Prop market
# coverage (especially receptions/rush/rec yards) can vary week to week and
# is not guaranteed for every event — always check `bookmakers` in the
# response rather than assuming a market was returned.
PLAYER_PROP_MARKETS = [
    "player_reception_yds",
    "player_rush_yds",
    "player_receptions",
]


class OddsAPIError(RuntimeError):
    pass


def _get(path: str, params: dict) -> requests.Response:
    if not config.ODDS_API_KEY:
        raise OddsAPIError(
            "ODDS_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    params = {**params, "apiKey": config.ODDS_API_KEY}
    resp = requests.get(f"{config.ODDS_API_BASE_URL}{path}", params=params, timeout=30)
    if resp.status_code != 200:
        raise OddsAPIError(f"The Odds API returned {resp.status_code}: {resp.text[:500]}")
    remaining = resp.headers.get("x-requests-remaining")
    used = resp.headers.get("x-requests-used")
    if remaining is not None:
        print(f"[odds_api] quota: {used} used, {remaining} remaining this billing period")
    return resp


def list_events(sport_key: str = SPORT_KEY) -> list[dict]:
    resp = _get(f"/sports/{sport_key}/events", {})
    return resp.json()


def get_game_lines(sport_key: str = SPORT_KEY) -> list[dict]:
    resp = _get(
        f"/sports/{sport_key}/odds",
        {
            "regions": config.ODDS_API_REGION,
            "markets": ",".join(GAME_LINE_MARKETS),
            "oddsFormat": "decimal",
            "bookmakers": ",".join(config.ODDS_API_AU_BOOKMAKERS),
        },
    )
    return resp.json()


def get_event_player_props(event_id: str, sport_key: str = SPORT_KEY, markets: list[str] | None = None) -> dict:
    markets = markets or PLAYER_PROP_MARKETS
    resp = _get(
        f"/sports/{sport_key}/events/{event_id}/odds",
        {
            "regions": config.ODDS_API_REGION,
            "markets": ",".join(markets),
            "oddsFormat": "decimal",
            "bookmakers": ",".join(config.ODDS_API_AU_BOOKMAKERS),
        },
    )
    return resp.json()


@dataclass
class OddsRow:
    pulled_at: str
    sport_key: str
    event_id: str
    commence_time: str
    home_team: str
    away_team: str
    market: str
    player: str | None
    line: float | None
    side: str
    bookmaker: str
    price_decimal: float


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_player_props(event_odds_json: dict) -> list[OddsRow]:
    """Flatten a single event's /events/{id}/odds response into rows.

    Returns an empty list (not fabricated data) if no AU bookmaker carries
    any of the requested prop markets for this event yet — prop coverage
    fills in closer to kickoff and isn't guaranteed.
    """
    rows: list[OddsRow] = []
    pulled_at = _now_iso()
    for bm in event_odds_json.get("bookmakers", []):
        for market in bm.get("markets", []):
            for outcome in market.get("outcomes", []):
                rows.append(
                    OddsRow(
                        pulled_at=pulled_at,
                        sport_key=event_odds_json.get("sport_key", SPORT_KEY),
                        event_id=event_odds_json.get("id", ""),
                        commence_time=event_odds_json.get("commence_time", ""),
                        home_team=event_odds_json.get("home_team", ""),
                        away_team=event_odds_json.get("away_team", ""),
                        market=market.get("key", ""),
                        player=outcome.get("description"),
                        line=outcome.get("point"),
                        side=outcome.get("name", ""),
                        bookmaker=bm.get("key", ""),
                        price_decimal=float(outcome.get("price", 0.0)),
                    )
                )
    return rows


def parse_game_lines(events_json: list[dict]) -> list[OddsRow]:
    rows: list[OddsRow] = []
    pulled_at = _now_iso()
    for event in events_json:
        for bm in event.get("bookmakers", []):
            for market in bm.get("markets", []):
                for outcome in market.get("outcomes", []):
                    rows.append(
                        OddsRow(
                            pulled_at=pulled_at,
                            sport_key=event.get("sport_key", SPORT_KEY),
                            event_id=event.get("id", ""),
                            commence_time=event.get("commence_time", ""),
                            home_team=event.get("home_team", ""),
                            away_team=event.get("away_team", ""),
                            market=market.get("key", ""),
                            player=None,
                            line=outcome.get("point"),
                            side=outcome.get("name", ""),
                            bookmaker=bm.get("key", ""),
                            price_decimal=float(outcome.get("price", 0.0)),
                        )
                    )
    return rows


def best_price(rows: list[OddsRow]) -> list[dict]:
    """For each (event, market, player, line, side) group, find the single
    best (highest) decimal price across AU bookmakers."""
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r.event_id, r.market, r.player, r.line, r.side)
        if key not in best or r.price_decimal > best[key]["best_price_decimal"]:
            best[key] = {
                "event_id": r.event_id,
                "commence_time": r.commence_time,
                "home_team": r.home_team,
                "away_team": r.away_team,
                "market": r.market,
                "player": r.player,
                "line": r.line,
                "side": r.side,
                "best_bookmaker": r.bookmaker,
                "best_price_decimal": r.price_decimal,
                "pulled_at": r.pulled_at,
            }
    return list(best.values())
