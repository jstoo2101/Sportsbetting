"""NBL player prop projection model (v1) — same structure as NFL's, adapted
for basketball:

    Proj = Recent3GameAvg x OpponentAdj x PaceAdj x RoleAdj

There's no WeatherAdj: NBL is played indoors, so it doesn't apply.

Unlike the NFL model, OpponentAdj and PaceAdj here are computed from
TEAM box scores (data/nbl/team_box.csv), not aggregated from player rows:

  - OpponentAdj: what the opponent's defense allows per game for this stat,
    vs league average. In box_team.csv each match has exactly two rows (one
    per team); "what team X allows" is literally the OTHER row's own stat
    total for that match (one team's production is definitionally what
    their opponent allowed), so this is a same-match_id self-join, not a
    position-based estimate. That sidesteps the playing_position column
    entirely, which is worth doing — its values are inconsistent junk
    across seasons/data-provider eras ('G', 'GRD', 'Guard', 'PG/SG', ...).
  - PaceAdj: team's own estimated possessions per game (the standard
    basketball formula: FGA + 0.44*FTA - OREB + TOV) vs league average.

All trailing stats use only rounds strictly before the target round, same
no-lookahead rule as the NFL model.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

SUPPORTED_STATS = ["points", "rebounds_total", "assists", "three_pointers_made"]

POSSESSION_COLS = ["field_goals_attempted", "free_throws_attempted", "rebounds_offensive", "turnovers"]


@dataclass
class NblProjection:
    player: str
    team: str
    opponent: str
    season: int
    round_number: int
    stat: str
    recent3_avg: float
    opponent_adj: float
    pace_adj: float
    role_adj: float
    projection: float
    games_used: int


def _round_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _trailing(df: pd.DataFrame, season: int, round_number: int) -> pd.DataFrame:
    rn = _round_num(df["round_number"])
    return df[(df["season"] == season) & (rn < round_number) & rn.notna()]


def recent_n_avg(
    player_box: pd.DataFrame,
    player_full_name: str,
    stat: str,
    season: int,
    round_number: int,
    window: int = 3,
) -> tuple[float, int]:
    hist = _trailing(player_box, season, round_number)
    full_name = hist["first_name"].fillna("") + " " + hist["family_name"].fillna("")
    hist = hist[full_name == player_full_name]
    # A round can carry more than one game (NBL sometimes schedules a team
    # twice in the same round), so round_number alone doesn't fully order
    # games — break ties with the match's actual kickoff time.
    hist = hist.sort_values(["round_number", "match_time_utc"], key=lambda c: _round_num(c) if c.name == "round_number" else c)
    recent = hist.tail(window)
    if recent.empty:
        return 0.0, 0
    return float(recent[stat].mean()), len(recent)


def _team_possessions(df: pd.DataFrame) -> pd.Series:
    return (
        df["field_goals_attempted"]
        + 0.44 * df["free_throws_attempted"]
        - df["rebounds_offensive"]
        + df["turnovers"]
    )


def pace_adj(team_box: pd.DataFrame, team: str, season: int, round_number: int) -> float:
    hist = _trailing(team_box, season, round_number)
    if hist.empty:
        return 1.0
    hist = hist.assign(_poss=_team_possessions(hist))

    team_hist = hist[hist["name"] == team]
    if team_hist.empty:
        return 1.0
    team_avg = team_hist["_poss"].mean()

    # .mean(), not .sum(): NBL sometimes schedules a team twice in the same
    # round (a real doubleheader, unlike NFL's one-game-per-team-per-week),
    # so summing would silently double-count those rounds' possessions and
    # inflate league_avg — confirmed via backtest (combined_adj was
    # averaging ~0.46 instead of ~1.0 before this fix).
    per_team_round = hist.groupby(["name", "round_number"])["_poss"].mean()
    league_avg = per_team_round.groupby(level=1).mean().mean() if not per_team_round.empty else team_avg

    if not league_avg:
        return 1.0
    return float(team_avg / league_avg)


def opponent_adj(team_box: pd.DataFrame, opponent: str, stat: str, season: int, round_number: int) -> float:
    hist = _trailing(team_box, season, round_number)
    if hist.empty:
        return 1.0

    # Self-join on match_id: the OTHER team's row in the same match is what
    # "name" allowed that game (their opponent's production = what they gave up).
    merged = hist.merge(hist, on="match_id", suffixes=("", "_opp"))
    merged = merged[merged["name"] != merged["name_opp"]]
    allowed_col = f"{stat}_opp"

    opp_allowed = merged[merged["name"] == opponent]
    if opp_allowed.empty:
        return 1.0
    opp_avg = opp_allowed[allowed_col].mean()

    # Same doubleheader fix as pace_adj: .mean() per (team, round), not .sum().
    league_allowed = merged.groupby(["name", "round_number"])[allowed_col].mean()
    league_avg = league_allowed.groupby(level=1).mean().mean() if not league_allowed.empty else opp_avg

    if not league_avg:
        return 1.0
    return float(opp_avg / league_avg)


def project(
    player_box: pd.DataFrame,
    team_box: pd.DataFrame,
    player_full_name: str,
    team: str,
    opponent: str,
    stat: str,
    season: int,
    round_number: int,
    role_adj: float = 1.0,
    window: int = 3,
) -> NblProjection:
    if stat not in SUPPORTED_STATS:
        raise ValueError(f"unsupported stat: {stat}. Supported: {SUPPORTED_STATS}")

    r3, games_used = recent_n_avg(player_box, player_full_name, stat, season, round_number, window)
    opp_a = opponent_adj(team_box, opponent, stat, season, round_number)
    pace_a = pace_adj(team_box, team, season, round_number)

    projection_value = r3 * opp_a * pace_a * role_adj

    return NblProjection(
        player=player_full_name,
        team=team,
        opponent=opponent,
        season=season,
        round_number=round_number,
        stat=stat,
        recent3_avg=r3,
        opponent_adj=opp_a,
        pace_adj=pace_a,
        role_adj=role_adj,
        projection=projection_value,
        games_used=games_used,
    )
