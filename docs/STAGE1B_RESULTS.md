# Stage 1B measured results — research, not a production replacement

Experiment **`baseline-20261113-v5`**, scientific source commit
`5131b6c23b2926489652b14324540b01661a8df1`. Python 3.14.10, Arrow 24.0.0.
All payload/source/input hashes and semantic time guards passed. The archive has
**45 independently loadable market-season bundles**, **55,303
scored player-market games** and **331,818 paired probes**.
No production models, data, secrets, ledger or bankroll settings were changed.

## What the comparison means

The comparator reproduces Stage 1A's continuous-normal probability rule and
in-sample residual scale on the SAME pregame-safe point engine and games. It is
not the historical production model: current production pickles contain later
outcomes, and historical closing-context capture times are unavailable. Both
probability versions share point forecasts, so their point-MAE difference is zero
by construction. The separate career-mean benchmark diagnoses point forecast skill.

2022–2025 are **development OOS**, not an untouched final test. They contain
**49,034 player-market games**, including **6,709 observed zero
outcomes**. 2026 weeks 1–10 contribute **6,269**
monitoring rows, reported separately. All 2026 week-11+ final outcomes remain sealed.

Thresholds are three preregistered pregame historical-mean half-line probes, not
bookmaker lines. Their outcomes are genuine NFL observations; their thresholds
are hypothetical. No price, profit, realised win rate or betting ROI is inferred.

## Probability performance, development OOS

Player-market-weighted Brier: **0.195927 → 0.189550**
(3.25% lower). Log loss: **0.574402 → 0.561503**
(2.25% lower). Paired Brier delta 95% week-block interval:
**[-0.007284, -0.005703]**. These conditional exploratory intervals
hold fitted models/selection fixed, do not cover arbitrary long player dependence,
and are not adjusted for multiple-market research. Receiving markets dominate the
player-market weighting; equal-market means are in the machine summary.

| Market | Games | Normal Brier | Selected Brier | Delta | 95% block interval | Normal log loss | Selected log loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| completions | 2,288 | 0.13273 | 0.13445 | +0.00171 | [+0.00039, +0.00290] | 0.40973 | 0.45580 |
| passing_attempts | 2,288 | 0.13060 | 0.13118 | +0.00058 | [-0.00141, +0.00221] | 0.40217 | 0.40852 |
| passing_yards | 2,288 | 0.15751 | 0.14387 | -0.01364 | [-0.02530, -0.00537] | 0.49374 | 0.46516 |
| qb_rushing_attempts | 2,288 | 0.19693 | 0.19651 | -0.00042 | [-0.00235, +0.00193] | 0.58328 | 0.57808 |
| qb_rushing_yards | 2,288 | 0.22733 | 0.21779 | -0.00954 | [-0.01212, -0.00594] | 0.65067 | 0.62592 |
| receiving_yards | 14,112 | 0.21703 | 0.20701 | -0.01002 | [-0.01105, -0.00906] | 0.62536 | 0.60301 |
| receptions | 14,112 | 0.19993 | 0.19300 | -0.00692 | [-0.00806, -0.00616] | 0.58627 | 0.56857 |
| rushing_attempts | 4,685 | 0.17848 | 0.17636 | -0.00212 | [-0.00350, -0.00087] | 0.52929 | 0.52440 |
| rushing_yards | 4,685 | 0.20346 | 0.20027 | -0.00319 | [-0.00651, -0.00030] | 0.59261 | 0.58613 |

Seven markets have lower Brier point estimates; six have paired Brier intervals
below zero. QB rushing attempts has an interval crossing zero. Completions is a
clear regression in these development data; passing attempts is also worse on
point estimates, with an inconclusive Brier interval. No method was reselected on
these evaluation results. Retain these failures in every model review.

## Hypothetical threshold sensitivity

| Career-mean multiplier | Normal Brier | Selected Brier | Normal log loss | Selected log loss |
| --- | --- | --- | --- | --- |
| 0.5 | 0.191708 | 0.187427 | 0.564827 | 0.554241 |
| 1.0 | 0.237786 | 0.230172 | 0.669593 | 0.652232 |
| 1.5 | 0.158287 | 0.151051 | 0.488787 | 0.478035 |

These are the three preregistered threshold families. Even the centre (1.0x)
probe is not an authentic offered line. Improvements on easier tail probes cannot
be presented as evidence of value at bookmaker thresholds.

## Point accuracy and interval sharpness

