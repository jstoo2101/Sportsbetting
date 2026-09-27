"""Edge calculation: compare a projection against the best available book
line and flag picks crossing the configured threshold.

Per the project brief, crossing the numeric threshold is necessary but not
sufficient — a pick also needs a matchup/role rationale that agrees with
the direction, which is a human judgment call and deliberately NOT
automated here. This module only answers "is the number big enough,"
scripts/log_pick.py is the deliberate, human-reviewed step that commits a
pick to the immutable tips_log.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config
from .projections import Projection


@dataclass
class EdgeResult:
    edge_pct: float
    side: str  # 'Over' or 'Under'
    flagged: bool


def compute_edge(projection_value: float, book_line: float, threshold: float = config.EDGE_THRESHOLD) -> EdgeResult:
    if book_line == 0:
        raise ValueError("book_line cannot be zero")
    edge_pct = (projection_value - book_line) / book_line
    side = "Over" if edge_pct > 0 else "Under"
    return EdgeResult(edge_pct=edge_pct, side=side, flagged=abs(edge_pct) >= threshold)


def evaluate_pick(
    projection: Projection,
    book_line: float,
    odds_by_side: dict[str, dict],
    min_games: int = config.RECENT_GAMES_WINDOW,
) -> dict | None:
    """Returns a candidate pick dict if the edge crosses the threshold AND a
    best price exists for the implied side, else None.

    Requires a full trailing window (min_games, default RECENT_GAMES_WINDOW)
    before flagging anything. Early in a season a player may only have 1-2
    games of history; the model's validated 0.48-0.56 correlation was
    measured on a full 3-game trailing average, not a thinner one, so a
    "projection" built from 1-2 games is a different, unvalidated thing —
    don't silently treat it as equivalent. This also incidentally guards
    against the edge_pct formula blowing up: thin-sample players tend to be
    low-usage bench guys with small book lines (0.5 receptions etc.), where
    a small absolute miss is a huge percentage "edge" that isn't real signal.
    """
    if projection.games_used < min_games:
        return None
    edge = compute_edge(projection.projection, book_line)
    if not edge.flagged:
        return None
    side_odds = odds_by_side.get(edge.side)
    if side_odds is None:
        return None
    return {
        "player": projection.player,
        "team": projection.team,
        "opponent": projection.opponent,
        "season": projection.season,
        "week": projection.week,
        "market": projection.stat,
        "side": edge.side,
        "book_line": book_line,
        "projection": projection.projection,
        "edge_pct": edge.edge_pct,
        "best_bookmaker": side_odds["best_bookmaker"],
        "best_price_decimal": side_odds["best_price_decimal"],
        "games_used": projection.games_used,
    }
