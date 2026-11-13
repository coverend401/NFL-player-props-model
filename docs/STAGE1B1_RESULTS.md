# Stage 1B.1 results and review

Immutable experiment: `improvements-20261113-v1`. Scientific source commit:
`f27f20d3d3aad750f0f6d03d69b21dc720208b71`. This is a research comparison, not a production
release or approval for live betting. Stage 1B was merged as `15a4028`; Stage 1A
release `stage1a-20261113-py314-arrow24-r2` remains active and unmodified.
No dashboard has been hosted or modified by Stage 1B.1.

## Population, validation and final holdout

45 annual market/year bundles; **49,034 development player-market games (2022–25,
6,709 observed zero outcomes)** and **6,269 monitoring games (2026 weeks 1–10,
903 zero outcomes)**. All row IDs, outcomes and old point/probability comparators
match the frozen benchmark exactly. There are 331,818 paired half-line probes,
with the three dependent thresholds averaged per player-game for inference.
No missing/zero-outcome substitution or selective removal of hard games occurred.

The final **2026 week 11 onward remains sealed**, including all future seasons.
No final outcomes were materialised. These previously inspected development and
monitoring seasons are NOT untouched final tests for this follow-up. The original
retrospective-data/participation limits still apply. All fitted/selection labels
precede outer decisions. Chronological phases are documented in
[the protocol](STAGE1B1_PROTOCOL.md). No methods were changed after this full run.

## Point accuracy

| Market | N dev | Stage 1B MAE | 1B.1 MAE | Naive MAE | 1B.1 RMSE | 1B.1 bias |
| --- | --- | --- | --- | --- | --- | --- |
| completions | 2288 | 5.497 | 5.497 | 5.775 | 7.070 | +0.964 |
| passing_attempts | 2288 | 8.032 | 8.032 | 8.466 | 10.474 | +1.050 |
| passing_yards | 2288 | 73.068 | 68.140 | 69.922 | 86.338 | +7.195 |
| qb_rushing_attempts | 2288 | 1.803 | 1.803 | 1.836 | 2.358 | +0.063 |
| qb_rushing_yards | 2288 | 11.903 | 11.903 | 12.213 | 16.779 | +0.311 |
| receiving_yards | 14112 | 19.003 | 19.003 | 19.694 | 26.387 | +0.067 |
| receptions | 14112 | 1.481 | 1.481 | 1.534 | 1.920 | +0.124 |
| rushing_attempts | 4685 | 3.855 | 3.855 | 4.292 | 4.990 | -0.045 |
| rushing_yards | 4685 | 22.563 | 22.563 | 24.045 | 30.429 | +0.149 |

Passing yards: MAE **73.068 → 68.140** (6.74% lower), versus career mean **69.922**
(2.55% lower). Paired week-block difference against Stage 1B is −4.928 yards,
95% exploratory band **[−10.845, −0.689]**; against naive −1.782,
**[-2.805, -0.852]**.
RMSE 92.328 → 86.338, but signed bias worsens −0.644 → **+7.195 yards**.
The aggregate gain is heavily influenced by repairing the weak 2024 point model.
It is not uniform across seasons or proof of future superiority:

| Season | N | Stage 1B MAE | 1B.1 MAE | Naive MAE | 1B.1 interval coverage |
| --- | --- | --- | --- | --- | --- |
| 2022 | 550 | 63.562 | 62.483 | 62.483 | 91.45% |
| 2023 | 581 | 68.523 | 75.367 | 75.367 | 91.91% |
| 2024 | 577 | 91.108 | 65.428 | 68.972 | 92.89% |
| 2025 | 580 | 68.689 | 68.963 | 72.467 | 86.38% |
| 2026 | 289 | 66.994 | 67.119 | 70.317 | 87.89% |

2023 and 2025 MAE regress against Stage 1B. In 2026 monitoring, MAE
**66.994 → 67.119** is a small regression, although below naive 70.317.
2025 coverage is only 86.38%, 2026 87.89%. Do not hide these failures behind the
pooled average. Eight other point models remain exactly unchanged. Cohort
comparisons (returning, nonreturning, short/long prior history and descriptive zero
outcomes) are saved in `stage1b1-cohorts.csv`; groups overlap and are not selection
criteria. Returning means a prior participation gap >21 days, including offseason;
it does not establish an injury return. Per-season metrics are in the immutable archive.

