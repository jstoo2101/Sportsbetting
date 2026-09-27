# Multi-Sport Betting System — Odds Integration & Paper-Trading Pipeline

Paper-trading research project: project player prop values, compare
against real Australian bookmaker lines, and build an evidence-backed,
immutable track record before any subscription product is considered.
NFL is the first, fully-built sport; NBL (Australian basketball) is next,
with its stats/projection half built and its odds half waiting on The
Odds API to activate the sport for the season (see NBL section below).

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
(`EDGE_THRESHOLD` in `src/betting/config.py`) **and** a player has a full
3-game trailing window (`games_used >= RECENT_GAMES_WINDOW`) **and** the
direction agrees with an actual matchup/role thesis — the threshold alone
is necessary but not sufficient, and that judgment call is intentionally
not automated.

The games-used gate exists because early in a season (weeks 1-3) trailing-3
is really trailing-1 or trailing-2, which is a different, unvalidated thing
from what the backtest measured — and because the edge-% formula blows up
on small book lines (a 0.5-reception line for a bench player turns a tiny
absolute miss into a fake "900% edge"). Confirmed live on the season's
actual Week 3 DEN @ LA game: every player capped at 2 trailing games and
the gate correctly returned zero candidates rather than surfacing that
noise. The earliest any pick can be validly flagged is Week 4.

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

## NBL (Australian basketball) — in progress

**Status: stats + projection model built and verified against live data.
Odds integration is not built yet — blocked on The Odds API, not on us.**

### Why NBL, and why odds are on hold

The Odds API lists `basketball_nbl` as a supported sport, but as of this
build it's returning zero events/odds even though the NBL27 season started
2026-09-19 and rounds 1-2 have already been played — confirmed independently
(you checked Sportsbet directly: no NBL markets live right now, despite
having bet on NBL games in the days prior). This reads as a normal
early-season odds-market lull rather than a real gap, so the plan is to
build the half that doesn't depend on it (stats + projections) now, and
re-check `basketball_nbl` periodically until markets reappear — not to
pay for a worse alternative. The one legitimate alternative investigated
(BetsAPI) is Bet365-sourced — a single bookmaker, not a multi-book AU
comparison — so it doesn't serve the "best price across AU books" goal
this system is built around, and scraping bookmaker sites directly is
off the table per the guardrails below.

### Data source

