# Court Script

NBA game, stat and player-prop analyzer. The NBA counterpart to
[Game Script](https://github.com/Drilium/game-script) (NFL) and
[Pitch Script](https://github.com/Drilium/pitch-script) (soccer).
A free portfolio project; nothing here is sold.

**Status: phase 1, data proof.** The site is not built yet.

## The idea

NBA props are driven by minutes and by who is on the floor. Every projection
is built as minutes x per-minute rate x matchup and pace adjustment, and the
minutes are rebuilt whenever the injury report changes.

## Phases

1. Data proof: confirm which sources respond from GitHub, build the pipeline. (now)
2. Core site: Tonight, players, teams, game logs, defense-allowed, compare.
3. Minutes and injuries: injury wire, rotations, with/without teammate splits.
4. Projections and props: all markets, best props, rest and blowout adjustments.
5. Simulator and combos: possession-based simulator, combo pricing, ladders.
6. Board and learning: matchup board, nightly report card, self-learning.
7. Extras: defender matchups, shot zones, referees, first basket, fantasy.

## Data source check

`probe_sources.py` tests every candidate source (NBA live data feed, NBA stats
site, the official injury report, ESPN, bulk history on GitHub) and writes
`PROBE.md`. The "Check which data sources respond" workflow runs it on a
GitHub runner, because that is where the daily pipeline will run.

Run it again: **Actions -> Check which data sources respond -> Run workflow**.
Locally: `python3 probe_sources.py`.
