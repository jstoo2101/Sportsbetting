import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from betting import nbl_projections as NP

# Two rounds, three teams, all matches invented so the arithmetic is checkable
# by hand. Round 3 is the target (not included in trailing history).
TEAM_BOX = pd.DataFrame([
    # round 1: A beats B 100-90
    {"match_id": "m1", "season": 2026, "round_number": "1", "name": "A", "points": 100,
     "field_goals_attempted": 80, "free_throws_attempted": 20, "rebounds_offensive": 10, "turnovers": 12},
    {"match_id": "m1", "season": 2026, "round_number": "1", "name": "B", "points": 90,
     "field_goals_attempted": 75, "free_throws_attempted": 15, "rebounds_offensive": 8, "turnovers": 14},
    # round 2: A beats C 110-95
    {"match_id": "m2", "season": 2026, "round_number": "2", "name": "A", "points": 110,
     "field_goals_attempted": 85, "free_throws_attempted": 18, "rebounds_offensive": 12, "turnovers": 10},
    {"match_id": "m2", "season": 2026, "round_number": "2", "name": "C", "points": 95,
     "field_goals_attempted": 78, "free_throws_attempted": 16, "rebounds_offensive": 9, "turnovers": 13},
])

PLAYER_BOX = pd.DataFrame([
    {"match_id": "m1", "season": 2026, "round_number": "1", "match_time_utc": "2026-01-01T00:00:00",
     "first_name": "Star", "family_name": "Player", "team_name": "A", "opp_name": "B", "points": 20},
    {"match_id": "m2", "season": 2026, "round_number": "2", "match_time_utc": "2026-01-08T00:00:00",
     "first_name": "Star", "family_name": "Player", "team_name": "A", "opp_name": "C", "points": 30},
])


def test_recent_n_avg_uses_only_trailing_rounds():
    avg, n = NP.recent_n_avg(PLAYER_BOX, "Star Player", "points", season=2026, round_number=3)
    assert n == 2
    assert avg == 25.0  # (20 + 30) / 2


def test_recent_n_avg_excludes_future_rounds():
    # Projecting for round 2 should only see round 1.
    avg, n = NP.recent_n_avg(PLAYER_BOX, "Star Player", "points", season=2026, round_number=2)
    assert n == 1
    assert avg == 20.0


def test_opponent_adj_uses_the_other_team_in_the_match():
    # B's only trailing game (round 1) allowed A 100 points -> opp_avg = 100.
    # League average allowed is computed per-round-across-teams, then
    # averaged across rounds (so a round with more games doesn't dominate):
    #   round 1: A allowed 90, B allowed 100 -> mean 95
    #   round 2: A allowed 95, C allowed 110 -> mean 102.5
    #   league_avg = mean(95, 102.5) = 98.75
    adj = NP.opponent_adj(TEAM_BOX, opponent="B", stat="points", season=2026, round_number=3)
    assert round(adj, 4) == round(100 / 98.75, 4)


def test_pace_adj_reflects_own_team_possessions_not_opponents():
    # A's own possessions: round1 = 80 + 0.44*20 - 10 + 12 = 90.8
    #                      round2 = 85 + 0.44*18 - 12 + 10 = 90.92
    #                      A's average = 90.86
    # League average is also per-round-across-teams then averaged:
    #   round 1: A=90.8, B=75+0.44*15-8+14=87.6 -> mean 89.2
    #   round 2: A=90.92, C=78+0.44*16-9+13=89.04 -> mean 89.98
    #   league_avg = mean(89.2, 89.98) = 89.59
    adj = NP.pace_adj(TEAM_BOX, team="A", season=2026, round_number=3)
    a_avg = ((80 + 0.44 * 20 - 10 + 12) + (85 + 0.44 * 18 - 12 + 10)) / 2
    round1_mean = ((80 + 0.44 * 20 - 10 + 12) + (75 + 0.44 * 15 - 8 + 14)) / 2
    round2_mean = ((85 + 0.44 * 18 - 12 + 10) + (78 + 0.44 * 16 - 9 + 13)) / 2
    league_avg = (round1_mean + round2_mean) / 2
    assert round(adj, 4) == round(a_avg / league_avg, 4)


def test_project_combines_all_factors():
    proj = NP.project(
        PLAYER_BOX, TEAM_BOX,
        player_full_name="Star Player", team="A", opponent="B",
        stat="points", season=2026, round_number=3,
    )
    assert proj.games_used == 2
    assert proj.recent3_avg == 25.0
    assert proj.projection == proj.recent3_avg * proj.opponent_adj * proj.pace_adj * proj.role_adj
