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
# nflverse-data publishes weekly player_stats as dated releases; the "player_stats"
# release tag always points at the latest full-history file.
NFLVERSE_PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "player_stats/player_stats.csv"
)

ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
