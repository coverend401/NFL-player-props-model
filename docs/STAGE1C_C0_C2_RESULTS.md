# Stage 1C C0–C2 results

Research experiment `c0-c2-20261113-v1`, scientific source commit
`516af13d0d56b005aad882d52a879dc20059b602`. **No primary passing-yard improvement over Stage
1B.1 was established. Do not promote any new model or probabilities.** Keep the
C0 contracts/replay and the failed contextual candidates as research evidence.
No parameter, feature family or method was retuned after this full experiment.

## Evidence and sample

270 fitted market/year/family bundles; seven versions including the exact frozen
Stage 1B.1 comparator. Every variant scores the same **55,303 player-market games**:
49,034 development (2022–25; 6,709 observed zeros) and 6,269 already-viewed 2026
monitoring observations (903 zeros). No sample reduction or zero fabrication.
There are 387,121 forecast rows and 1,161,363 hypothetical pricing probes.
These previously inspected periods are NOT a new independent test. The **2026
week-11 onward final period remains sealed**, with no final outcome inspection.

All additional inputs are **retrospective corrected statistics**. Thirty-six-hour
context availability is a proxy, not an authenticated publication archive. There
are **zero genuinely verified historical pre-decision context records** in this
experiment. No historical prop quotes, genuine bets, realised profit or ROI exist.
PBP original-byte hashes and small immutable aggregates are preserved for replay,
not presented as independent proof of historical publication.

## Passing yards: primary outcome

| Version | MAE | RMSE | Bias | Brier | Log loss | 90% coverage | Width | Interval score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| stage1b1 | 68.140 | 86.338 | +7.195 | 0.143268 | 0.441123 | 90.65% | 280.47 | 350.25 |
| player_control | 68.455 | 86.923 | +5.706 | 0.150172 | 0.460936 | 90.12% | 276.10 | 348.23 |
| c1_opportunity | 68.243 | 86.401 | +3.703 | 0.149154 | 0.457997 | 90.12% | 273.52 | 342.75 |
| c1_efficiency | 68.311 | 86.688 | +5.330 | 0.149504 | 0.459188 | 90.82% | 280.84 | 346.42 |
| c1_schedule | 68.164 | 86.467 | +5.336 | 0.149062 | 0.457675 | 90.56% | 277.74 | 343.84 |
| c2_volume | 68.383 | 86.589 | +6.293 | 0.150203 | 0.460228 | 90.69% | 281.92 | 346.07 |
| c1_c2 | 68.226 | 86.287 | +5.464 | 0.149415 | 0.457884 | 91.13% | 281.10 | 343.92 |

Combined C1–C2 MAE is **68.226 vs Stage 1B.1 68.140** (+0.085 yards, +0.13%).
Against the common player control it improves **68.455 → 68.226** (−0.230,
−0.34%), below the registered 1% practical gate with an interval crossing zero.
The schedule-adjusted variant improves the common control by 0.291 yards (0.43%),
but is still 0.023 worse than Stage 1B.1 and its control-comparison band includes
zero. **No contextual passing-yard variant meets the primary retention criterion.**

Paired four-observed-week bootstrap MAE differences, conditional on fitted folds:

| Version | Reference | Delta yards | 95% exploratory band |
| --- | --- | --- | --- |
| c1_c2 | stage1b1 | +0.085 | [-0.253, +0.556] |
| c1_c2 | player_control | -0.230 | [-0.565, +0.130] |
| c1_efficiency | stage1b1 | +0.170 | [-0.191, +0.767] |
| c1_efficiency | player_control | -0.145 | [-0.411, +0.230] |
| c1_opportunity | stage1b1 | +0.102 | [-0.335, +0.946] |
| c1_opportunity | player_control | -0.213 | [-0.536, +0.248] |
| c1_schedule | stage1b1 | +0.023 | [-0.270, +0.448] |
| c1_schedule | player_control | -0.291 | [-0.572, +0.023] |
| c2_volume | stage1b1 | +0.243 | [-0.215, +0.625] |
| c2_volume | player_control | -0.072 | [-0.508, +0.224] |
| player_control | stage1b1 | +0.315 | [+0.025, +0.728] |

