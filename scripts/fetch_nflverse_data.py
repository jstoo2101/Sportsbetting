#!/usr/bin/env python3
"""Download the two nflverse source files this system depends on.

Both are free, public, and require no API key:
  - games.csv: every NFL game since 1999 (closing lines + results)
  - player_stats.csv: weekly player stats since 1999

Re-run this weekly during the season to pick up the latest week's stats.
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from betting import config  # noqa: E402


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    print(f"  -> saved {dest} ({len(resp.content):,} bytes)")


def main() -> None:
    download(config.NFLVERSE_GAMES_URL, config.NFLVERSE_DIR / "games.csv")
    download(
        config.NFLVERSE_PLAYER_STATS_URL,
        config.NFLVERSE_DIR / "player_stats.csv",
    )


if __name__ == "__main__":
    main()
