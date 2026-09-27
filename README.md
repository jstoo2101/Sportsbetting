# NFL Betting System — Odds Integration & Paper-Trading Pipeline

Paper-trading research project: project NFL player prop values, compare
against real Australian bookmaker lines, and build an evidence-backed,
immutable track record before any subscription product is considered.

**No real money is wagered anywhere in this system.** Every pick is
hypothetical, logged with timestamps, for evidence-gathering only.

## Why player props, not game lines

A 15-season backtest (2011-2025, nflverse) confirmed every generic
game-line angle (home dogs, home favorites, overs/unders, divisional
games) is break-even-to-negative at standard -110 pricing — the
game-lines market is efficient. Player props (rushing yards, receiving
yards, receptions) are where mispricing is more plausible; a real
2022-2024 check found ~0.48-0.56 correlation between a player's trailing
3-game average and next-game actual, a real but moderate signal.

## Projection model (v1)

```
Proj = Recent3GameAvg x OpponentAdj x PaceAdj x RoleAdj x WeatherAdj
```

| Factor | Source | Computed how |
|---|---|---|
| `Recent3GameAvg` | nflverse `player_stats.csv` | trailing 3-game average for the stat, strictly before the target week (no lookahead) |
| `OpponentAdj` | nflverse `player_stats.csv` | opponent's trailing stat-allowed-per-game to the relevant position group, vs league average |
| `PaceAdj` | nflverse `player_stats.csv` | team's trailing plays-per-game vs league average |
| `RoleAdj` | **manual**, analyst judgment | ±10-15% nudge for a recent snap-share/target-share trend — no reliable free data source for this yet, so it's a CLI flag (`--role-adj`), not automated |
| `WeatherAdj` | **manual**, analyst judgment | passing props only: knock 10-20% off for wind >15mph or heavy outdoor precip (`--weather-adj`) |

A pick is only a candidate when `|edge| = (Proj - BookLine) / BookLine >= 12%`
(`EDGE_THRESHOLD` in `src/betting/config.py`) **and** the direction agrees
with an actual matchup/role thesis — the threshold alone is necessary but
not sufficient, and that judgment call is intentionally not automated.

## Data sources

