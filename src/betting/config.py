"""Central configuration: paths, thresholds, and env-derived settings.

All paths are relative to the repo root so scripts work the same whether
run from the repo root or from within scripts/.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
NFLVERSE_DIR = DATA_DIR / "nflverse"
NBL_DIR = DATA_DIR / "nbl"
ODDS_CACHE_DIR = DATA_DIR / "odds_cache"
DB_PATH = DATA_DIR / "db" / "betting.db"

load_dotenv(REPO_ROOT / ".env")

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
ODDS_API_REGION = os.environ.get("ODDS_API_REGION", "au")
ODDS_API_AU_BOOKMAKERS = [
    b.strip()
    for b in os.environ.get(
        "ODDS_API_AU_BOOKMAKERS", "sportsbet,tab,ladbrokes_au,neds"
    ).split(",")
    if b.strip()
]

# Betting system parameters (see project brief — validated against
# 2011-2025 nflverse backtest and 2022-2024 player-prop correlation check).
EDGE_THRESHOLD = 0.12  # minimum |edge| to flag a pick
UNIT_SIZE_AUD = 5.00  # flat paper-trading stake per pick
RECENT_GAMES_WINDOW = 3

NFLVERSE_GAMES_URL = (
    "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
)

# nflverse-data's combined "player_stats.csv" release asset (single file, all
# seasons) lags well behind the season and should NOT be relied on for
# current-week data — as of this build it stopped updating after the 2024
# season. The "stats_player" release's per-season files
# (stats_player_week_{season}.csv) are what's actually kept live during the
# season (confirmed updating through the current in-progress season). Use
# these; fetch_nflverse_data.py concatenates the seasons it needs.
NFLVERSE_STATS_PLAYER_WEEK_URL_TEMPLATE = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_week_{season}.csv"
)
# How many trailing seasons (including the current one) to pull by default.
NFLVERSE_SEASONS_WINDOW = 2

ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"

# NBL data: JaseZiv/nblr_data is a free, open (GPL-3), community-maintained
# companion data repo to the nblR R package — same "GitHub release assets"
# pattern as nflverse, just .rds (R serialized) instead of .csv. Confirmed
# live and current: includes the 2026-2027 season, which started 2026-09-19.
# No key needed. Player box scores go back to 2015-16; match results to 1979.
NBL_DATA_RELEASE_BASE_URL = "https://github.com/JaseZiv/nblr_data/releases/download"
NBL_BOX_PLAYER_URL = f"{NBL_DATA_RELEASE_BASE_URL}/box_player/box_player.rds"
NBL_BOX_TEAM_URL = f"{NBL_DATA_RELEASE_BASE_URL}/box_team/box_team.rds"
NBL_RESULTS_WIDE_URL = f"{NBL_DATA_RELEASE_BASE_URL}/match_results/results_wide.rds"
