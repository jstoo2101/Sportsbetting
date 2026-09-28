import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from betting import nba_projections as NP

# Three games, three teams, invented so the arithmetic is checkable by hand.
# 2026-01-15 is the target date (not included in trailing history).
TEAM_BOX = pd.DataFrame([
    {"game_id": "g1", "season": 2026, "game_date": "2026-01-01", "team_abbreviation": "A", "team_score": 100,
     "field_goals_attempted": 80, "free_throws_attempted": 20, "offensive_rebounds": 10, "total_turnovers": 12,
     "total_rebounds": 40, "assists": 22, "three_point_field_goals_made": 10},
    {"game_id": "g1", "season": 2026, "game_date": "2026-01-01", "team_abbreviation": "B", "team_score": 90,
     "field_goals_attempted": 75, "free_throws_attempted": 15, "offensive_rebounds": 8, "total_turnovers": 14,
     "total_rebounds": 38, "assists": 18, "three_point_field_goals_made": 8},
    {"game_id": "g2", "season": 2026, "game_date": "2026-01-08", "team_abbreviation": "A", "team_score": 110,
     "field_goals_attempted": 85, "free_throws_attempted": 18, "offensive_rebounds": 12, "total_turnovers": 10,
     "total_rebounds": 42, "assists": 25, "three_point_field_goals_made": 12},
    {"game_id": "g2", "season": 2026, "game_date": "2026-01-08", "team_abbreviation": "C", "team_score": 95,
     "field_goals_attempted": 78, "free_throws_attempted": 16, "offensive_rebounds": 9, "total_turnovers": 13,
     "total_rebounds": 36, "assists": 20, "three_point_field_goals_made": 9},
])

PLAYER_BOX = pd.DataFrame([
    {"game_id": "g1", "season": 2026, "game_date": "2026-01-01", "game_date_time": "2026-01-01T00:00:00",
     "athlete_id": 1, "athlete_display_name": "Star Player", "team_abbreviation": "A",
     "opponent_team_abbreviation": "B", "points": 20, "rebounds": 5, "assists": 4, "three_point_field_goals_made": 2},
    {"game_id": "g2", "season": 2026, "game_date": "2026-01-08", "game_date_time": "2026-01-08T00:00:00",
     "athlete_id": 1, "athlete_display_name": "Star Player", "team_abbreviation": "A",
     "opponent_team_abbreviation": "C", "points": 30, "rebounds": 7, "assists": 6, "three_point_field_goals_made": 4},
])


def test_recent_n_avg_uses_only_trailing_games():
    avg, n = NP.recent_n_avg(PLAYER_BOX, 1, "points", season=2026, game_date="2026-01-15")
    assert n == 2
    assert avg == 25.0  # (20 + 30) / 2


def test_recent_n_avg_excludes_future_games():
    avg, n = NP.recent_n_avg(PLAYER_BOX, 1, "points", season=2026, game_date="2026-01-08")
    assert n == 1
    assert avg == 20.0


def test_opponent_adj_uses_the_other_team_in_the_game():
    # B's only trailing game allowed A 100 points -> opp_avg = 100.
    # league_avg (per-date-across-teams, then averaged across dates):
    #   2026-01-01: A allowed 90, B allowed 100 -> mean 95
    #   2026-01-08: A allowed 95, C allowed 110 -> mean 102.5
    #   league_avg = mean(95, 102.5) = 98.75
    adj = NP.opponent_adj(TEAM_BOX, opponent="B", stat="points", season=2026, game_date="2026-01-15")
    assert round(adj, 4) == round(100 / 98.75, 4)


def test_pace_adj_reflects_own_team_possessions_not_opponents():
    a_avg = ((80 + 0.44 * 20 - 10 + 12) + (85 + 0.44 * 18 - 12 + 10)) / 2
    round1_mean = ((80 + 0.44 * 20 - 10 + 12) + (75 + 0.44 * 15 - 8 + 14)) / 2
    round2_mean = ((85 + 0.44 * 18 - 12 + 10) + (78 + 0.44 * 16 - 9 + 13)) / 2
    league_avg = (round1_mean + round2_mean) / 2
    adj = NP.pace_adj(TEAM_BOX, team="A", season=2026, game_date="2026-01-15")
    assert round(adj, 4) == round(a_avg / league_avg, 4)


def test_pace_adj_averages_not_sums_a_teams_multiple_trailing_games_same_date():
    # Same defensive check as the NBL model's doubleheader-round bug: if a
    # team appears twice for the same (team, game_date) group, .sum() would
    # double-count it and inflate league_avg. Every team here plays at an
    # identical pace, so a correct implementation gives every team pace_adj
    # == 1.0 regardless of how many rows land in one (team, date) group.
    same_date_box = pd.DataFrame([
        {"game_id": "d1", "season": 2026, "game_date": "2026-01-01", "team_abbreviation": "D",
         "field_goals_attempted": 80, "free_throws_attempted": 20, "offensive_rebounds": 10, "total_turnovers": 12},
        {"game_id": "d1", "season": 2026, "game_date": "2026-01-01", "team_abbreviation": "X",
         "field_goals_attempted": 80, "free_throws_attempted": 20, "offensive_rebounds": 10, "total_turnovers": 12},
        {"game_id": "d2", "season": 2026, "game_date": "2026-01-01", "team_abbreviation": "D",
         "field_goals_attempted": 80, "free_throws_attempted": 20, "offensive_rebounds": 10, "total_turnovers": 12},
        {"game_id": "d2", "season": 2026, "game_date": "2026-01-01", "team_abbreviation": "Y",
         "field_goals_attempted": 80, "free_throws_attempted": 20, "offensive_rebounds": 10, "total_turnovers": 12},
        {"game_id": "d3", "season": 2026, "game_date": "2026-01-08", "team_abbreviation": "E",
         "field_goals_attempted": 80, "free_throws_attempted": 20, "offensive_rebounds": 10, "total_turnovers": 12},
        {"game_id": "d3", "season": 2026, "game_date": "2026-01-08", "team_abbreviation": "Z",
         "field_goals_attempted": 80, "free_throws_attempted": 20, "offensive_rebounds": 10, "total_turnovers": 12},
    ])
    adj = NP.pace_adj(same_date_box, team="E", season=2026, game_date="2026-01-15")
    assert round(adj, 4) == 1.0


def test_project_combines_all_factors():
    proj = NP.project(
        PLAYER_BOX, TEAM_BOX,
        athlete_id=1, player_name="Star Player", team="A", opponent="B",
        stat="points", season=2026, game_date="2026-01-15",
    )
    assert proj.games_used == 2
    assert proj.recent3_avg == 25.0
    assert proj.projection == proj.recent3_avg * proj.opponent_adj * proj.pace_adj * proj.role_adj
