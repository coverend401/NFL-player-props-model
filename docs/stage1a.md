# Stage 1A: eligibility and forecast timing

> The [final pre-merge review](stage1a-final-review.md) supersedes the original coverage interpretation and documents subsequent hardening. The report below preserves the initial PR snapshot; the current code separately labels roof scenarios.

Implemented on `stage-1a-eligibility-feature-timing` against audited commit `0c6029002be0820c0502d957372d5261610ba927`. No deployment, merge, or tracked data/model replacement is included in this change. Regenerated artifacts were validated in an isolated copy.

## Eligibility and observation policy

- Pregame candidates use the market position, at least three prior verified offensive-participation games, and positive prior recent offensive snap share. Actual current-game targets/carries/attempts never determine candidacy.
- Outcome admissibility is separate: positive recorded offensive snaps and a nonmissing target are required. Observed zero outcomes are retained. The forecasts are conditional on offensive participation; this does not assert universal sportsbook eligibility.
- A zero offensive snap share is labelled `no_offensive_snaps`, not “inactive” or “void”. Missing snap coverage is `unknown_participation`. Neither contributes an assumed zero training outcome or player-history game.
- Snap-only records enter the panel with `stats_observed=False` and missing statistical outcomes. Missing core outcomes occupy a participating-game window and invalidate the affected last-three/last-five features instead of being replaced by older games. Career averages still describe available observed outcomes; they are not complete-career ground truth.
- Confirmed historical inactive designations and bookmaker-specific void/start/participation rules are not available in these sources. These remain unknown and are not inferred from missing statistics.
- Official team-stat totals supply opponent-defense outcomes, avoiding incomplete sums of individual player rows. Historical opponent features exclude the target game; upcoming defense states include the latest available completed game. The fallback for old snapshots uses observed player sums and cannot certify completeness.

## Missing-source investigation

The independent snap source contains positive-offensive-snap player-games absent from the weekly stats source:

| Snap position | Missing statistical observations |
|---|---:|
| QB | 106 |
| RB | 475 |
| WR | 2,090 |
| TE | 3,028 |

There are also 120 positive-snap source records without a GSIS mapping. They are reported and excluded, not guessed. The full pipeline reports 218 unmapped snap records including records with no offensive snaps. Mapping uses IDs, not display names.

The full observation panel increases from 133,353 to 185,820 rows. This includes non-model positions and no-offensive-snap observations. A larger panel does not mean more usable training outcomes.

## Dataset comparison

Counts refer to unique player/season/week records across all available regular seasons. Added/removed counts compare exact membership, not simply the net change. Removal includes insufficient verified history, unknown/no offensive participation, missing current outcomes, and incomplete recent history. The JSON report contains disjoint exclusion categories and before/after membership by position for every market.

| Market | Before | After | Added | Removed | Retained zero outcomes |
|---|---:|---:|---:|---:|---:|
| passing_yards | 4,110 | 4,019 | 110 | 201 | 152 |
| passing_attempts | 4,144 | 4,059 | 125 | 210 | 125 |
| completions | 4,110 | 4,019 | 110 | 201 | 148 |
| rushing_yards | 8,641 | 8,232 | 523 | 932 | 605 |
| rushing_attempts | 8,665 | 8,240 | 529 | 954 | 529 |
| qb_rushing_yards | 3,785 | 4,055 | 484 | 214 | 611 |
| qb_rushing_attempts | 3,787 | 4,059 | 486 | 214 | 486 |
| receiving_yards | 28,778 | 25,132 | 2,734 | 6,380 | 4,530 |
| receptions | 28,829 | 25,206 | 2,783 | 6,406 | 4,424 |

## Prediction timing and replay contract

- All prediction and completed-game cutoffs are explicit UTC timestamps. `completed_before` cannot exceed `prediction_at`.
- Completed-history selection requires scored fixtures and availability strictly before the cutoff. Future outcomes and precomputed future rolling features are not inputs to the reconstructed state.
- Player features share one calculator for entering-game training rows and inclusive upcoming states. Genuine zero games count; byes do not create rows. Career history carries across season boundaries. Opening-week slates can use prior-season history.
- nflverse schedules do not include observed final-whistle timestamps. The fallback uses kickoff in America/New_York converted to UTC plus eight hours, with final scores required. `completion_time_basis=kickoff_plus_8h_proxy` makes the approximation explicit. Supplied `completed_at` and `stats_available_at` are supported. This proxy can delay inclusion and cannot certify unusual suspended/extended fixtures or true publication timing.
- Historical feature construction fails on overlapping/unavailable prior games rather than using unfinished outcomes.
- Upcoming selection uses kickoff time, not today’s knowledge of eventual scores. Already-started fixtures are excluded; a historical future fixture remains selectable even if today’s file contains its result.
- Default slate generation requires timestamped schedule/line context and, when supplied, timestamped QB starter snapshots. Later/unknown game context becomes missing and cannot feed the existing context-dependent models. The CLI timestamps freshly fetched context; replay callers must provide archived snapshots.
- New model bundles record `training_cutoff` and reject forecasts whose declared completed-game cutoff is not after their training outcomes. Legacy models without that provenance are rejected by default. `allow_unverified_models` and `allow_unverified_context` exist only for the explicitly labelled frozen-model diagnostic; they must not be used to claim valid backtesting.
- Historical closing-line features retain the existing kickoff-time assumption. Earlier-week replay and revisions in upstream auxiliary datasets require genuine point-in-time snapshots. This change prevents future game outcomes entering feature state; it does not manufacture an archive of what upstream providers knew at historical times.
- Streamlit lookup and engine use the same slate prediction. Missing upcoming projections produce an unavailable message rather than replaying a historical entering-game row. Existing tabs and deployed file formats remain readable.