## Probability scores and investigation of previous regressions

Lower Brier and log loss are better. Bands below are paired week-block Brier
differences (1B.1 minus 1B), conditional on fitted fold decisions, not independent
observations or multiplicity-adjusted significance claims.

| Market | Brier: 1B → 1B.1 | Log loss: 1B → 1B.1 | 95% Brier delta band |
| --- | --- | --- | --- |
| completions | 0.134449 → 0.132333 | 0.455800 → 0.408868 | [-0.003255, -0.001181] |
| passing_attempts | 0.131184 → 0.130842 | 0.408520 → 0.401765 | [-0.001266, +0.000663] |
| passing_yards | 0.143867 → 0.143268 | 0.465164 → 0.441123 | [-0.001815, +0.001011] |
| qb_rushing_attempts | 0.196511 → 0.196511 | 0.578076 → 0.578076 | [+0.000000, +0.000000] |
| qb_rushing_yards | 0.217791 → 0.217791 | 0.625921 → 0.625921 | [+0.000000, +0.000000] |
| receiving_yards | 0.207013 → 0.207013 | 0.603011 → 0.603011 | [+0.000000, +0.000000] |
| receptions | 0.193002 → 0.193002 | 0.568566 → 0.568566 | [+0.000000, +0.000000] |
| rushing_attempts | 0.176361 → 0.176361 | 0.524396 → 0.524396 | [+0.000000, +0.000000] |
| rushing_yards | 0.200273 → 0.200273 | 0.586134 → 0.586134 | [+0.000000, +0.000000] |

Completions improves both scores; its paired Brier band excludes zero. Passing
attempts and passing yards improve the pooled point estimates, but their Brier
bands include zero. Six other markets' probability arrays are exactly unchanged.
The changed passing-yard point engine contributes to its probability comparison;
this is not an isolated calibration attribution study. Across all markets weighted
Brier/log-loss aggregates are in `stage1b1-summary.json`; the small QB population
means aggregates can obscure those markets.

The normal reference is now eligible. Bounded empirical/quantile tails, flexible
calibration on small QB samples, and a four-week method-selection bootstrap were
credible failure mechanisms. New disjoint windows, positive-slope shrinkage and an
explicit tail anchor address them together; this experiment is **not an ablation**
proving their separate causal contributions. In development completions, 17 of
6,864 old probes were wrong with >99.9% confidence (11.26% of old total log loss);
new probes have zero such cases at these three thresholds. Tail probability
accuracy elsewhere is still unproven. Passing attempts has 2 such old cases,
passing yards 9; the new versions have none. Selection details and old/new
families are recorded in the machine summary/fold archive. Completion NB thinning
was researched and evaluated as a candidate, not forced into the selected result.

Relative to the ORIGINAL Stage 1B normal-rule comparator, development completions
Brier is 0.132333 vs 0.132735 and log loss 0.408868 vs 0.409734; these small gains
do not prove superiority. Passing-attempt Brier remains slightly worse (0.130842
vs 0.130604), despite log loss 0.401765 vs 0.402175. The regression is reduced,
not universally resolved against every benchmark. Original comparator uses the
same point model for attempts/completions and is not a historical production replay.

Supplementary paired log-loss bands are in `stage1b1-logloss-intervals.csv`.
Threshold-level scores are in `stage1b1-threshold-sensitivity.csv`; they are
hypothetical half-lines, NEVER observed book lines. In 2026 monitoring,
completions Brier 0.138116 → 0.136226; attempts 0.132051 → 0.127978; yards
0.143001 → 0.140612. These small, already viewed samples are not final evidence.

## Reliability

Fixed ten-band weighted absolute calibration gaps (descriptive ECE):

| Market | Stage 1B | 1B.1 |
| --- | --- | --- |
| completions | 2.25% | 2.31% |
| passing_attempts | 2.71% | 3.18% |
| passing_yards | 2.10% | 1.66% |
| qb_rushing_attempts | 2.02% | 2.02% |
| qb_rushing_yards | 2.23% | 2.23% |
| receiving_yards | 1.89% | 1.89% |
| receptions | 1.60% | 1.60% |
| rushing_attempts | 2.22% | 2.22% |
| rushing_yards | 2.46% | 2.46% |

