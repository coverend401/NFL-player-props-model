# Sunday game-script experiment: 20 November 2026

**Decision: do not activate player adjustments.** All nine earlier-selection gates rejected the adjustment. The certified Week 11 release, nine models, probabilities and Top Picks remain unchanged. Hubbard remains **17.1 carries**.

## Historical design

- Team results: 2000–2026 scores already in the schedule; authoritative pass-attempt/carry totals begin in 2019. Missing older workload values are not zero-filled. All workload histories used for the 2022–2026 evaluations are complete; 2026 has no missing team-volume rows.
- Teams: chronological T−60 decisions, last-eight-game team states, Ridge margin model trained only on earlier available outcomes, with a 36-hour availability proxy. Final-margin probabilities use earlier out-of-sample residuals, never the game being forecast.
- Player baseline: archived Stage 1B chronological point models. The actual November-trained live nine models cannot be used retrospectively for Weeks 1–10 without leakage. Archived models are reused, not retrained. Updated features remain pregame.
- Adjustment: residual Ridge fit on 2022–24, strength selected on 2025 from the preregistered 0 / 0.25 / 0.5 / 1 choices. Minimum selection gain 2%. No parameters changed in response to 2026 results.
- 2026 holdout: all 150 completed games in Weeks 1–10 and 6,869 eligible player-market outcomes, including 991 genuine observed zeros. Both arms use identical player-game populations. Participation is established for scoring; missing observations and inactive players are not converted to zeros.
- These data were inspected by prior research. They are held out from this experiment’s fitting/selection, but are **not a fresh independent test**. Historical publication/roster snapshots remain unverified; revised data with a lag proxy are not evidence of live point-in-time availability.
- Final margin below −7 / within ±7 / above +7 is an outcome scenario, **not in-game lead/trail occupancy**. Conditional workloads are associations, not causal scenario effects or a coherent teammate allocation model.

## All-market 2026 results

The full-strength column reports the prespecified candidate that was rejected by earlier selection. It is diagnostic and must not be retrospectively chosen from these holdout results. The selected model is unchanged in every market. Paired intervals resample whole games, retaining teammates together.

| Market | N | Baseline MAE | Full-strength MAE | Baseline RMSE | Full-strength RMSE | Baseline bias | Full-strength bias | 95% MAE delta |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| passing_yards | 311 | 67.861 | 69.075 | 84.249 | 86.608 | +1.264 | +0.968 | [-0.937, +3.513] |
| passing_attempts | 311 | 8.254 | 8.234 | 10.786 | 10.797 | -0.196 | -0.930 | [-0.146, +0.094] |
| completions | 311 | 5.599 | 5.660 | 7.158 | 7.159 | +0.541 | -0.291 | [-0.038, +0.152] |
| rushing_yards | 639 | 21.498 | 21.331 | 29.133 | 29.012 | -0.880 | -1.598 | [-0.385, +0.028] |
| rushing_attempts | 639 | 3.889 | 3.857 | 5.087 | 5.073 | -0.446 | -0.435 | [-0.065, -0.001] |
| qb_rushing_yards | 311 | 11.271 | 11.127 | 15.014 | 14.812 | +1.433 | +1.208 | [-0.247, -0.053] |
| qb_rushing_attempts | 311 | 1.773 | 1.762 | 2.256 | 2.240 | +0.235 | +0.218 | [-0.020, -0.001] |
| receiving_yards | 2018 | 19.258 | 19.214 | 27.156 | 27.127 | -1.476 | -1.559 | [-0.076, -0.009] |
| receptions | 2018 | 1.437 | 1.419 | 1.907 | 1.914 | -0.025 | -0.177 | [-0.026, -0.010] |

All selected-model errors equal the baseline exactly. Small diagnostic gains do not meet the 2% rule; passing yards worsens. Some exploratory paired intervals exclude zero, but multiple markets/candidates and reused development data prohibit selecting those apparent winners. All candidate strengths, weekly metrics, selection sizes and historical season-level team metrics are retained in the hashed artifacts.

## Win and final-margin calibration

For 150 home-game observations in 2026: margin MAE **10.103**, RMSE **12.702**, bias **+2.855 points**; win Brier **0.22775**, log loss **0.64490**; final-margin-category multiclass Brier **0.62678**, log loss **1.02611**. These multiclass scores sum the three squared errors before averaging over games.