The new control uses a common small candidate budget, not a reconstruction of the
Stage 1B.1 point recipe. Its MAE is itself worse than Stage 1B.1. Therefore changes
against Stage 1B.1 include a backbone/probability-wrapper change; only comparisons
to `player_control` isolate adding context under the common recipe. A small gain
against a weaker control does not justify replacing the frozen stronger model.
These results do not prove that all matchup features are intrinsically useless.

Bias is reduced in the combined model (+7.195 → +5.464), and interval score is
lower (350.25 → 343.92), but probability Brier/log loss worsen materially. Do not
select the favourable metrics while disregarding the primary and pricing failures.

Per-season primary MAE, including already-viewed monitoring:

| Season | N | Stage 1B.1 | Control | C1 schedule | C1+C2 |
| --- | --- | --- | --- | --- | --- |
| 2022 | 550 | 62.483 | 62.483 | 62.483 | 62.483 |
| 2023 | 581 | 75.367 | 75.367 | 75.367 | 75.367 |
| 2024 | 577 | 65.428 | 66.677 | 65.946 | 66.190 |
| 2025 | 580 | 68.963 | 68.963 | 68.541 | 68.542 |
| 2026 | 289 | 67.119 | 67.119 | 67.491 | 68.032 |

Monitoring combined MAE **67.119 → 68.032** is a regression. The primary point
findings are not stable enough to support retention or production activation.

## All nine point markets

Mean absolute error, development only; units are each market's yards/counts:

| Market | stage1b1 | player_control | c1_opportunity | c1_efficiency | c1_schedule | c2_volume | c1_c2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| completions | 5.497 | 5.720 | 5.625 | 5.681 | 5.712 | 5.720 | 5.612 |
| passing_attempts | 8.032 | 8.137 | 8.127 | 8.118 | 8.155 | 8.197 | 8.078 |
| passing_yards | 68.140 | 68.455 | 68.243 | 68.311 | 68.164 | 68.383 | 68.226 |
| qb_rushing_attempts | 1.803 | 1.836 | 1.836 | 1.836 | 1.836 | 1.836 | 1.836 |
| qb_rushing_yards | 11.903 | 12.213 | 12.213 | 12.213 | 12.213 | 12.213 | 12.213 |
| receiving_yards | 19.003 | 19.387 | 19.386 | 19.214 | 19.218 | 19.467 | 19.453 |
| receptions | 1.481 | 1.497 | 1.506 | 1.493 | 1.494 | 1.524 | 1.508 |
| rushing_attempts | 3.855 | 3.855 | 3.874 | 3.853 | 3.853 | 3.903 | 3.886 |
| rushing_yards | 22.563 | 22.671 | 22.550 | 22.569 | 22.575 | 23.698 | 22.626 |

Tiny RB-market point gains in isolated variants do not satisfy the registered
practical gate or establish broad improvement. QB rushing often retains career
mean after prior validation, so identical MAE is expected rather than evidence
that a context learner improved. No winner is selected retrospectively per season.
All per-season MAE/RMSE/bias/counts are in the archive `accuracy.csv`; paired point
and interval differences are in `paired_accuracy.csv`. Cohorts are provided in
`stage1c-c0-c2-cohorts.csv`; returning is a >21-day prior participation gap,
including offseason, not retrospective injury knowledge.

## Probabilities and intervals

Combined context versus the archived benchmark:

