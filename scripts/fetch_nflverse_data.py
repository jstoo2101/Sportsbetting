#!/usr/bin/env python3
"""Download the nflverse source files this system depends on.

  - games.csv: every NFL game since 1999 (closing lines + results),
    refreshed continuously including the in-progress season.
  - player_stats.csv: weekly player stats, built by concatenating the
    live per-season "stats_player_week_{season}.csv" files (the combined
    all-seasons "player_stats.csv" release asset lags behind — it stopped
    updating after 2024 as of this build, so we don't use it for anything
    current).

Re-run this weekly during the season to pick up the latest week's stats.

Usage:
    python scripts/fetch_nflverse_data.py                # auto-detect current season
    python scripts/fetch_nflverse_data.py --seasons 2024 2025 2026
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from betting import config  # noqa: E402


def download(url: str, dest: Path | None = None) -> bytes:
    print(f"Downloading {url}")
    resp = requests.get(url, timeout=60, allow_redirects=True)
    resp.raise_for_status()
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        print(f"  -> saved {dest} ({len(resp.content):,} bytes)")
    return resp.content


def detect_current_season(games_csv: Path) -> int:
    """The latest season in games.csv that has at least one played game."""
    games = pd.read_csv(games_csv)
    played = games[games["home_score"].notna()]
    return int(played["season"].max())


def fetch_player_stats(seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        url = config.NFLVERSE_STATS_PLAYER_WEEK_URL_TEMPLATE.format(season=season)
        try:
            content = download(url)
        except requests.HTTPError as e:
            print(f"  skipping {season}: {e}")
            continue
        from io import BytesIO

        df = pd.read_csv(BytesIO(content))
        frames.append(df)

    if not frames:
        raise RuntimeError(f"No player stats fetched for seasons {seasons}")

    combined = pd.concat(frames, ignore_index=True)
    # Normalize the one column nflverse renamed between the old combined
    # release and the new per-season files, so downstream code (which
    # expects `recent_team`, matching the original player_stats.csv schema)
    # doesn't need to know which source file a row came from.
    if "team" in combined.columns and "recent_team" not in combined.columns:
        combined = combined.rename(columns={"team": "recent_team"})
    return combined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seasons", type=int, nargs="+", default=None,
        help="explicit seasons to fetch, e.g. --seasons 2024 2025 2026 "
             "(default: auto-detect current season from games.csv and pull "
             f"the last {config.NFLVERSE_SEASONS_WINDOW} seasons)",
    )
    args = parser.parse_args()

    games_dest = config.NFLVERSE_DIR / "games.csv"
    download(config.NFLVERSE_GAMES_URL, games_dest)

    if args.seasons:
        seasons = sorted(args.seasons)
    else:
        current_season = detect_current_season(games_dest)
        seasons = list(range(current_season - config.NFLVERSE_SEASONS_WINDOW + 1, current_season + 1))
        print(f"Auto-detected current season: {current_season} (fetching {seasons})")

    player_stats = fetch_player_stats(seasons)
    dest = config.NFLVERSE_DIR / "player_stats.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    player_stats.to_csv(dest, index=False)
    print(f"  -> saved {dest} ({len(player_stats):,} rows, seasons {seasons})")


if __name__ == "__main__":
    main()
