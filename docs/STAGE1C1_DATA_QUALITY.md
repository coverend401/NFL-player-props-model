# Stage 1C.1 data-quality findings

The reconciled input bundle is `research_inputs/stage1c1/reconciled-20261114-v2`. It uses the same hash-checked 2019–2026 development play-by-play snapshots as Stage 1C and the frozen Stage 1A player-feature snapshot. The final evaluation period is filtered before Parquet materialisation. No live data, evaluation outcomes, frozen player-history features or production files are repaired by this experiment.

## What reconciliation establishes

Player identities are joined by game, canonical franchise and stable player ID. Positions come from the same game's frozen player record, never a current roster or a later season. Complete event ledgers can establish zero opportunities for an observed offensive participant even when no statistical box row exists. They cannot establish that an absent or inactive player participated.

| Positional category | Original complete team-games | Reconciled complete | Recovered |
| --- | ---: | ---: | ---: |
| Passing | 4,016 | 4,016 | 0 |
| RB receiving | 2,756 | 4,012 | 1,256 |
| TE receiving | 1,439 | 4,008 | 2,569 |
| WR receiving | 2,008 | 4,010 | 2,002 |
| QB rushing | 3,883 | 4,016 | 133 |
| RB rushing | 2,756 | 4,015 | 1,259 |

The original QB rushing source had only 4,008 group rows; the 4,016-game grid includes eight missing groups reconstructed only when the ledger is complete. Recovered groups require the full category's opportunity, production and completion/catch credits to reconcile. Passing 4,016/4,016 is preserved legacy coverage, not a claim that all passing ledgers pass the stricter audit (4,015 do).

Among active offensive participants with absent box observations there are 106 QB, 475 RB, 3,028 TE and 2,092 WR records. Reconciliation supports zero targets for all of these records, zero carries except one RB and one TE unresolved record, and zero passing attempts except one WR unresolved record. There are no recovered positive opportunities in these missing-box cohorts. See `stage1c1-results/missing_box_opportunity_audit.csv` for field-level counts. These are auxiliary diagnostic facts; no target zeros are manufactured or added to the scored population. Team mismatches stay unknown.

## Remaining credit inconsistencies

Seventeen team-games retain differences between structured event credits and published team totals. Absolute aggregate differences are one passing attempt, one carry, 35 rushing yards and 105 receiving yards; completion, passing-yard, target and catch totals agree. Category-strict ledgers cover 4,015 passing, 4,015 rushing and 4,001 receiving team-games.

HOU 2024 week 15 contains a carry/rushing-yard discrepancy that the structured actor fields do not resolve. PIT 2025 week 2 contains a passing-attempt discrepancy. Fifteen receiving discrepancies involve incomplete structured credit across multi-lateral chains. A single lateral-receiver field cannot reconstruct every actor in those chains. We do not infer the missing credits from a guess or force totals to balance. Multiple categories may refer to the same team-game; these counts are not independent samples.

All parsed player-credit IDs match same-game identities in this snapshot, and the unresolved parsed-event table is empty. That does **not** prove that every real credit was represented: the residual totals identify structured-feed limitations even when all parsed IDs match. A future credit-resolution patch would require explicit fixtures and a separately versioned source.

## Evidence and timing limits

Team and event data share an upstream play-by-play source; reconciliation checks internal consistency, not independent official certification. Published box totals are the benchmark here, not a separate licensed audited feed. Player-position observations and revised play-by-play are retrospective. A 36-hour availability proxy is conservative for replay but does not establish actual historical publication by T−60. No post-season participation or coverage release is treated as in-season knowledge.

The factorial experiments deliberately retain identical frozen player-history features and evaluation populations. They test reconciliation of defensive positional aggregates; they do not test repaired individual opportunity histories or a new player-allocation engine. Team-volume C2 inputs are identical before and after positional reconciliation. These limits matter before attributing any forecast change to improved data quality or recommending C3.
