# Week 11 certification — exact contract gate confirmed

Local checkpoint following `67de79d`. **Stopped at Step 1's provenance gate. No source correction, forecast publication, pointer change or deployment.**

## Verified blocking requirements

`validate_bundle` in `scripts/validate_release.py` enforces all of these, in addition to the unchanged manifest hashes/source/runtime checks:

1. Every data table and every model bundle must have the candidate's `release_id` (lines 27–38 and 73–77).
2. For each model: `build_started_at <= training_as_of <= prediction_at`, and `training_cutoff < training_as_of` and `< completed_before` (lines 74–85).
3. All nine models must share one `training_as_of` (lines 96–101). Feature schemas, positions, finite residual scales and the historical training cutoff are also checked.
4. Rebuilding from candidate `player_features`, schedule, timestamped QB starters and its model files must reproduce the **entire slate**, with exact values/columns/rows after sorting, ignoring dtype only (lines 103–119).
5. Original `compute_top_picks(..., side_filter="Over")` output must also exactly match; fixture-expiry metadata must cover the generated slate (lines 120–133).

The existing trained models have the Week 10 release ID and `training_as_of=2026-11-13T17:09:40.909923Z`. A genuine fresh build on 20 November starts **after** that training timestamp. Reusing the weights may be valid for prediction, but the existing coordinated-build certification contract cannot attest that as a newly trained build. An ID rewrap alone would not resolve the training-time condition. Backdating a new build, editing training timestamps or weakening a check would misrepresent provenance and was not done.

## Focused execution of the actual validator

Added two negative-fixture tests. They copy the real bundle into a `TemporaryDirectory`, leave all nine model files byte-identical and create explicitly pending **test-only** table/build metadata. Test-fixture checksums are calculated normally. Neither fixture is an offered Week 11 slate. No manifest-validation function or validator condition is mocked/disabled.

- New release identity + frozen model files: the unmodified validator rejects with **`Mixed or legacy model`**.
- Retaining the old release identity + a genuine new build timestamp: it rejects with **`Future/stale build provenance`**.

**2 focused tests passed in 4.375 seconds**: success here means both refusals occurred as expected. The production model hashes remained unchanged. No full suite, forecast replay, new model fit or repeated previous test run was needed. These tests prove the provenance obstacle; they do not certify any Week 11 predictions.

## Existing eligibility paths and why post-filtering is unsupported

The current builder supports historical position/minimum-game/positive-recent-snap eligibility, season and upcoming-team filters, finite required features, and a timestamped **QB-only** current-starter mapping. Missing roof context is a distinct hypothetical-scenario status and is excluded from Top Picks.

There is **no** general timestamped current-roster, status/elevation or non-QB current-team input to `build_slate`, and no such artifact is supplied by the validator during replay. The 30 practice-squad exclusions cannot be replayed merely by deleting output rows. Remigio's correct HOU identity is already evidenced, but `upcoming_player_state` derives identity from the latest positive-snap performance row. A source correction must keep historical game teams intact and separate current identity from performance history. Silently changing old teams, snap values, positions or game counts to force an exclusion would falsify source inputs.

Therefore eligibility corrections must be applied to the timestamped **current eligible-player state before prediction**, with the same evidence supplied on replay. Arbitrary output-subset publication fails exact equality. The existing contract also has no replayed publication handling for the 12 unresolved roster-status rows; missing depth evidence cannot be called inactivity, nor can roster uncertainty be relabelled as roof uncertainty. No exclusion, elevation or uncertainty policy was invented here.

## State and required decision

- Current accepted Week 11 forecast count: **0**; accepted fixture coverage: **0**; Top Picks generated: **0**.
- The earlier **692 rows / 12 fixtures** remain unaffected draft coverage, not newly certified or publishable output.
- The research app still resolves the preserved Week 10 release and cannot load an accepted Week 11 bundle. No integration success is claimed.
- No further player investigation, data refresh, source-code correction or pipeline rerun followed this gate. Week 11 outcomes remain sealed.
- Production/main, models, credentials, bookmaker code, quotas and rollback points are unchanged. No SportsGameOdds calls or paid resources. Codex and provider usage balances were not queried.

To satisfy frozen-model reuse **without retraining**, an explicitly approved extension of the existing contract is needed: immutable parent-model lineage/hashes and original training timestamps, plus a timestamped current-eligibility input replayed by the same builder. Exact replay, integrity, source/runtime verification and training/history cutoff checks must remain mandatory. That changes the current contract; it was **not** assumed authorised or implemented under this assignment's prohibition on an alternative publication policy or validator bypass.