Ten-percentage-point win bands have weighted absolute reliability error **0.11976** on these data. In the 50–60% band, the mean forecast is 54.1% but only 30.0% won (30 games). This is material miscalibration, not a calibrated win-pricing product. The full reliability table is archived. No player predictive distribution or adjusted EV is validated.

## Sunday research scenarios

These are market-free experimental home-team forecasts. They do not change player picks, probabilities or pricing. Roof-context uncertainty still excludes TEN–DAL player scenarios from recommendations/pricing.

| Fixture | Home team | Expected home margin | Home win | Final behind by 8+ | Final within 7 | Final ahead by 8+ |
|---|---|---:|---:|---:|---:|---:|
| 2026_11_MIA_BUF | BUF | +11.6 | 81.4% | 9.0% | 26.3% | 64.6% |
| 2026_11_BAL_CAR | CAR | +6.5 | 70.1% | 15.4% | 36.2% | 48.3% |
| 2026_11_NO_CHI | CHI | +6.6 | 70.4% | 15.2% | 36.0% | 48.8% |
| 2026_11_TEN_DAL | DAL | +5.7 | 68.0% | 16.7% | 37.5% | 45.8% |
| 2026_11_TB_DET | DET | +4.0 | 63.0% | 19.6% | 40.2% | 40.2% |
| 2026_11_ARI_KC | KC | +12.1 | 82.3% | 8.6% | 25.1% | 66.3% |
| 2026_11_JAX_NYG | NYG | -4.3 | 36.2% | 41.1% | 39.7% | 19.2% |
| 2026_11_NYJ_LAC | LAC | +1.4 | 54.6% | 25.3% | 42.3% | 32.5% |
| 2026_11_LV_DEN | DEN | +8.5 | 74.8% | 12.8% | 32.3% | 54.8% |
| 2026_11_PIT_PHI | PHI | -3.1 | 39.8% | 37.5% | 41.2% | 21.3% |
| 2026_11_MIN_SF | SF | +4.3 | 63.8% | 19.0% | 39.7% | 41.3% |
| 2026_11_CIN_WAS | WAS | -4.4 | 35.8% | 41.6% | 39.5% | 18.9% |

## Access, integrity and limits

In the existing research app choose **Game Intelligence**, then expand **Experimental game script — separate from certified forecasts**. Select a fixture and player/prop. T−60 expiry checks apply; completed fixtures cannot appear as upcoming. The table contains 568 complete player forecasts; all 50 roof scenarios remain excluded. Selected player projections and scenario projections equal the certified baseline because every adjustment was rejected.

The experiment manifest binds code, source release, source features/schedule, archived baseline and model hashes, protocol, forecasts, weekly metrics and reliability. The dashboard verifies code/input/output hashes and source release identity, failing closed to the unchanged certified app if experimental files differ. No automatic retraining, provider requests, quota writes, original-model changes or production changes.

£0 additional infrastructure, no dependencies/services/accounts added, no SportsGameOdds calls. No full regression suite rerun: focused chronological, artifact, entrypoint and existing release/presentation tests only. New real-time state-occupancy modelling or probability calibration requires a separately designed experiment; it is not silently inferred from final scores.

## Verification

- 17 focused tests passed, covering temporal invariance under a future-outcome mutation, sealed Week 11 rejection, exact zero-adjustment preservation (including negative yard projections), source/output hashes, identical evaluation populations, certified counts, roof exclusions, natural-language cards and the real authenticated research entrypoint.
- Five final experiment/UI tests passed, including selecting BAL–CAR and Hubbard's rushing attempts through the real entrypoint; the displayed baseline and experimental projection are both 17.1.
- Deterministic replay reproduced all seven output hashes and the complete experiment manifest exactly. This reruns the same frozen protocol, not a new tuned experiment.
- Ruff and whitespace checks passed. No full regression suite was rerun locally for this bounded task.
- Real Chromium at 390px passed the authenticated landing → Game Intelligence → BAL–CAR → Hubbard rushing-attempts flow, with the experimental warning visible, 17.1/17.1 comparison and no horizontal overflow. No provider requests were made. Hosted authenticated verification is not claimed.