| Market | 1B.1 Brier | C1+C2 Brier | 1B.1 log loss | C1+C2 log loss |
| --- | --- | --- | --- | --- |
| completions | 0.132333 | 0.138340 | 0.408868 | 0.426975 |
| passing_attempts | 0.130842 | 0.132107 | 0.401765 | 0.406733 |
| passing_yards | 0.143268 | 0.149415 | 0.441123 | 0.457884 |
| qb_rushing_attempts | 0.196511 | 0.196557 | 0.578076 | 0.579013 |
| qb_rushing_yards | 0.217791 | 0.219455 | 0.625921 | 0.631718 |
| receiving_yards | 0.207013 | 0.212125 | 0.603011 | 0.613263 |
| receptions | 0.193002 | 0.198462 | 0.568566 | 0.581765 |
| rushing_attempts | 0.176361 | 0.178249 | 0.524396 | 0.528525 |
| rushing_yards | 0.200273 | 0.202561 | 0.586134 | 0.590741 |

All family/season scores are in `probability_metrics.csv`; paired Brier/log-loss
bands against BOTH references are in `stage1c-c0-c2-paired-probabilities.csv`.
These are three dependent career-mean half-line probes per player-game, not
bookmaker lines. Their per-game scores are averaged for inference. The control
and context share a newly trained CDF/calibration recipe; archived calibration
was not reused under new point models. Comparisons against Stage 1B.1 therefore
do not isolate a fixture effect. No probability method should be promoted here.

Nominal 90% predictive interval quality:

| Market | Coverage: 1B.1 → C1+C2 | Width | Interval score |
| --- | --- | --- | --- |
| completions | 92.00% → 90.65% | 23.84 → 22.91 | 29.95 → 29.84 |
| passing_attempts | 89.64% → 89.86% | 32.02 → 32.14 | 44.47 → 44.19 |
| passing_yards | 90.65% → 91.13% | 280.47 → 281.10 | 350.25 → 343.92 |
| qb_rushing_attempts | 95.41% → 96.37% | 7.57 → 7.98 | 9.30 → 9.33 |
| qb_rushing_yards | 92.92% → 93.53% | 49.81 → 51.00 | 64.69 → 65.91 |
| receiving_yards | 91.62% → 93.08% | 73.75 → 74.77 | 99.03 → 98.87 |
| receptions | 97.22% → 97.13% | 6.48 → 6.51 | 7.46 → 7.49 |
| rushing_attempts | 94.30% → 94.41% | 16.34 → 16.41 | 20.06 → 20.00 |
| rushing_yards | 90.07% → 90.76% | 88.24 → 91.02 | 120.52 → 120.88 |

Reliability by band, sample size and dependent-week intervals is in the immutable
`reliability.csv`; descriptive ECE is in `stage1c-c0-c2-ece.csv`. Assess proper
scores with reliability, not ECE alone. Predictive sets need not match selected
CDF quantiles, and temporal conformal coverage is not guaranteed. These direct
models are separate marginals: joint player allocation/coherence is out of scope.

## C0 data quality and C1 limitations

| Category | Team groups | Known complete | Complete fraction |
| --- | --- | --- | --- |
| pass | 4016 | 4016 | 100.0% |
| rec_RB | 4016 | 2756 | 68.6% |
| rec_TE | 4016 | 1439 | 35.8% |
| rec_WR | 4016 | 2008 | 50.0% |
| rush_QB | 4008 | 3883 | 96.9% |
| rush_RB | 4016 | 2756 | 68.6% |

Official passing totals have complete coverage in the selected team games.
Positional aggregates are frequently incomplete because players with snap records
have no observed box-score outcomes. They are marked unknown and skipped, with
state decay and source-completeness features; they are NEVER assigned zero. The
absence of eight QB-rushing groups is not invented as eight zero totals. Missingness
is nonrandom (role/rotation/recording), so rates based on complete groups can still
be biased. This is a major reason not to claim validated positional intelligence.

