#!/usr/bin/env python3
"""Walk-forward validation of the NBL projection model.

Holds out one full season (default: the last COMPLETE one) and, round by
round, computes a real projection for every player using ONLY data that
would have been available at that point in time (this falls out for free
from nbl_projections' round < target filtering — no lookahead is possible
by construction), then compares it to what the player actually did.

This is the same check the NFL side ran to get its "0.48-0.56 correlation"
number — the point isn't to backtest bets (we have no historical NBL odds
to backtest against), it's to answer: does Recent3Avg x OpponentAdj x
PaceAdj actually predict next-game production better than noise, and does
it beat or hurt vs. just using the raw trailing average alone?

Usage:
    python scripts/backtest_nbl_model.py                  # defaults to season 2025
    python scripts/backtest_nbl_model.py --season 2024
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from betting import nbl_projections as NP  # noqa: E402


def walk_forward(player_box: pd.DataFrame, team_box: pd.DataFrame, season: int, min_games: int = 3, window: int = 3) -> pd.DataFrame:
    season_rows = player_box[player_box["season"] == season].copy()
    season_rows["round_number"] = pd.to_numeric(season_rows["round_number"], errors="coerce")
    season_rows = season_rows.dropna(subset=["round_number"])
    season_rows["full_name"] = season_rows["first_name"].fillna("") + " " + season_rows["family_name"].fillna("")
    # Same tie-break as nbl_projections.recent_n_avg: a round can carry more
    # than one game (confirmed: NBL schedules real doubleheader rounds), so
    # round_number alone doesn't fully order them.
    season_rows = season_rows.sort_values(["full_name", "round_number", "match_time_utc"])

    # nbl_projections.recent_n_avg treats a whole ROUND as the trailing
    # boundary (round_number < target), not each individual game — so for a
    # doubleheader round's second game, its trailing-3 is identical to the
    # first game's (both exclude every game in that round, not just the one
    # before it row-wise). A naive shift(1).rolling(window) is WRONG here:
    # it would let the round's first game leak into the second game's
    # window. Confirmed by spot-checking against the scalar function directly
    # (3 of 8 random rows mismatched before this fix). Precomputing each
    # player's own small sorted history once — instead of re-scanning the
    # whole season and rebuilding full_name on every call, which is what
    # made the fully-scalar version too slow to finish — keeps this exact
    # while still being fast.
    player_histories = {name: g.reset_index(drop=True) for name, g in season_rows.groupby("full_name")}

    rounds = sorted(season_rows["round_number"].unique())
    teams = season_rows["team_name"].unique()

    results = []
    for target_round in rounds:
        target_round = int(target_round)
        round_rows = season_rows[season_rows["round_number"] == target_round]
        if round_rows.empty:
            continue

        # opponent_adj/pace_adj don't depend on the player, only on
        # (team, stat, round) — compute each exactly once per round instead
        # of once per player.
        pace_by_team = {team_name: NP.pace_adj(team_box, team_name, season, target_round) for team_name in teams}
        opp_adj_by_team_stat = {
            (team_name, stat): NP.opponent_adj(team_box, team_name, stat, season, target_round)
            for team_name in teams for stat in NP.SUPPORTED_STATS
        }

        seen_this_round: dict[tuple[str, str], tuple[float, int]] = {}
        for _, row in round_rows.iterrows():
            hist = player_histories[row["full_name"]]
            hist_before = hist[hist["round_number"] < target_round]
            for stat in NP.SUPPORTED_STATS:
                cache_key = (row["full_name"], stat)
                if cache_key in seen_this_round:
                    r3, games_used = seen_this_round[cache_key]
                else:
                    recent = hist_before[stat].tail(window)
                    r3, games_used = (float(recent.mean()), len(recent)) if not recent.empty else (0.0, 0)
                    seen_this_round[cache_key] = (r3, games_used)
                if games_used < min_games:
                    continue
                opp_a = opp_adj_by_team_stat[(row["opp_name"], stat)]
                pace_a = pace_by_team[row["team_name"]]
                results.append({
                    "round": target_round, "player": row["full_name"], "team": row["team_name"],
                    "opponent": row["opp_name"], "stat": stat,
                    "recent3_avg": r3, "projection": r3 * opp_a * pace_a,
                    "actual": row[stat],
                })
    return pd.DataFrame(results)


def summarize(df: pd.DataFrame) -> None:
    for stat in NP.SUPPORTED_STATS:
        sub = df[df["stat"] == stat]
        if len(sub) < 10:
            print(f"{stat:22s} n={len(sub):5d}  (too few observations to summarize)")
            continue
        corr_full = sub["projection"].corr(sub["actual"])
        corr_raw = sub["recent3_avg"].corr(sub["actual"])
        mae_full = (sub["projection"] - sub["actual"]).abs().mean()
        mae_raw = (sub["recent3_avg"] - sub["actual"]).abs().mean()
        print(f"{stat:22s} n={len(sub):5d}  "
              f"corr(full_model)={corr_full:+.3f}  corr(raw_trailing3)={corr_raw:+.3f}  "
              f"MAE(full)={mae_full:6.2f}  MAE(raw)={mae_raw:6.2f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025, help="held-out season to forward-test (default: 2025, the last complete season)")
    parser.add_argument("--min-games", type=int, default=3, help="same games_used gate used live — default matches production")
    parser.add_argument("--out", type=Path, default=None, help="optional path to save the full player-game-level results as CSV")
    args = parser.parse_args()

    player = pd.read_csv("data/nbl/player_box.csv", low_memory=False)
    team = pd.read_csv("data/nbl/team_box.csv", low_memory=False)

    print(f"Walk-forward testing season {args.season} (min_games={args.min_games})...")
    df = walk_forward(player, team, args.season, args.min_games)
    print(f"Collected {len(df)} (player, round, stat) observations with a full trailing window.\n")

    summarize(df)

    if args.out:
        df.to_csv(args.out, index=False)
        print(f"\nSaved full results -> {args.out}")


if __name__ == "__main__":
    main()