Completions ECE worsens 2.25% → 2.31%, and attempts 2.71% → 3.18%, despite
better proper scores. Calibration has not improved uniformly. Do not describe the
entire probability family as demonstrably calibrated.

Full reliability bands, player-game/probe counts and dependent-week gap intervals
are in `reliability.csv`. ECE is not a proper score or an individual probability
confidence bound. Sparse bands and threshold transfer remain concerns.

## Interval sharpness and calibration

Nominal 90%; widths in market units; lower interval score is better:

| Market | Coverage: 1B → 1B.1 | Mean width | Mean interval score |
| --- | --- | --- | --- |
| completions | 87.11% → 92.00% | 21.08 → 23.84 | 31.31 → 29.95 |
| passing_attempts | 91.17% → 89.64% | 39.40 → 32.02 | 48.67 → 44.47 |
| passing_yards | 92.88% → 90.65% | 465.68 → 280.47 | 522.09 → 350.25 |
| qb_rushing_attempts | 95.32% → 95.41% | 7.52 → 7.57 | 9.08 → 9.30 |
| qb_rushing_yards | 94.76% → 92.92% | 94.71 → 49.81 | 103.55 → 64.69 |
| receiving_yards | 98.18% → 91.62% | 263.94 → 73.75 | 270.62 → 99.03 |
| receptions | 94.79% → 97.22% | 5.70 → 6.48 | 7.26 → 7.46 |
| rushing_attempts | 92.87% → 94.30% | 15.49 → 16.34 | 19.83 → 20.06 |
| rushing_yards | 93.90% → 90.07% | 190.54 → 88.24 | 211.81 → 120.52 |

Yardage intervals are substantially narrower with pooled coverage closer to 90%.
Passing-yard width falls 39.77%, receiving-yard width 72.06%. Completions widens
to repair prior undercoverage. Receptions, RB attempts and QB attempts score worse
and/or widen; **do not promote the interval family indiscriminately**. The prior
selection rule is frozen and those outer regressions are retained. Independent
CQR sets need not equal selected pricing-CDF quantiles. Temporal role changes
invalidate any unqualified exchangeable conformal coverage guarantee. Per-season
and 2026 undercoverage remain important, particularly the QB markets.

## Authentic bookmaker evidence and operational blockers

**Genuine quotes: 0. Genuine historical bets: 0. Realised profit/ROI: unavailable.**
The owner confirmed no provider yet. A tested manual collector now preserves raw
future-event quote bytes, actual capture/quote/kickoff times, decimal odds, lines,
requested markets, hashes and raw settlement-rule documents. It refuses failed,
empty, backdated or post-kickoff substitutes and marks all captures unreviewed.
It stores no credential in metadata; no keys, paid requests or jobs are configured.
See [activation requirements](STAGE1B1_ODDS_CAPTURE.md).

Provider/licence/coverage, a privately configured key, approved domain, private
durable archive, capture schedule, event/player crosswalks and reviewed rule/price
availability remain prerequisites. Prepared tooling does **not** mean collection
is operational. Raw observations alone do not prove executable prices or valid
settlement. Existing evidence-bound replay and staking protections remain intact.

## Recommendation and next work

Review/merge Stage 1B.1 only as research infrastructure, with no app/probability
activation or dashboard hosting. Do not ship these experimental probabilities or
intervals to live betting on the strength of development scores.

1. Select/license an odds provider and establish approved private prospective
   quote/rule/model-decision evidence capture before claiming betting value.
2. Freeze the prospective protocol and retain the sealed final period until a
   separately approved, one-time evaluation. Do not retune against its outcomes.
3. Investigate passing-yard positive bias, 2023/2025 reversals and 2026 monitoring
   regression; validate weekly cross-fitted updates and naive baselines prospectively.
4. Investigate count interval regressions/conditional undercoverage, probability–
   interval coherence and joint attempts/completions consistency. Retain per-season
   coverage and proper interval score; assess deeper/longer-block uncertainty.
5. Only then consider a separately reviewed market-by-market production candidate.
   Stage 1C matchup/injury features must preserve authentic timing and the frozen
   baseline. This PR does not begin Stage 1C or alter production risk settings.
