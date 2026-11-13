# Stage 1A final pre-merge review

Reviewed original PR head `de61892691507fa292fe9676488c3b91c7de7495` against baseline `0c6029002be0820c0502d957372d5261610ba927`. Corrections remain on the same development branch. No merge, deployment, production workflow dispatch or Stage 1B implementation is included.

## Recommendation

The hardened code is suitable for controlled research/paper evaluation after a coordinated artifact refresh. Do not merge it as an unattended update to an auto-deployed production branch while the old forecast/model files remain in use. Runtime readability is not semantic compatibility. Live-betting readiness is not established: selection/calibration, distribution, accounting and risk-control findings from the audit remain out of scope.

## Exact explanation of 1,270 → 689

This is the frozen-model comparison at `2026-11-12T20:00:00Z`, using the archived sources whose SHA-256 hashes are in `stage1a-validation.json`. Neither implementation received a QB1 override. These counts include backups and unconfirmed players; they are not counts of bookmaker-offered or validated eligible bets. All 689 retained rows were already in the baseline; 581 rows were removed.

Each removed row is assigned one primary reason in order: missing participating history; season/team restriction; pregame eligibility/position; fixture context; opponent defense; missing recent core history; other required features. A row can have additional missing fields, so counts below must not be read as independent causes.

| Market | Baseline | Original PR | Roof/context | Recent statistics | Pregame eligibility | Prior-season only | No verified participation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Completions | 51 | 30 | 14 | 6 | 1 | 0 | 0 |
| Passing Attempts | 51 | 30 | 14 | 6 | 1 | 0 | 0 |
| Passing Yards | 51 | 30 | 14 | 6 | 1 | 0 | 0 |
| QB Rushing Attempts | 51 | 30 | 14 | 6 | 1 | 0 | 0 |
| QB Rushing Yards | 51 | 30 | 14 | 6 | 1 | 0 | 0 |
| Receiving Yards | 388 | 200 | 106 | 69 | 8 | 5 | 0 |
| Receptions | 395 | 201 | 107 | 72 | 9 | 6 | 0 |
| Rushing Attempts | 120 | 69 | 25 | 13 | 10 | 2 | 1 |
| Rushing Yards | 112 | 69 | 25 | 12 | 4 | 2 | 0 |
| **Total** | **1,270** | **689** | **333** | **196** | **36** | **15** | **1** |

Every fixture-context exclusion in this comparison is the `indoor` feature. There are no additional primary defense/auxiliary exclusions. Four upcoming retractable-roof venues had unknown roof state: KC–ATL (Mercedes-Benz Stadium), MIA–IND (Lucas Oil Stadium), LA–ARI (State Farm Stadium), SF–DAL (AT&T Stadium). Assuming those games were outdoors, as the baseline effectively did, was not justified. Dropping all their otherwise complete forecasts was unnecessarily restrictive. The initial report incorrectly framed the reduction mainly as missing player-history coverage; this review corrects that interpretation.

The per-player/per-market evidence, exact missing features and last participation week are in `stage1a-final-review-exclusions.csv`; machine-readable totals are in `stage1a-final-review.json`.

## Legitimate players and corrections

- Seven QB1s in the timestamp-filtered depth-chart snapshot lost Passing Yards projections primarily to roof context: Matthew Stafford, Dak Prescott, Jacoby Brissett, Patrick Mahomes, Daniel Jones, Brock Purdy and Michael Penix Jr. Established non-QBs such as Travis Kelce and CeeDee Lamb were also affected. These are genuine forecast-coverage losses, not proof that their props were unavailable.
- Unknown roof now produces separate indoor/outdoor model scenarios, a low/high range and an explicitly exploratory midpoint. It does not invent a roof observation or a statistical outcome. The midpoint is an unweighted sensitivity summary, not an estimated roof probability or calibrated mixture forecast.
- Such rows carry `projection_status=roof_scenarios_only`, remain visible in the slate, and are blocked from pricing, probability displays and Top Picks. Known-roof forecast calculations are unchanged. This recovers useful forecast information without silently turning missing roof status into zero.
- Of the 333 primary roof exclusions, 249 have otherwise complete inputs and are restored as scenarios. The other 84 also lack recent statistics and remain withheld. The frozen comparison now has **689 complete + 249 scenario-only = 938 displayed projections**, not 938 priced predictions.
- The remaining 332 withheld rows break down as **280 incomplete recent histories, 36 pregame eligibility failures, 15 prior-season-only histories and one without verified offensive participation**. The 280 includes the 84 whose first exclusion was roof context.
- Incomplete-history exclusions include established players such as Jonnu Smith, Tyler Conklin, David Njoku and Josh Palmer. Missing participating-game outcomes cannot safely be restored as zeros or skipped to manufacture complete last-three/last-five windows. These players remain a real coverage limitation. No missing-data fallback model was added in this stage.
- A returning QB can now use prior-season history after Week 1, or a corrected current team, when a timestamped QB1 snapshot confirms his role/team. The previous season gate ran before that confirmation and could incorrectly discard him. Regression coverage includes a returning/traded QB. Unconfirmed older players are not indiscriminately revived.
- The 15 prior-season-only contracts in this cohort are non-QBs, including Kene Nwangwu, British Brooks, Kenny Yeboah, Irvin Charles, Xavier Restrepo and Ke'Shawn Williams. Some have later special-teams/no-offensive-snap records. These sources do not prove a current offensive role, active-game designation or offered sportsbook contract; they remain withheld rather than being called inactive or a void.