Historical aliases were normalised before grouping, preventing OAK/LV fragments
from duplicating the same fixture side. Team/player identity still inherits the
benchmark's retrospective role and participation limitations. The effective-dated
identity contract exists, but no historical live roster archive was fabricated.
Schedule adjustment is a first-order entering-offence residual, not a fully
identified simultaneous attack/defence or causal rating. Denominator uncertainty,
missingness and simplistic shrinkage may mask or distort matchup signals.

## C2 intermediate quality and availability sensitivity

See `stage1c-c0-c2-team-diagnostics.csv` for competitive-play/dropback MAE,
count-distribution log loss and 90% width/coverage; script multiclass Brier/log loss
are compared with prior league frequencies. These intermediate diagnostics do not
substitute for improved player forecasts. Development scenario Brier improves
0.62271 → 0.60617 versus prior league frequencies, and log loss 1.03647 → 1.00267.
Play-volume MAE improves only 6.632 → 6.604, while dropback MAE worsens slightly
6.429 → 6.436. Nominal 90% dropback intervals cover only **85.83%**. These are
mixed intermediate findings, not evidence for a new player model. Paired week-block
bands are in the diagnostics CSV. Competitive plays and dropbacks differ
from official carries and pass attempts; the model never supplies actual future
play counts or score paths as predictors.

Script categories refer to final-margin scenarios (±7 points), not a full temporal
score simulator. Student margin and NB2 volume-mixture assumptions are provisional;
team distributions are uncalibrated context, not bookmaker probabilities. Pace is
a possession/game-clock proxy. There is no spread/total branch because timestamped
market data is unavailable, and no fake historical closing-line substitution.

`stage1c-c0-c2-lag-stress.csv` records frozen combined-model forecasts with +8h/
+72h source proxies. No model was refit or chosen on those results. This stress
test cannot establish actual historical publication times. Thirty-six-hour feeds
are still unsuitable for a genuinely verified live deployment until observed
source receipt/publication archives exist.

## Retention and next decision

- **Retain C0 as research infrastructure:** canonical/effective identity contracts,
  explicit evidence tiers, sealed predicates, as-of fixture states, incomplete-data
  checks, fixed-population comparisons, immutable inputs and full replay.
- **Keep C1 candidates archived, not promoted.** Passing-yard effects are small and
  uncertain; missing positional totals and first-order schedule adjustment limit
  interpretation. Do not represent them as validated defensive strengths.
- **Keep C2 experimental, not promoted.** The market-free baseline and diagnostics
  are useful, but no downstream primary gain is demonstrated. Do not turn its
  scenario probabilities into live betting probabilities.
- A future separately scoped experiment could preserve the stronger archived point
  recipe while adding context, improve completeness/reconciliation and investigate
  source-timing evidence. Preregister it; do not keep rerunning these viewed data
  until they appear positive. No C3–C6 work, paid source or dashboard is begun.
- No production model/probability change is recommended. Stage 1A remains active;
  the research PR requires owner approval to merge and cannot deploy anything.

## Reproduction and evidence

Scientific source was committed before the full run. `stage1c/protocol.json` and
`STAGE1C_C0_C2_PROTOCOL.md` fix families, phases, candidate budget and assumptions.
Hashes bind code, exact 69-package runtime, input aggregates, baseline and outputs.
Validation checks identical outcomes/IDs, source timing, model matrix, hypothetical
probe thresholds/scores and preserved frozen comparators. Every fitted model and
its forecast/probability outputs are replayed. No production database or settings
were accessed. Raw data are attributed to **nflverse contributors / NFL play-by-play**
and the selected project's frozen player-stat snapshot; source URLs/hashes are in
the input manifest. Upstream publication/retention conditions remain relevant.

```sh
python -m stage1c.artifacts experiments/stage1c/c0-c2-20261113-v1 --replay
python scripts/report_stage1c.py
python -m unittest discover -s tests -v
```

Re-fitting requires a NEW immutable experiment ID and the pinned Python 3.14
runtime. No production entry point imports `stage1c`. Full baseline limitations,
source availability and the approved proposal remain in the companion documents.
