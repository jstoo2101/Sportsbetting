#!/usr/bin/env python3
"""Download the NBA data this system depends on, from sportsdataverse-data
(same publishing family as nflverse — hoopR's load_nba_player_box() /
load_nba_team_box() read from these same release assets). Free, no key.

ESPN labels a season by its ENDING calendar year: the season that tips off
Oct 2026 and runs through June 2027 is season "2027", not "2026". This
script auto-detects which season label(s) to fetch from today's date.

Produces two CSVs downstream code reads like any other pandas source:
  - data/nba/player_box.csv
  - data/nba/team_box.csv

Both are pre-filtered to season_type == REGULAR_SEASON_TYPE and with the
All-Star exhibition game removed (see EXHIBITION_TEAM_ABBREVIATIONS below)
so nothing downstream has to know about either quirk.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pyreadr
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from betting import config  # noqa: E402

# ESPN's season_type codes: 1=preseason, 2=regular season, 3=postseason.
# There's a real trap here: the All-Star Game is ALSO tagged 2 (regular
# season), not given its own code — confirmed directly against the live
# 2026 data (three fake "teams", below, all showing season_type == 2 on
# the actual All-Star Weekend date). Filtering on season_type alone is not
# enough; the exhibition teams must be excluded explicitly too.
REGULAR_SEASON_TYPE = 2
EXHIBITION_TEAM_ABBREVIATIONS = {"STARS", "STRIPES", "WORLD"}  # All-Star Game / Rising Stars


def current_season_label(today: date | None = None) -> int:
    """NBA seasons start in October — from July onward, the season about to
    start (or just started) is labeled by the year it will END in."""
    today = today or date.today()
    return today.year + 1 if today.month >= 7 else today.year


def download_rds(url: str, dest: Path) -> pd.DataFrame | None:
    print(f"Downloading {url}")
    resp = requests.get(url, timeout=60, allow_redirects=True)
    if resp.status_code == 404:
        print(f"  -> not available yet (404) — season hasn't started publishing data")
        return None
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    df = pyreadr.read_r(str(dest))[None]
    print(f"  -> {dest} ({len(df):,} rows)")
    return df


def clean(df: pd.DataFrame, team_abbrev_col: str, opp_abbrev_col: str) -> pd.DataFrame:
    df = df[df["season_type"] == REGULAR_SEASON_TYPE]
    df = df[~df[team_abbrev_col].isin(EXHIBITION_TEAM_ABBREVIATIONS)]
    df = df[~df[opp_abbrev_col].isin(EXHIBITION_TEAM_ABBREVIATIONS)]
    if "athlete_id" in df.columns:
        # A small number of rows (inactive/"COACH'S DECISION" roster slots)
        # carry no real athlete_id or name at all — confirmed on live data
        # (33 of 64,883 rows). Not a real player-game, drop them.
        df = df[df["athlete_id"].notna()]
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seasons", type=int, nargs="+", default=None,
        help="explicit ESPN season label(s) to fetch, e.g. --seasons 2026 2027 "
             "(default: auto-detect from today's date)",
    )
    args = parser.parse_args()

    seasons = args.seasons or [current_season_label()]

    tmp_dir = config.NBA_DIR / "_raw"
    player_frames, team_frames = [], []
    for season in seasons:
        player_df = download_rds(
            config.NBA_PLAYER_BOX_URL_TEMPLATE.format(season=season), tmp_dir / f"player_box_{season}.rds"
        )
        team_df = download_rds(
            config.NBA_TEAM_BOX_URL_TEMPLATE.format(season=season), tmp_dir / f"team_box_{season}.rds"
        )
        if player_df is not None:
            player_frames.append(player_df)
        if team_df is not None:
            team_frames.append(team_df)

    if not player_frames or not team_frames:
        print(f"No NBA data available yet for season(s) {seasons}. "
              f"The upcoming season's files appear once ESPN starts publishing games for it.")
        return

    player = clean(pd.concat(player_frames, ignore_index=True), "team_abbreviation", "opponent_team_abbreviation")
    team = clean(pd.concat(team_frames, ignore_index=True), "team_abbreviation", "opponent_team_abbreviation")

    config.NBA_DIR.mkdir(parents=True, exist_ok=True)
    player_dest = config.NBA_DIR / "player_box.csv"
    team_dest = config.NBA_DIR / "team_box.csv"
    player.to_csv(player_dest, index=False)
    team.to_csv(team_dest, index=False)
    print(f"  -> saved {player_dest} ({len(player):,} rows, seasons {seasons})")
    print(f"  -> saved {team_dest} ({len(team):,} rows)")


if __name__ == "__main__":
    main()