[`JaseZiv/nblr_data`](https://github.com/JaseZiv/nblr_data) — a free,
open (GPL-3), community-maintained companion data repo to the `nblR` R
package. Same "GitHub release assets" pattern as nflverse, just `.rds`
(R-serialized) instead of `.csv`; `fetch_nbl_data.py` reads it with
`pyreadr` (no R install needed) and writes plain CSVs downstream code
reads like any other pandas source. Confirmed live and current — includes
the in-progress 2026-2027 season. Player box scores (points, rebounds,
assists, 3PM, minutes) go back to 2015-16; match results to 1979.

Two real data-quality issues were found and are patched in
`fetch_nbl_data.py`, not worked around downstream:
- `team_box`'s `points` column is 100% null for the 2025 and 2026 seasons
  (an upstream provider/schema change) — `score` holds the same value in
  every season including the broken ones (verified identical wherever
  both are populated), so it's used to patch the gap.
- Within the *same* 2026 season, "New Zealand Breakers" is used
  inconsistently — their own box-score rows say `NZ Breakers`, but every
  other team's `opp_name` reference to them says `New Zealand Breakers`.
  Left alone this silently fragments their trailing history mid-season;
  `TEAM_NAME_ALIASES` canonicalizes it before anything downstream sees it.

### Projection model (v1)

```
Proj = Recent3GameAvg x OpponentAdj x PaceAdj x RoleAdj
```

No `WeatherAdj` — NBL is played indoors. `OpponentAdj` and `PaceAdj` are
computed from **team** box scores, not player rows: in `team_box.csv`
every match has exactly two rows (one per team), so "what team X allows"
is literally the other row's own total for that match — a same-`match_id`
self-join, not a position-based estimate. That sidesteps `playing_position`
entirely, whose values are inconsistent junk across seasons/data-provider
eras (`G`, `GRD`, `Guard`, `PG/SG`, ...). `PaceAdj` uses the standard
basketball estimated-possessions formula (`FGA + 0.44*FTA - OREB + TOV`)
on the team's own box score, same idea as the NFL model's plays-per-game.

Verified against real Round 3 fixtures: Bryce Cotton (Perth Wildcats) vs.
South East Melbourne Phoenix (his actual next opponent) projects at 23.1
points / 1.5 rebounds / 5.1 assists / 3.9 threes off a real 33.0
points-per-game start through 2 rounds. `games_used` is correctly capped
at 2 this early — the same games-used gate built for NFL (see above)
applies identically here once NBL picks get wired into `edges.py`, so
nothing gets flagged until a player has a real 3-round trailing window.

### Pipeline (stats half only, for now)

```bash
python scripts/fetch_nbl_data.py   # writes data/nbl/player_box.csv, team_box.csv
```

```python
import pandas as pd
from betting import nbl_projections as NP

player = pd.read_csv("data/nbl/player_box.csv", low_memory=False)
team = pd.read_csv("data/nbl/team_box.csv", low_memory=False)

NP.project(player, team, player_full_name="Bryce Cotton", team="Perth Wildcats",
           opponent="South East Melbourne Phoenix", stat="points", season=2026, round_number=3)
```

Odds fetching, edge computation, and pick logging for NBL aren't built
yet — that's the second half, waiting on `basketball_nbl` odds to appear.

### Validation: does the model actually work?

`scripts/backtest_nbl_model.py` walk-forward tests the model exactly the
way it'd run live: holds out a full season, and for every round computes
each player's projection using ONLY rounds strictly before it (no
lookahead — this falls out of the same round-boundary logic the live
model uses), then compares to what actually happened. Same idea as the
NFL side's "0.48-0.56 correlation" validation.

```bash
python scripts/backtest_nbl_model.py --season 2025   # or 2024, 2023, ...
```

**A real bug was caught by this process, not invented for it.** The
first run showed the full model's projections centered at ~46% of the
raw trailing average instead of ~100% — `pace_adj`/`opponent_adj` grouped
by `(team, round_number)` and used `.sum()`, silently assuming at most one
game per team per round. True for NFL weeks, **false for NBL** — some
rounds are real doubleheaders, and summing two games into one round
double-counted them, inflating the league-average denominator and
systematically deflating every projection. Fixed by grouping with
`.mean()` instead (mathematically identical for NFL's one-game case,
correct for NBL's). Both factors now correctly center at ~1.00 across the
league, verified directly, and a regression test
(`test_pace_adj_averages_not_sums_a_teams_doubleheader_round`) checks this
holds going forward — confirmed it would have caught the original bug by
reverting the fix and watching it fail.

**Result, walk-forward across three complete seasons (2023, 2024, 2025):**

| Stat | corr(full model) | corr(raw trailing-3 alone) |
|---|---|---|
| points | 0.69 – 0.70 | 0.69 – 0.70 |
| rebounds | 0.61 – 0.66 | 0.62 – 0.65 |
| assists | 0.66 – 0.68 | 0.66 – 0.68 |
| three_pointers_made | 0.45 – 0.51 | 0.45 – 0.51 |

The trailing-3-game average has real, consistent predictive power —
stronger than the NFL side's validated 0.48-0.56, actually. But
`OpponentAdj` and `PaceAdj` are now honestly neutral: they neither
meaningfully help nor hurt the correlation (differences are ≤0.01 across
every stat and season, noise-level). **The signal is real; the two
adjustment factors aren't currently adding anything on top of it.** That's
a legitimate finding to sit with before wiring this into live picks —
options are to simplify the NBL model down to trailing-average-only, try
different adjustment formulations, or gather more seasons of data before
judging them. Not decided yet; flagging it rather than picking one.

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