## Performance diagnostics — no improvement claim

For each market a fixed Ridge(alpha=1) model is fitted on seasons before 2025 using the old or corrected training population. Both are evaluated on exactly the same 2025 player-games present in both datasets. This is a paired diagnostic on a previously inspected season, not an untouched holdout, inference of significance, or betting backtest. It omits added-only and removed-only test cases. Existing model selection and in-sample uncertainty procedures remain for Stage 1B.

| Market | Common 2025 games | Before MAE | After MAE |
|---|---:|---:|---:|
| passing_yards | 559 | 65.864 | 65.811 |
| passing_attempts | 560 | 7.781 | 7.776 |
| completions | 559 | 5.333 | 5.355 |
| rushing_yards | 1,102 | 22.604 | 22.427 |
| rushing_attempts | 1,102 | 3.678 | 3.653 |
| qb_rushing_yards | 512 | 12.281 | 12.125 |
| qb_rushing_attempts | 512 | 1.682 | 1.666 |
| receiving_yards | 3,115 | 19.793 | 19.749 |
| receptions | 3,118 | 1.458 | 1.464 |

Errors move in both directions. No predictive or betting improvement is established.

The controlled feature/coverage comparison reuses identical frozen model weights at 2026-11-12T20:00:00Z, with no QB starter override in either implementation: 1,270 baseline versus 689 corrected projections, with 689 common contracts. Both historical context and legacy model provenance are explicitly unverified for this diagnostic. Mean absolute projection changes (stat units, not accuracy changes):

| Market | Mean absolute change |
|---|---:|
| Completions | 0.857 |
| Passing Attempts | 1.267 |
| Passing Yards | 10.600 |
| QB Rushing Attempts | 0.273 |
| QB Rushing Yards | 1.740 |
| Receiving Yards | 2.010 |
| Receptions | 0.155 |
| Rushing Attempts | 0.710 |
| Rushing Yards | 2.799 |

A separate full source-refresh pipeline regenerated all nine models and produced 629 live Week 10 projections and 20 Top Picks. Its live QB starter snapshot and regenerated model weights differ from the controlled comparison, so its row count is reported separately.

## Validation

- 24 automated regression tests passed on Python 3.12, including manual history, zeros, byes, season boundaries, missing outcomes, completed-game cutoffs, future-result perturbation, future-trained models, replay context, team totals, empty slates, and Streamlit consistency.
- The manual pipeline leakage check passed 72 comparisons across 12 players.
- The existing update-data, feature-build, nine-market training, slate-build and Top Picks pipeline completed in `/tmp/nfl-stage1a/pipeline`; source data and trained artifacts in the checkout were left unchanged.
- AppTest rendered each of the nine regenerated markets and accepted representative odds without exceptions. The Streamlit server returned a successful health response and root HTML.
- Static checks for the new modules/tests and `git diff --check` passed. CI is configured for Python 3.11 and 3.12; remote CI results are separate from these local checks.
- Earlier test/pipeline failures exposed fixture assumptions and the old manual check’s treatment of no-snap games; these were corrected and the affected checks rerun. No unresolved local test failure remains.

## Reproducing the comparison

Use the repository root and its installed requirements. Capture these public nflreadpy snapshots into a separate directory: `load_schedules(True)` → `schedules.parquet`; `load_players()` → `players.parquet`; `load_snap_counts(list(range(2019, 2027)))` → `snaps.parquet`; and `load_team_stats(list(range(2019, 2027)))` → `team_stats.parquet` (convert each to pandas and save without an index). Source hashes for this run are in `stage1a-validation.json`. The report freezes auxiliary measurements at the audited bundled feature snapshot to isolate code changes from later upstream revisions. Future source refreshes can change the numbers.

```bash
python -m unittest discover -s tests -v
python scripts/validate_stage1a.py --sources /path/to/snapshots --output /tmp/stage1a-results --prediction-at 2026-11-12T20:00:00Z
```

For a future authorised artifact refresh, run the existing four scripts in their documented order: `update_data.py`, `build_features.py`, `train_all_markets.py`, `build_slate.py`. These overwrite bundled data and models; use an isolated copy for review. Regenerate the full set together: default slate generation requires the new training-cutoff metadata. This PR deliberately does not replace the deployed artifacts or trigger a production data workflow.

## Remaining limits and review decisions

- Review the conservative participation policy and eight-hour availability proxy. Actual historical inactive/void classification still requires additional authoritative data and bookmaker rules.
- Missing statistical observations are not recovered as zero; this deliberately reduces forecast coverage for incomplete histories. Improved source reconciliation is needed before restoring those forecasts.
- Historical roster changes, long injury absences, retired players, display-name identity in the UI, and complete point-in-time source archives remain limited.
- Probability distributions, calibration, model-selection bias, stake/exposure controls, parlay settlement and performance-accounting audit findings are unchanged. No Stage 1B work, deployment or merge is included.
- Regenerated models demonstrate execution, not validated live betting value. An untouched forward evaluation and real historical prices are still required.
