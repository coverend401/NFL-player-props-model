# Weekly learning — first operational demonstration

Dry run: **2026 Week 9**, 15 completed fixtures, 708 player-market forecasts, 103 observed zero outcomes, all 708 reconciled. This is archived chronological replay, not forecasts genuinely published before those historical games.

The current Week 11 forecasts were separately frozen prospectively on **2026-11-20 at 22:48:42 UTC**, before all recorded T−60 cutoffs. Original forecasts/Top Picks and all nine model hashes remain unchanged.

## Week 9 measured forecast errors

| Market | N | MAE | RMSE | Bias | Zeros |
|---|---:|---:|---:|---:|---:|
| completions | 32 | 4.380 | 5.993 | +1.026 | 1 |
| passing_attempts | 32 | 6.907 | 9.174 | +0.121 | 1 |
| passing_yards | 32 | 62.611 | 77.617 | -1.987 | 1 |
| qb_rushing_attempts | 32 | 1.898 | 2.688 | +0.038 | 1 |
| qb_rushing_yards | 32 | 12.979 | 17.830 | +0.298 | 4 |
| receiving_yards | 209 | 17.832 | 26.140 | -2.169 | 44 |
| receptions | 209 | 1.196 | 1.564 | +0.081 | 41 |
| rushing_attempts | 65 | 3.556 | 4.586 | -0.431 | 5 |
| rushing_yards | 65 | 18.041 | 22.336 | +0.047 | 5 |

Positive bias means overprediction. Team and position breakdowns are in the immutable JSON report and dashboard. Cached PBP supplies at-snap lead/trail fractions for all 30 team-games; the experimental final-margin category Brier is **0.5574**, a different target from in-game state occupancy.

Recurring associative diagnostics (counts are overlapping player-market records, not independent causal cases): 454 workload deviations, 293 missed experimental final-margin categories, 174 run/pass-balance deviations, 120 team-opportunity volume deviations, 66 playing-time changes and 52 forecast-implied share deviations. No injury or coaching cause is asserted.

## Prespecified bias correction — 2026 Weeks 1–10 validation

Half the 2022–24 mean residual is added by market. The holdout has 6,869 outcomes over 150 games, previously inspected in research. No coefficients were selected from these holdout results.

| Market | Baseline MAE | Candidate MAE | Baseline RMSE | Candidate RMSE | Gain % |
|---|---:|---:|---:|---:|---:|
| completions | 5.599 | 5.598 | 7.158 | 7.139 | +0.018 |
| passing_attempts | 8.254 | 8.269 | 10.786 | 10.800 | -0.181 |
| passing_yards | 67.861 | 67.822 | 84.249 | 84.316 | +0.058 |
| qb_rushing_attempts | 1.773 | 1.770 | 2.256 | 2.254 | +0.152 |
| qb_rushing_yards | 11.271 | 11.230 | 15.014 | 14.998 | +0.362 |
| receiving_yards | 19.258 | 19.251 | 27.156 | 27.158 | +0.038 |
| receptions | 1.437 | 1.429 | 1.907 | 1.910 | +0.590 |
| rushing_attempts | 3.889 | 3.889 | 5.087 | 5.086 | -0.009 |
| rushing_yards | 21.498 | 21.431 | 29.133 | 29.147 | +0.310 |

**Decision: RETAIN_CHAMPION.** Primary-market gain is far below 2%, passing-attempt error and some probability scores regress, no fresh independent holdout exists, the historical baseline is a chronological proxy, and there is no compatible certified bias-postprocessor release. Small significant exploratory differences in other markets do not justify selective promotion. All Brier/log-loss diagnostics, paired intervals and Holm decisions are archived in `weekly_learning_state/candidates/`.

## Forecast readiness

Existing Week 11 bundle exactly replayed: 618 forecasts / 568 complete / 50 labelled roof scenarios / 12 fixtures / 22 Top Picks / 22 eligible Top 2 rows. The first dry run reused the existing Week 11 release. A later cached-source rehearsal generated a separate certified Week 11 bundle without selecting it. Week 12 was **not generated**: reading Week 11 results and admitting them to the existing inference validator remain blocked by the sealed-period policy.

The source/feature/certification adapter passed a cached-source Week 11 end-to-end rehearsal; its fresh Week 12 run awaits that approval. The scheduled workflow is prepared but not registered on main, and therefore not active. See `weekly_learning/README.md` for commands, free-tier safeguards, exact remaining steps and rollback.

No production/main changes, model retraining, bookmaker calls, quota writes, new services or paid resources.

## Validation and delivery checks

- **420 tests passed** in the single full regression run (362.367 seconds).
- **14 focused learning tests passed**, covering immutable writes, concurrency,
  missing-versus-zero results, chronology, seals, holdout reuse, promotion rejection,
  a synthetic certified-promotion/rollback path and the real research entrypoint.
- Four final focused safety checks passed after hardening publication/source paths:
  report-write failure preserves the prior research pointer; successful certification
  alone advances it; corrupted/unapproved/future/stale source snapshots are rejected.
- Read-only replay reproduced **all 708 rows exactly** and all nine markets' point
  errors and hypothetical probability scores exactly. The genuine capture matches
  the original forecast and Top Picks bytes; all nine original model hashes and
  actual pre-T−60 capture timestamps were verified.
- An idempotent rerun left every learning state file unchanged, with no new test or
  holdout reservation. Original dry-run execution code is preserved in checkpoint
  `28f17f2`; subsequent hardening is separately versioned, not written over that audit.
- Real Chromium at **390px** passed Weekly Learning navigation, rejected-candidate
  display and blocker visibility with no exception or horizontal overflow. Hosted
  authenticated verification is not claimed.
- Existing public-repository status was verified. The workflow uses standard free
  Linux jobs and no additional Actions artifact or cache storage. No new financial
  service, paid account or quota dependency was created.

The schedule is **not active on the research branch**: GitHub requires default-
branch registration, which needs separate approval. The requested operational
settlement exception has not been approved; Week 11 outcomes remain unread and
Week 12 certification remains blocked. No production or main update occurred.

## Subsequent cached-source rehearsal and calendar hardening

`research_inference_releases/weekly-offline-rehearsal-20261120` was generated with
the existing nine frozen models and already downloaded official source files. It
passed the unchanged `research_frozen_model_inference_v1` contract with 618 rows,
568 complete forecasts, 12 fixtures, 22 Top Picks and exact replay. It was **not
selected**; no active forecast or production default changed. The source adapter
fixed a pandas depth-chart name collision caught by this real pipeline run.

Source provenance explicitly records 20 unmapped positive offensive snap rows
(C: 8, OL: 1, RB: 1, WR: 10), using the existing core's handling of unlinked IDs.
No identities, team assignments or zero outcomes were invented. Current eligible
player coverage and unresolved/ineligible decisions still pass the original
versioned eligibility/replay rules. This is a known coverage limitation, not a
claim of complete NFL participation data.

13 additional focused archive tests passed after pinning the immutable Week 11
fixture and historical test clock. Football evidence now reads the explicitly
selected immutable bundle and verifies feature/schedule hashes, so changing the
current weekly default does not invalidate archive regressions. No frozen
benchmark, original inference validator or production pricing code changed.
