"""Player prop projection model (v1).

    Proj = Recent3GameAvg x OpponentAdj x PaceAdj x RoleAdj x WeatherAdj

Recent3GameAvg, OpponentAdj, and PaceAdj are computed from nflverse weekly
player_stats data. RoleAdj and WeatherAdj are analyst judgment calls (manual
snap/target-share nudges and outdoor-weather knockdowns per the project
brief) and are passed in by the caller rather than derived here — there is
no free, reliable data source for either yet.

All trailing stats use only games strictly before the target week, so a
projection for week N never sees week N (or later) data — otherwise the
correlation/backtest numbers in the project brief would be leaking future
information into "predictions."
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

STAT_TO_PLAY_COLS = {
    # stat column -> the play-count columns that count as a "play" for pace purposes
    "receiving_yards": ["attempts", "carries"],
    "rushing_yards": ["attempts", "carries"],
    "receptions": ["attempts", "carries"],
}

STAT_TO_ATTACKING_POSITIONS = {
    # which position group's production this stat is measured against, for
    # computing how generous an opponent defense has been
    "receiving_yards": ["WR", "TE", "RB"],
    "rushing_yards": ["RB", "QB"],
    "receptions": ["WR", "TE", "RB"],
}

REGULAR_SEASON = "REG"


@dataclass
class Projection:
    player: str
    team: str
    opponent: str
    season: int
    week: int
    stat: str
    recent3_avg: float
    opponent_adj: float
    pace_adj: float
    role_adj: float
    weather_adj: float
    projection: float
    games_used: int


def _trailing(df: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    """Rows from the same season, strictly before `week`, regular season only."""
    return df[
        (df["season"] == season)
        & (df["week"] < week)
        & (df["season_type"] == REGULAR_SEASON)
    ]


def recent_n_avg(
    player_stats: pd.DataFrame,
    player_display_name: str,
    stat: str,
    season: int,
    week: int,
    window: int = 3,
) -> tuple[float, int]:
    hist = _trailing(player_stats, season, week)
    hist = hist[hist["player_display_name"] == player_display_name].sort_values("week")
    recent = hist.tail(window)
    if recent.empty:
        return 0.0, 0
    return float(recent[stat].mean()), len(recent)


def pace_adj(
    player_stats: pd.DataFrame,
    team: str,
    stat: str,
    season: int,
    week: int,
) -> float:
    """Team's trailing plays-per-game vs league average trailing plays-per-game."""
    hist = _trailing(player_stats, season, week)
    play_cols = STAT_TO_PLAY_COLS[stat]
    team_plays_by_week = (
        hist[hist["recent_team"] == team]
        .groupby("week")[play_cols]
        .sum()
        .sum(axis=1)
    )
    if team_plays_by_week.empty:
        return 1.0

    team_avg = team_plays_by_week.mean()

    # League average plays-per-team-per-week, computed the same way as team_avg.
    per_team_week = hist.groupby(["recent_team", "week"])[play_cols].sum().sum(axis=1)
    league_avg = per_team_week.groupby(level=1).mean().mean() if not per_team_week.empty else team_avg

    if not league_avg:
        return 1.0
    return float(team_avg / league_avg)


def opponent_adj(
    player_stats: pd.DataFrame,
    opponent: str,
    stat: str,
    season: int,
    week: int,
) -> float:
    """Opponent's trailing stat-allowed-per-game vs league average allowed-per-game,
    restricted to the position group(s) that produce this stat."""
    hist = _trailing(player_stats, season, week)
    positions = STAT_TO_ATTACKING_POSITIONS[stat]
    hist = hist[hist["position_group"].isin(positions)]

    allowed_by_week = hist[hist["opponent_team"] == opponent].groupby("week")[stat].sum()
    if allowed_by_week.empty:
        return 1.0
    opp_avg = allowed_by_week.mean()

    league_allowed = hist.groupby(["opponent_team", "week"])[stat].sum()
    league_avg = league_allowed.groupby(level=1).mean().mean() if not league_allowed.empty else opp_avg

    if not league_avg:
        return 1.0
    return float(opp_avg / league_avg)


def project(
    player_stats: pd.DataFrame,
    player_display_name: str,
    team: str,
    opponent: str,
    stat: str,
    season: int,
    week: int,
    role_adj: float = 1.0,
    weather_adj: float = 1.0,
    window: int = 3,
) -> Projection:
    if stat not in STAT_TO_PLAY_COLS:
        raise ValueError(f"unsupported stat: {stat}. Supported: {list(STAT_TO_PLAY_COLS)}")

    r3, games_used = recent_n_avg(player_stats, player_display_name, stat, season, week, window)
    opp_a = opponent_adj(player_stats, opponent, stat, season, week)
    pace_a = pace_adj(player_stats, team, stat, season, week)

    proj_value = r3 * opp_a * pace_a * role_adj * weather_adj

    return Projection(
        player=player_display_name,
        team=team,
        opponent=opponent,
        season=season,
        week=week,
        stat=stat,
        recent3_avg=r3,
        opponent_adj=opp_a,
        pace_adj=pace_a,
        role_adj=role_adj,
        weather_adj=weather_adj,
        projection=proj_value,
        games_used=games_used,
    )
