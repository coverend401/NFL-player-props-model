# C0–C2 verification and scope record

Scientific source/protocol committed before the full experiment:
`516af13` (full SHA in experiment manifest). Immutable result:
`experiments/stage1c/c0-c2-20261113-v1`. No post-result source/protocol tuning.

## Completed checks

- Production target Python 3.14: **140 tests passed** (115 prior +25 C0–C2 tests).
- Python 3.12 reference: **134 passed, six intentional skips**. Three existing
  Stage 1B.1 and three new Stage 1C archive tests require the pinned Python 3.14
  archive runtime. This does not change production Python.
- 270 newly fitted market/year/family bundles replayed from joblib, with every
  generated forecast/probability field compared to the saved archive at tolerance
  1e-12. Seven versions cover identical 55,303 row IDs and outcomes. Frozen
  Stage 1B.1 point, interval and probability comparators match exactly.
- Source/runtime/input/baseline/payload hashing and semantic checks passed. The
  validator enforces the model matrix, pregame hypothetical thresholds, proper
  score recomputation, completed/selection/feature timestamps, evidence tier,
  scope, context probability partition and sealed period.
- New tests cover future/current outcome invariance, future rate mutation,
  effective-dated identity and aliases, late publication, verified-versus-proxy
  evidence, postseason-only refusal, sealed Parquet predicates, hand-calculated
  shrinkage/schedule adjustment and clock pace, incomplete positional totals,
  missing fixtures, byes/season boundaries, same-time batch ordering, upcoming
  fixture states without target-game outcomes, team count-mixture support/moments,
  sparse selection windows, player zero outcomes/CDF support, archive tampering
  and final-period rejection even after recomputing a payload hash.
- Existing production candidate validator and app smoke passed: nine models,
  all production predictions replayed, **780 slate rows and 18 Top Picks**.
- Existing fault-injection and rollback rehearsal passed in temporary copies;
  malformed forecasts/models were refused and a ledger marker was retained.
- New-source Ruff F checks, formatting, compile and git whitespace checks passed.
- Added CI runs the original checks plus full Stage 1C replay on Python 3.14.
  Final-head GitHub status must be checked on the review PR; local tests alone
  are not a substitute for remote CI.

## Isolation and evidence limits

Expected main: `bcb9df3ca45055ace7e7cde75cd3a9170686f1a6` (approved research-only
PR #4 merge). Before preparing this PR, main remained unchanged and the legacy
updater remained manually disabled. Production app/pricing/accounting, database
code, settings, pipeline, selected release, frozen Stage 1B/1B.1 packages/archives
and the exact dependency lock are byte-identical to main.

Active production release remains `stage1a-20261113-py314-arrow24-r2`. No Supabase,
authentication, bankroll, production secret or data-table access/change occurred.
No separate dashboard was hosted. No paid source/provider or collection job was
configured. Stage 1C is not imported by the production app. No merge/deployment
or experimental probability activation is authorised by these results.

No C3 player allocation, C4 scheme/personnel, C5 injury or C6 joint player outcome
model is implemented. Source and target identity inherit the frozen historical
benchmark's limitations; a strict contract is not a fabricated roster archive.
All new data are retrospective, with a +36h availability proxy. No genuine
historical publication archive or verified pre-decision context is asserted.
Source-lag stress is frozen-model sensitivity, not proof of true publication.

The final 2026 week-11 onward period and future seasons remain sealed. Development
and 2026 weeks 1–10 monitoring were already viewed. Results fail the primary
retention gate; they cannot justify model promotion or profitable-betting claims.
Raw downloaded bytes were cached outside the repository; committed aggregates
contain development observations only, with original URLs/hashes/receipt metadata.
Incomplete positional stats were not converted to zero.

See `STAGE1C_C0_C2_RESULTS.md` for all nine markets, year-level regressions,
calibration/interval evidence, source coverage, C2 intermediate diagnostics and
explicit retention recommendations. The small common-backbone gains must not be
misrepresented as gains against the stronger Stage 1B.1 recipe.
