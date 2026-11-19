# Experiment termination audit (B)

The original official `results.csv` remains **exactly 14 columns**. We have not
changed the meanings of `result`, `error`, or the existing `draws` count.

For every new match, the runner also appends a companion file beside it:
`<name>_termination.csv`, for example `smoke_G1_termination.csv`.
The companion fields are: `group, seed, game_id, result, plies, termination`.
They join to the main file by `(group, seed, game_id)`.

- `rules`: game ended according to chess rules. `result=1/2-1/2` is a **rules draw**.
- `ply_limit`: game stopped at the configured safety cap. `result=1/2-1/2`
  is a **truncated match**, not evidence of a natural draw.
- `engine_error`: an AI failed and forfeited.
- `unknown`: old result rows, or mock engines, that cannot reliably tell why
  the game ended. Old unannotated data **cannot be retroactively classified**.

The runner adds summary keys `rule_draws`, `ply_limits`, `unknown_draws`,
`engine_errors`, and `termination_csv`. For backward compatibility it keeps
`draws` as the raw count of matches whose `result` is `1/2-1/2`.

**Analysis rule for F**: Do not report the raw `draws` as genuine drawn games.
Join the two CSVs and separate natural draws, truncated matches, engine errors,
and unclassified legacy rows. Report denominators and exclusion rules.

Both files are needed for analysis. Do not delete the audit file or share only
`results.csv`. If a process crashes between writing the two files, a completed
main row without an audit row will be flagged as `unknown` on resume. These two
separate CSVs are not atomic. Do not reuse a single results path for different
configurations with the same `(group, seed, game_id)`; use separate output names.
