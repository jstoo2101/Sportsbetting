#!/usr/bin/env python3
"""Download the NBL data this system depends on, from JaseZiv/nblr_data —
a free, open (GPL-3), community-maintained companion data repo to the nblR
R package. Same "GitHub release assets" pattern as nflverse, just .rds
(R serialized) instead of .csv, read here via pyreadr (no R install needed).

Produces two CSVs downstream code reads like any other pandas source:
  - data/nbl/player_box.csv  (one row per player per match, with round_number
    and match date attached via a join against match results)
  - data/nbl/team_box.csv    (one row per team per match, same join — used
    for the pace/possessions estimate)

Re-run this during the season to pick up new rounds.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyreadr
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from betting import config  # noqa: E402


def download_rds(url: str, dest: Path) -> pd.DataFrame:
    print(f"Downloading {url}")
    resp = requests.get(url, timeout=60, allow_redirects=True)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    df = pyreadr.read_r(str(dest))[None]
    print(f"  -> {dest} ({len(df):,} rows)")
    return df


def season_start_year(season_label: str) -> int:
    """'2026-2027' -> 2026. Matches the season INTEGER column the DB schema
    already uses for NFL; NBL's season just isn't a single calendar year."""
    return int(str(season_label)[:4])


# The source data isn't internally consistent about team names: within the
# same 2026 season, a team's own box-score row and other teams' opp_name
# references to it can use different strings for the SAME team (confirmed:
# "NZ Breakers" as their own team_name/name, "New Zealand Breakers" as
# everyone else's opp_name for them). Left unnormalized, this silently
# fragments a team's trailing history mid-season. Canonicalize to whichever
# form is used consistently as the team's own name in team_box.
TEAM_NAME_ALIASES = {
    "New Zealand Breakers": "NZ Breakers",
}

TEAM_NAME_COLUMNS = {
    "player_box": ["team_name", "opp_name"],
    "team_box": ["name", "opp_name"],
}


def normalize_team_names(df: pd.DataFrame, columns: list[str]) -> None:
    for col in columns:
        if col in df.columns:
            df[col] = df[col].replace(TEAM_NAME_ALIASES)


def minutes_to_float(m: str) -> float:
    """'19:14' -> 19.23. Bad/missing values ('', '00:00', NaN) -> 0.0."""
    if not isinstance(m, str) or ":" not in m:
        return 0.0
    mins, secs = m.split(":")
    try:
        return int(mins) + int(secs) / 60
    except ValueError:
        return 0.0


def main() -> None:
    tmp_dir = config.NBL_DIR / "_raw"
    player = download_rds(config.NBL_BOX_PLAYER_URL, tmp_dir / "box_player.rds")
    team = download_rds(config.NBL_BOX_TEAM_URL, tmp_dir / "box_team.rds")
    results = download_rds(config.NBL_RESULTS_WIDE_URL, tmp_dir / "results_wide.rds")

    round_lookup = results[["match_id", "round_number", "match_time_utc"]].drop_duplicates("match_id")

    player = player.merge(round_lookup, on="match_id", how="left")
    team = team.merge(round_lookup, on="match_id", how="left")

    for df in (player, team):
        df["season"] = df["season"].apply(season_start_year)

    normalize_team_names(player, TEAM_NAME_COLUMNS["player_box"])
    normalize_team_names(team, TEAM_NAME_COLUMNS["team_box"])

    player["minutes_played"] = player["minutes"].apply(minutes_to_float)

    # team_box's 'points' column is 100% null for the 2025 and 2026 seasons
    # (a provider/schema change upstream) — 'score' is the same value under
    # both eras (verified identical wherever 'points' is populated) and stays
    # fully populated throughout, so it's the reliable source to patch from.
    broken_points = team["points"].isna() & team["score"].notna()
    if broken_points.any():
        print(f"Patching {broken_points.sum()} team_box rows where 'points' is null but 'score' isn't "
              f"(known gap in seasons 2025+) using 'score' instead.")
        team.loc[broken_points, "points"] = team.loc[broken_points, "score"]

    missing_round = player["round_number"].isna().sum()
    if missing_round:
        print(f"Warning: {missing_round} player-box rows have no matching round_number "
              f"(match_id not found in results_wide) — these will be dropped from trailing calcs "
              f"if used, since there's no way to order them chronologically.")

    config.NBL_DIR.mkdir(parents=True, exist_ok=True)
    player_dest = config.NBL_DIR / "player_box.csv"
    team_dest = config.NBL_DIR / "team_box.csv"
    player.to_csv(player_dest, index=False)
    team.to_csv(team_dest, index=False)
    print(f"  -> saved {player_dest} ({len(player):,} rows, seasons {sorted(player['season'].unique())})")
    print(f"  -> saved {team_dest} ({len(team):,} rows)")


if __name__ == "__main__":
    main()
