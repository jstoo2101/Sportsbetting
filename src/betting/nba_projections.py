"""NBA player prop projection model (v1) — same shape as the NBL model:

    Proj = Recent3GameAvg x OpponentAdj x PaceAdj x RoleAdj

No WeatherAdj (indoors). Unlike NBL, there's no "round" concept to worry
about: sportsdataverse's NBA data carries a real per-game date
(game_date/game_date_time) on every row, so trailing history is ordered
chronologically rather than via a round-number boundary — this sidesteps
the doubleheader-round bug class found in the NBL model entirely (a team
essentially never plays twice on the same calendar date in the modern NBA
schedule), but the per-team-round-style aggregations below still default
to `.mean()` rather than `.sum()` wherever they group by (team, date), on
the same principle that caused that bug: never assume exactly one row per
group when a data source hasn't explicitly guaranteed it.

OpponentAdj/PaceAdj are computed from TEAM box scores via a same-game_id
self-join (each game has exactly two rows, one per team — confirmed on the
live data after filtering out the All-Star exhibition game, see
fetch_nba_data.py), the same technique as the NBL model. PaceAdj uses the
standard basketball estimated-possessions formula on the team's own box
score: FGA + 0.44*FTA - OREB + TOV, using `total_turnovers` (turnovers +
team_turnovers — verified these two sum to total_turnovers for ~99.96% of
rows) rather than the bare `turnovers` column, which excludes team-level
turnovers like shot-clock violations and would otherwise systematically
inflate every team's estimated pace.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

SUPPORTED_STATS = ["points", "rebounds", "assists", "three_point_field_goals_made"]

POSSESSION_COLS = ["field_goals_attempted", "free_throws_attempted", "offensive_rebounds", "total_turnovers"]

# player_box and team_box don't share column names for the same stat —
# team_box has no "points" (it's "team_score") or "rebounds" (it's
# "total_rebounds"); assists and threes happen to match.
STAT_TO_TEAM_COL = {
    "points": "team_score",
    "rebounds": "total_rebounds",
    "assists": "assists",
    "three_point_field_goals_made": "three_point_field_goals_made",
}


@dataclass
class NbaProjection:
    player: str
    team: str
    opponent: str
    season: int
    game_date: str
    stat: str
    recent3_avg: float
    opponent_adj: float
    pace_adj: float
    role_adj: float
    projection: float
    games_used: int


def _trailing(df: pd.DataFrame, season: int, game_date: str) -> pd.DataFrame:
    return df[(df["season"] == season) & (df["game_date"] < game_date)]


def recent_n_avg(
    player_box: pd.DataFrame,
    athlete_id,
    stat: str,
    season: int,
    game_date: str,
    window: int = 3,
) -> tuple[float, int]:
    hist = _trailing(player_box, season, game_date)
    hist = hist[hist["athlete_id"] == athlete_id].sort_values(["game_date", "game_date_time"])
    recent = hist.tail(window)
    if recent.empty:
        return 0.0, 0
    return float(recent[stat].mean()), len(recent)


def _team_possessions(df: pd.DataFrame) -> pd.Series:
    return (
        df["field_goals_attempted"]
        + 0.44 * df["free_throws_attempted"]
        - df["offensive_rebounds"]
        + df["total_turnovers"]
    )


def pace_adj(team_box: pd.DataFrame, team: str, season: int, game_date: str) -> float:
    hist = _trailing(team_box, season, game_date)
    if hist.empty:
        return 1.0
    hist = hist.assign(_poss=_team_possessions(hist))

    team_hist = hist[hist["team_abbreviation"] == team]
    if team_hist.empty:
        return 1.0
    team_avg = team_hist["_poss"].mean()

    per_team_date = hist.groupby(["team_abbreviation", "game_date"])["_poss"].mean()
    league_avg = per_team_date.groupby(level=1).mean().mean() if not per_team_date.empty else team_avg

    if not league_avg:
        return 1.0
    return float(team_avg / league_avg)


def opponent_adj(team_box: pd.DataFrame, opponent: str, stat: str, season: int, game_date: str) -> float:
    hist = _trailing(team_box, season, game_date)
    if hist.empty:
        return 1.0

    merged = hist.merge(hist, on="game_id", suffixes=("", "_opp"))
    merged = merged[merged["team_abbreviation"] != merged["team_abbreviation_opp"]]
    allowed_col = f"{STAT_TO_TEAM_COL[stat]}_opp"

    opp_allowed = merged[merged["team_abbreviation"] == opponent]
    if opp_allowed.empty:
        return 1.0
    opp_avg = opp_allowed[allowed_col].mean()

    league_allowed = merged.groupby(["team_abbreviation", "game_date"])[allowed_col].mean()
    league_avg = league_allowed.groupby(level=1).mean().mean() if not league_allowed.empty else opp_avg

    if not league_avg:
        return 1.0
    return float(opp_avg / league_avg)


def project(
    player_box: pd.DataFrame,
    team_box: pd.DataFrame,
    athlete_id,
    player_name: str,
    team: str,
    opponent: str,
    stat: str,
    season: int,
    game_date: str,
    role_adj: float = 1.0,
    window: int = 3,
) -> NbaProjection:
    if stat not in SUPPORTED_STATS:
        raise ValueError(f"unsupported stat: {stat}. Supported: {SUPPORTED_STATS}")

    r3, games_used = recent_n_avg(player_box, athlete_id, stat, season, game_date, window)
    opp_a = opponent_adj(team_box, opponent, stat, season, game_date)
    pace_a = pace_adj(team_box, team, season, game_date)

    projection_value = r3 * opp_a * pace_a * role_adj

    return NbaProjection(
        player=player_name,
        team=team,
        opponent=opponent,
        season=season,
        game_date=game_date,
        stat=stat,
        recent3_avg=r3,
        opponent_adj=opp_a,
        pace_adj=pace_a,
        role_adj=role_adj,
        projection=projection_value,
        games_used=games_used,
    )