| Market | Complete after review | Roof scenarios after review | Displayed total |
|---|---:|---:|---:|
| Completions | 30 | 13 | 43 |
| Passing Attempts | 30 | 13 | 43 |
| Passing Yards | 30 | 13 | 43 |
| QB Rushing Attempts | 30 | 13 | 43 |
| QB Rushing Yards | 30 | 13 | 43 |
| Receiving Yards | 200 | 72 | 272 |
| Receptions | 201 | 72 | 273 |
| Rushing Attempts | 69 | 20 | 89 |
| Rushing Yards | 69 | 20 | 89 |
| **Total** | **689** | **249** | **938** |

## Training cutoffs and normal weekly operation

A concrete weekly failure was verified: a Monday 20:15 EST kickoff is Tuesday 01:15 UTC, so the eight-hour proxy becomes Tuesday 09:15 UTC. The original Tuesday 09:00 job could train on that scored game because feature building/training only checked for a nonmissing completion time, then reject its own model at the live slate step because its declared training cutoff was in the future.

Corrections:

1. Feature building excludes records with availability at or after its explicit `data_cutoff` (default current UTC).
2. Real model fitting applies a strict `training_as_of` filter, even if the input file already contains later records. The training CLI shares one timestamp across markets. The model stores both `training_as_of` and the maximum completion/availability timestamp of outcomes actually fitted.
3. Forecasting retains the strict requirement `model.training_cutoff < completed_before <= prediction_at`. Equality and future-dated models are rejected; provenance is not invented for legacy bundles. Matching `feature_timing_version=stage1a` is required by default.
4. The scheduled job moves to **Tuesday 12:00 UTC**, providing a buffer after ordinary Monday-game proxy availability. Late/manual runs still filter unavailable observations safely; arbitrary feed publication delays are not guaranteed away by a cron time.
5. The CLI selects the depth-chart **NFL season from the upcoming fixture**, not the calendar year. This fixes January forecasts for the previous NFL season.

Tests cover the exact Tuesday 09:00/09:15 case, strict equality, actual model fitting with an extreme future-labelled row, cutoff metadata, and January fixture-season selection. A fresh nine-market fit and default live generation succeeded without the diagnostic bypass flags; every model satisfied `training_cutoff < training_as_of < live_prediction_at`.

These guards prevent future game outcomes being fitted or included in a forecast state. They do not prove point-in-time correctness of revised provider auxiliary data or replace archived historical lines/rosters. A backtest using today’s revised sources is still not certified leakage-free. Existing model-selection bias also remains.

## Production compatibility and coordinated refresh

- All nine existing production joblib files remain loadable in the tested runtime. The upgraded Streamlit app rendered the existing bundled artifacts successfully and now shows an explicit legacy-artifact warning.
- Those nine files have no training-cutoff/feature-timing provenance. They are therefore **not accepted for fresh Stage 1A slate generation**. This is intentional fail-closed behaviour, not a request to weaken cutoff checks.
- The saved legacy slate remains readable but is not corrected merely by updating Python source. Do not treat its old projections as newly corrected forecasts.
- Before production cutover, run `update_data.py`, `build_features.py`, `train_all_markets.py`, then `build_slate.py` in an isolated staging copy using the deployment’s matching Python/dependency versions. Verify all expected model files, their timing metadata, data cutoffs, slate statuses and app behaviour. Review the regenerated feature/model/slate/Top Picks set together and release it as one coherent artifact update.
- No production binaries were replaced by this review. Matching dependencies and coherent artifact cutover remain deployment prerequisites; the current unpinned requirements are not a guarantee of future pickle compatibility.

## Eight-hour proxy: material limits and safeguards

- It is an availability approximation, not observed final-whistle or provider-publication time. It can delay usable data and is not sufficient to certify suspended/abandoned fixtures or unusually long delays.
- It assumes the schedule kickoff is accurate and interprets nflverse kickoff times in America/New_York with DST conversion. Explicit `kickoff_at`, `completed_at` and `stats_available_at` should be preferred when available.
- Explicit non-final `game_status`/`status` now excludes a scored suspended/live fixture. Impossible completion-before-kickoff input is rejected. A stats-availability timestamp can no longer substitute for a missing explicit completion timestamp.
- Default nflverse schedules lack explicit final status and observed completion/publication timestamps, so that residual uncertainty remains. Supplying a verified final/availability feed is the stronger remedy; changing eight hours to another arbitrary duration does not establish finality.
- In ordinary live operation, only already-observed source rows and strict past cutoffs are used. Historical replay additionally needs genuine point-in-time source snapshots.

## Validation and remaining blockers

- **36 local automated tests passed**, including 12 additions covering the final-review defects and scenario UI. No failed/skipped local test remains.
- Fresh isolated feature building passed the existing 72 manual comparisons across 12 players; all nine markets retrained and default live slate generation succeeded. The final-review fit reused the bundled weekly-player snapshot while refreshing auxiliary/participation/team sources, preserving the audit population.
- The live run produced **848 rows: 634 complete and 214 roof scenarios**, with 20 Top Picks drawn only from complete rows. Its current QB1 snapshot and retrained weights differ from the frozen 1,270-row diagnostic, so these counts must not be mixed.
- All nine regenerated complete-market app scenarios passed. A regenerated roof-scenario app case suppressed probabilities/pricing. Actual legacy artifact loading/rendering also passed.
- Remote Python 3.11/3.12 CI results for the review commit are reported separately in PR #1. No live-betting performance improvement is claimed.
- Remaining blockers for an unattended production merge: a reviewed coordinated artifact refresh/cutover and matching deployment dependencies. Remaining live-betting blockers include unresolved histories and roof states, incomplete availability/roster archives, and the untouched validation/calibration/accounting/risk-control audit findings.