| Market | MAE | Career-mean MAE | RMSE | Bias | 90% coverage | 90% mean width |
| --- | --- | --- | --- | --- | --- | --- |
| completions | 5.497 | 5.775 | 7.070 | +0.964 | 87.1% | 21.08 |
| passing_attempts | 8.032 | 8.466 | 10.474 | +1.050 | 91.2% | 39.40 |
| passing_yards | 73.068 | 69.922 | 92.328 | -0.644 | 92.9% | 465.68 |
| qb_rushing_attempts | 1.803 | 1.836 | 2.358 | +0.063 | 95.3% | 7.52 |
| qb_rushing_yards | 11.903 | 12.213 | 16.779 | +0.311 | 94.8% | 94.71 |
| receiving_yards | 19.003 | 19.694 | 26.387 | +0.067 | 98.2% | 263.94 |
| receptions | 1.481 | 1.534 | 1.920 | +0.124 | 94.8% | 5.70 |
| rushing_attempts | 3.855 | 4.292 | 4.990 | -0.045 | 92.9% | 15.49 |
| rushing_yards | 22.563 | 24.045 | 30.429 | +0.149 | 93.9% | 190.54 |

Signed bias is prediction minus outcome; units are each market's yards/counts.
Passing-yards point accuracy is worse than the naive career mean in this replay.
Completions intervals under-cover; several yardage intervals are very wide and
substantially over-cover. High coverage achieved by broad intervals is not good
sharpness or proof of calibrated tails. The probability CDF and point estimator
are separate fitted objects; a displayed point forecast is not asserted to equal
the mean of every candidate CDF. Do not promote the full family automatically.

## Calibration evidence

Fixed ten-band expected absolute calibration error (descriptive, sample-dependent):

| Market | Normal-rule ECE | Selected ECE |
| --- | --- | --- |
| completions | 3.17% | 2.25% |
| passing_attempts | 2.46% | 2.71% |
| passing_yards | 3.74% | 2.10% |
| qb_rushing_attempts | 4.59% | 2.02% |
| qb_rushing_yards | 11.07% | 2.23% |
| receiving_yards | 9.36% | 1.89% |
| receptions | 7.22% | 1.60% |
| rushing_attempts | 4.58% | 2.22% |
| rushing_yards | 7.52% | 2.46% |

ECE is not a proper score and can improve while log loss worsens, as completions
demonstrates. Use Brier/log loss, band gaps, sample sizes and interval sharpness
together. Probability-band tables include dependent-week block intervals and
calibration-gap intervals; sparse bands can have no interval. Wilson bands are
secondary descriptive summaries, not individual-probability confidence intervals.

## Authentic betting results and risk

**Authentic historical prop quotes: 0. Genuine historical strategy bets: 0.
Realised profit/ROI: unavailable.** The repository contains no authenticated price
archive. Unit-test prices and profits are synthetic fixtures and excluded from
all experiment reports. Provider historical-event APIs exist, but access/licence,
NFL-market coverage, exact price availability and historical rules need review.

The implemented backtest requires hash-bound original provider responses,
reviewed extractions, archived rules available before decision, explicit timezone
and availability timing, exact-line as-of forecasts and observed action/outcomes.
It accounts for pushes, verified voids, vig through actual quoted odds, reserved
concurrent stakes and an initial bankroll in drawdown. Historical replay timestamps
represent information cutoffs; models were built now, not published in the past.
Even with authentic quotes, returns would be counterfactual strategy results, not
actual placed-bet P/L. Unsupported rules or missing observations stop the backtest.

Fair odds/EV are push-aware. Fractional Kelly and fixed-stake utilities are
experimental; default staking remains zero without separate validation. Model
disagreement is not a statistical probability confidence interval.

## Remaining limitations and decisions

1. Historical stat revisions and missing publication/roster archives prevent a fully
   authenticated point-in-time population replay. Scores condition on observable
   participation and complete history; absent games/players cannot be invented.
2. The source's kickoff+8h availability is a proxy. No historical injury or closing
   market information is used as a known pregame feature in this baseline.
3. Annual refitting is the registered walk-forward design. Weekly model updates
   require new cross-fitted residual/calibration validation, not reuse of this
   mapping under new point models.
4. Completion/attempt regressions, thin QB selection periods, empirical/quantile
   tails and nonstationary role changes need further research. Do not tune using
   final-period outcomes to repair them.
5. Collect prospective raw source/roster/quote/rule snapshots before final-period
   decisions. The capture utility stamps the actual pregame clock and stores no
   outcomes. Final evaluation requires separate approval; no unseal flag exists.
6. Stage 1C must use the frozen protocol, same row IDs/population and proper-score
   comparisons, with timestamped matchup/personnel inputs and paired uncertainty.

## Review and dashboard

Run `streamlit run stage1b_dashboard.py` in the pinned environment to inspect
accuracy/cohorts, coverage, probability bands, versions, uncertainty, genuine-odds
status and provenance. This is a standalone proposal, not the production app.
See [audit/research](STAGE1B_AUDIT_RESEARCH.md) and [protocol/runbook](STAGE1B_PROTOCOL.md).
No Stage 1B merge or deployment is authorised by these results.