- [`nflverse/nfldata`](https://github.com/nflverse/nfldata) `games.csv` — every NFL game since 1999, closing lines + results, refreshed continuously including the in-progress season. Free, no key.
- [`nflverse/nflverse-data`](https://github.com/nflverse/nflverse-data) — weekly player stats, live during the season. Free, no key. **Use the per-season `stats_player_week_{season}.csv` files** (release tag `stats_player`), not the combined `player_stats.csv` asset (release tag `player_stats`) — that combined file stopped updating after the 2024 season as of this build and will silently make every projection look like historical backtest data instead of a live pick. `fetch_nflverse_data.py` auto-detects the current season from `games.csv` and pulls the right per-season files; it's already wired up correctly, this note is here so nobody "fixes" it back to the stale endpoint.
- [The Odds API](https://the-odds-api.com/) — live game lines + player prop odds, filtered to `regions=au` (Sportsbet, TAB, Ladbrokes AU, Neds). **Requires your own paid API key** — never committed to the repo.

Player prop odds are patchier than game lines: if The Odds API hasn't got
AU bookmaker coverage for a market/event yet, the pipeline says so and
returns nothing for it rather than filling the gap with US-book prices or
invented numbers.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your ODDS_API_KEY
```

## Pipeline

```bash
# 1. Pull latest nflverse data (weekly during the season)
python scripts/fetch_nflverse_data.py

# 2. Pull current odds from The Odds API (game lines + player props,
#    filtered to AU bookmakers). Check quota/rate limits at
#    https://the-odds-api.com/liveapi/guides/v4/ before automating this
#    on a schedule — player props cost one request per market per event.
python scripts/fetch_odds.py

# 3. Compute a projection and check the edge against the odds you just pulled.
#    This does NOT write to the ledger — it's a review step.
python scripts/compute_edges.py \
    --odds data/odds_cache/best_prices_latest.csv \
    --player "Dalton Schultz" --team HOU --opponent DAL \
    --stat receiving_yards --season 2026 --week 4

# 4. If the edge crosses 12% AND the direction matches your thesis, log it.
#    This is the only way to add a row to tips_log.
python scripts/log_pick.py \
    --player "Dalton Schultz" --team HOU --season 2026 --week 4 \
    --market receiving_yards --side Over --book-line 34.5 --projection 41.2 \
    --best-bookmaker sportsbet --best-price 1.91 \
    --thesis "Nico Collins out again, Schultz drew 14 targets last time"

# 5. After the game, record the outcome (this is the ONLY field update
#    the database permits — everything else about the pick is frozen).
python scripts/settle_pick.py --id 1 --status won --actual-result 47
```

## Data store & immutability

`data/db/betting.db` (SQLite) is the source of truth, versioned in git.

- `odds_snapshots` — every raw quote pulled from The Odds API, timestamped.
- `projections` — computed projection inputs/outputs, timestamped.
- `tips_log` — the paper-trading ledger. **Append-only at the database
  layer**: a trigger blocks `UPDATE`/`DELETE` on every pick field (line,
  projection, edge, thesis, stake...). The only permitted update is via
  `settle_pick()` / `scripts/settle_pick.py`, which touches only
  `status`, `actual_result`, `settled_at`. A mis-logged pick is corrected
  by logging a new row referencing the old one via `corrects_pick_id`,
  never by editing history. This is what makes the eventual track record
  auditable rather than self-reported — see `tests/` for a check that the
  triggers actually block edits.

No Excel dependency going forward: this repo's SQLite DB (with CSV
exports from `fetch_odds.py` for quick review) is the canonical source of
truth per your instruction. `NFL_Betting_System.xlsx` stays as a one-time
historical snapshot of the pre-repo backtest work; nothing here writes
back to it. If you want an Excel view of the live ledger later, that's a
straightforward export script to add on top of `tips_log` — say the word.

## Current watchlist (not yet logged — need a real odds pull first)

Two picks were being tracked before this pipeline existed. They are
**not** yet in `tips_log`: logging them would mean inventing a book line
and price, which contradicts the no-fabricated-data rule above. The
model side is live and confirmed real (see below) — the missing piece is
just your Odds API pull for the actual line and best AU price. Once you
run `fetch_odds.py` and `compute_edges.py`, log whichever still clears
12% with real numbers:

1. **Dalton Schultz (HOU TE) receiving yards, Over** — Nico Collins (HOU
   WR1) has missed 2 straight games (hamstring); Schultz drew 14 targets
   when Collins was out in Week 2. Watching Week 4 vs. Dallas.
   Confirmed against live 2026 data: Schultz's actual weeks 1-3 were 35 /
   140 / 30 receiving yards (the 140 is the Week 2 Collins-out game, 14
   targets). Trailing-3 model projection for Week 4 vs. DAL:
   **70.3 receiving yards** (`recent3_avg=68.3`, `opponent_adj=0.95`,
   `pace_adj=1.09`). Whatever HOU's book line turns out to be, this is a
   real, reproducible number, not a placeholder — run
   `compute_edges.py` once you've pulled the odds.
2. **Tutu Atwell (LAR WR2) receptions, Under** — Puka Nacua (LAR WR1) has
   missed 2 straight games, expected back Week 4 vs. Philadelphia; whoever
   absorbed his targets likely has an inflated line if the market hasn't
   repriced for his return.

## Guardrails

- Paper trading only — nothing here places real bets or touches a real
  betting account.
- Check The Odds API's and each bookmaker's terms before running any of
  this on a schedule/frequently; confirm current rate limits and usage
  terms at the-odds-api.com.
- No fabricated data — if AU bookmaker coverage isn't there for a
  market/event, the pipeline reports that plainly instead of substituting
  US-book prices or invented numbers.
- Immutable logging — see above. This matters because the eventual pitch
  is a paid subscription; the track record has to be provably real.

## Tests

```bash
pip install pytest
python -m pytest tests/
```

Covers odds parsing/best-price selection (mocked API responses — no key
needed) and the tips_log immutability triggers.
