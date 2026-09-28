#!/usr/bin/env python3
"""Walk-forward validation of the NBA projection model — same method as
scripts/backtest_nbl_model.py, adapted for date-based (not round-based)
ordering: holds out one full season and, for every game date, computes
each player's projection using ONLY strictly-prior games, then compares to
what actually happened.

Usage:
    python scripts/backtest_nba_model.py                  # defaults to season 2026
    python scripts/backtest_nba_model.py --season 2025
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from betting import nba_projections as NP  # noqa: E402


def walk_forward(player_box: pd.DataFrame, team_box: pd.DataFrame, season: int, min_games: int = 3, window: int = 3) -> pd.DataFrame:
    season_rows = player_box[player_box["season"] == season].copy()
    season_rows = season_rows.sort_values(["athlete_id", "game_date", "game_date_time"])
    player_histories = {pid: g.reset_index(drop=True) for pid, g in season_rows.groupby("athlete_id")}

    # opponent_adj/pace_adj's underlying self-join and per-team aggregation
    # don't need to be redone per date — the self-join itself is a fixed,
    # cheap (2 rows per game) operation on the WHOLE season, and only the
    # trailing-window filter afterward actually varies with target_date.
    # Doing that self-join and possession calc fresh for every (date, team,
    # stat) combo — ~170 dates x ~20 teams x 4 stats — was the actual
    # bottleneck (the naive version didn't finish in 2 minutes). Hoisting it
    # out of the date loop cuts thousands of redundant identical merges down
    # to one.
    season_team = team_box[team_box["season"] == season].copy()
    season_team["_poss"] = NP._team_possessions(season_team)
    merged = season_team.merge(season_team, on="game_id", suffixes=("", "_opp"))
    merged = merged[merged["team_abbreviation"] != merged["team_abbreviation_opp"]]

    # league_avg (for both pace and each stat's opponent-allowed) only
    # depends on (date, stat) — NOT on which specific team we're about to
    # look up — so computing it once per team on top of once per date was
    # still ~20x more groupbys than necessary (one call per team playing
    # that date, all recomputing the same league-wide number). Hoisting it
    # to once per date turned this from not finishing in 2 minutes into a
    # few seconds.
    dates = sorted(season_rows["game_date"].unique())
    results = []
    for target_date in dates:
        date_rows = season_rows[season_rows["game_date"] == target_date]
        if date_rows.empty:
            continue
        teams_today = date_rows["team_abbreviation"].unique()

        hist_team = season_team[season_team["game_date"] < target_date]
        per_team_date_poss = hist_team.groupby(["team_abbreviation", "game_date"])["_poss"].mean()
        league_avg_pace = per_team_date_poss.groupby(level=1).mean().mean() if not per_team_date_poss.empty else 1.0
        pace_by_team = {}
        for t in teams_today:
            team_hist = hist_team[hist_team["team_abbreviation"] == t]
            team_avg = team_hist["_poss"].mean() if not team_hist.empty else league_avg_pace
            pace_by_team[t] = float(team_avg / league_avg_pace) if league_avg_pace else 1.0

        hist_merged = merged[merged["game_date"] < target_date]
        opp_adj_by_team_stat = {}
        for stat in NP.SUPPORTED_STATS:
            allowed_col = f"{NP.STAT_TO_TEAM_COL[stat]}_opp"
            league_allowed = hist_merged.groupby(["team_abbreviation", "game_date"])[allowed_col].mean()
            league_avg_allowed = league_allowed.groupby(level=1).mean().mean() if not league_allowed.empty else 1.0
            for t in teams_today:
                opp_allowed = hist_merged[hist_merged["team_abbreviation"] == t]
                opp_avg = opp_allowed[allowed_col].mean() if not opp_allowed.empty else league_avg_allowed
                opp_adj_by_team_stat[(t, stat)] = float(opp_avg / league_avg_allowed) if league_avg_allowed else 1.0

        for _, row in date_rows.iterrows():
            hist = player_histories[row["athlete_id"]]
            hist_before = hist[hist["game_date"] < target_date]
            for stat in NP.SUPPORTED_STATS:
                recent = hist_before[stat].tail(window)
                if len(recent) < min_games:
                    continue
                r3 = float(recent.mean())
                opp_a = opp_adj_by_team_stat[(row["opponent_team_abbreviation"], stat)]
                pace_a = pace_by_team[row["team_abbreviation"]]
                results.append({
                    "date": target_date, "player": row["athlete_display_name"], "team": row["team_abbreviation"],
                    "opponent": row["opponent_team_abbreviation"], "stat": stat,
                    "recent3_avg": r3, "projection": r3 * opp_a * pace_a,
                    "actual": row[stat],
                })
    return pd.DataFrame(results)


def summarize(df: pd.DataFrame) -> None:
    for stat in NP.SUPPORTED_STATS:
        sub = df[df["stat"] == stat]
        if len(sub) < 10:
            print(f"{stat:30s} n={len(sub):5d}  (too few observations to summarize)")
            continue
        corr_full = sub["projection"].corr(sub["actual"])
        corr_raw = sub["recent3_avg"].corr(sub["actual"])
        mae_full = (sub["projection"] - sub["actual"]).abs().mean()
        mae_raw = (sub["recent3_avg"] - sub["actual"]).abs().mean()
        print(f"{stat:30s} n={len(sub):5d}  "
              f"corr(full_model)={corr_full:+.3f}  corr(raw_trailing3)={corr_raw:+.3f}  "
              f"MAE(full)={mae_full:6.2f}  MAE(raw)={mae_raw:6.2f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026, help="held-out ESPN season label to forward-test (default: 2026, the 2025-26 season)")
    parser.add_argument("--min-games", type=int, default=3)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    player = pd.read_csv("data/nba/player_box.csv", low_memory=False)
    team = pd.read_csv("data/nba/team_box.csv", low_memory=False)

    print(f"Walk-forward testing season {args.season} (min_games={args.min_games})...")
    df = walk_forward(player, team, args.season, args.min_games)
    print(f"Collected {len(df)} (player, date, stat) observations with a full trailing window.\n")

    summarize(df)

    if args.out:
        df.to_csv(args.out, index=False)
        print(f"\nSaved full results -> {args.out}")


if __name__ == "__main__":
    main()
