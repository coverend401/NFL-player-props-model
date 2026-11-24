# Alternative prediction families — 24 November 2026

Canonical immutable run: `weekly_learning_state/threshold_benchmark/studies/14f8d4049e1c3a621cc12f5c`. Earlier study directories are retained debugging/reporting snapshots; this run supersedes them. Protocol preregistered in commits `ab4f413`, `2b64fec`, `354c7fb`, before model fitting. No deployed selections or forecasts changed.

## What was tested

19,300 player-market outcomes; 55,635 distinct statistical threshold observations, nine markets. Test folds: all 2025 and previously inspected 2026 Weeks 1–10. For test year Y, fit on 2022..Y−2; calibrate on Y−1 Weeks 1–9, choose ensemble members and selection cutoffs on Y−1 Weeks 10–18. Outcomes must be available before the next split. No refit after selection. These are chronological reconstructions, **not a fresh untouched holdout**. Week 11 operational outcomes were reconciled separately and never entered this benchmark.

Thresholds are half-integer lines around each pregame last-five/career anchor, with offsets derived only from training outcomes. Duplicate numerical lines are removed. They are hypothetical statistical questions, **not authentic bookmaker propositions**. Same eligible population and thresholds for every method; player-market-balanced losses and paired two-week block uncertainty. Ranking uses information available at a common pregame weekly timestamp.

Six families: monotone direct threshold classifier; calibrated lower/median/upper quantile score; conditional forest outcome distributions; opportunity-count × efficiency model; player/position-shrunk consistency and variability; equal-weight ensemble of components passing prior-year validation. Zero outcomes remain in observed data. Missing observations are not turned into zeros. Current-game opportunities enter training targets only. Actual same-game opportunities, inherited champion predictions/sigmas, and unverified historical bookmaker context are excluded from new-model inputs.

## Probability comparison

Equal-market macro log loss (lower is better). Brier, calibration bands, all nine markets, positions, sample sizes and weekly uncertainty are in the immutable Parquet outputs.

| Method | 2025 log loss | 2026 log loss | 2026 Brier |
|---|---:|---:|---:|
| champion_normal | 0.58088 | 0.57942 | 0.19680 |
| existing_research | 0.57004 | 0.56741 | 0.19215 |
| threshold_prior | 0.58569 | 0.58754 | 0.20034 |
| direct_classifier | 0.56394 | 0.57169 | 0.19292 |
| quantile_cdf | 0.59979 | 0.60657 | 0.19296 |
| distribution_forest | 0.56291 | 0.56777 | 0.19110 |
| workload_production | 0.58822 | 0.59542 | 0.19506 |
| player_consistency | 0.59661 | 0.60891 | 0.19899 |
| validated_ensemble | 0.56319 | 0.56709 | 0.19170 |

The registered primary analysis compares against the old Gaussian reference. Secondary comparisons against `existing_research` are explicitly stored separately and never used to retune models or selection policies. Against this stronger reference, forest worsens 2026 macro log loss by **0.063%**; ensemble improves **0.056%**. Both paired uncertainty intervals include zero. Ensemble improves 2025 log loss 1.20%, but that does not establish a stable 2026 gain. No new family clears all registered evidence gates in 2026; champion retained.

## Selection comparisons

Fixed-count pools: eight unique players per weekly slate; two unique players per fixture. These tables measure ability to rank the training-defined thresholds, not betting performance at comparable prices. Easy alternative thresholds can produce high hit rates at commercially unattractive odds; without real prices these figures cannot establish reasonable odds, profitability or season-long accumulator success.

| Method | 2025 slate hit (144 legs) | 2026 slate hit (80 legs) | 2025 game hit (544 legs) | 2026 game hit (300 legs) |
|---|---:|---:|---:|---:|
| champion_normal | 80.56% | 82.50% | 84.19% | 85.00% |
| existing_research | 90.97% | 95.00% | 92.83% | 91.00% |
| threshold_prior | 83.33% | 82.50% | 81.43% | 85.00% |
| direct_classifier | 95.83% | 88.75% | 93.20% | 89.33% |
| quantile_cdf | 81.94% | 85.00% | 87.32% | 90.33% |
| distribution_forest | 85.42% | 95.00% | 90.07% | 92.33% |
| workload_production | 86.11% | 86.25% | 87.87% | 87.33% |
| player_consistency | 90.97% | 86.25% | 86.58% | 87.33% |
| validated_ensemble | 92.36% | 93.75% | 94.30% | 91.67% |

Prior-validation-qualified policies can abstain: ≥50 validation selections, ≥6 weeks, hit ≥75%, block-bootstrap lower ≥65%, calibration gap ≤5 percentage points. Cutoffs are chosen on prior-year validation only. In the 2026 diagnostic forest selected 80 slate legs and hit 78, versus 76/80 for existing research; this is not independently validated superiority or a sportsbook win-rate claim. The fixed-count game comparison is 92.33% vs 91.00%, with paired interval including zero. Selection counts, weekly lower quartile, standard deviation and per-market coverage are stored, including abstentions.

For weekly consistency, the 2026 fixed-eight lower-quartile hit rate is 90.63% for both current research and forest, versus 87.50% for ensemble; weekly standard deviations are 8.29, 8.29 and 6.25 percentage points. Forest selected-leg probabilities average 98.60% against 95.00% observed hits, so good aggregate distribution scores do not remove selection-tail overconfidence. Only ten inspected weeks are available.

## Market-specific 2026 log loss

| Market | n player-markets | Gaussian | Existing research | Direct | Forest | Ensemble |
|---|---:|---:|---:|---:|---:|---:|
| completions | 311 | 0.56608 | 0.56608 | 0.55751 | 0.54343 | 0.56608 |
| passing_attempts | 311 | 0.55024 | 0.55024 | 0.55433 | 0.54295 | 0.54225 |
| passing_yards | 311 | 0.57177 | 0.57177 | 0.56971 | 0.57910 | 0.57177 |
| qb_rushing_attempts | 311 | 0.56274 | 0.56274 | 0.56897 | 0.56055 | 0.55956 |
| qb_rushing_yards | 311 | 0.60732 | 0.57602 | 0.58890 | 0.59088 | 0.58559 |
| receiving_yards | 2010 | 0.61760 | 0.59264 | 0.59445 | 0.59391 | 0.59122 |
| receptions | 2014 | 0.58243 | 0.57001 | 0.57258 | 0.56917 | 0.56626 |
| rushing_attempts | 639 | 0.57194 | 0.55471 | 0.57147 | 0.56275 | 0.56000 |
| rushing_yards | 638 | 0.58462 | 0.56251 | 0.56726 | 0.56716 | 0.56111 |

## Interpretation and limits

- Direct classification improved 2025 ranking, but loses 6.25 percentage points on the 2026 fixed-eight slate comparison versus existing research. It is not a general upgrade.
- Forest and validated ensembles are the strongest new candidates; neither supports replacing current methods now. Ensemble components are admitted separately per market/year and fall back explicitly when none qualifies. Their errors are not assumed independent.
- Quantile, two-stage and player-consistency methods regress in probability loss. Lower quantiles do not automatically confer reliable hit probabilities. Nominal 20–80% quantile intervals cover 55.84% in 2025 and 55.62% in 2026 (target 60%, equal-market average). No quantile reliability claim is justified.
- Current empirical reference is chronologically reconstructed from the frozen research policy. Completions pricing was unavailable, so that reference uses a labelled Gaussian fallback. It is not an invented deployed completion probability.
- Timing checks use the existing reconstructed availability metadata; they do not prove every historical source was actually published at that time. No postseason-only routes or coverage observations were added as in-season inputs.
- References retain inherited unverified market publication timing; new methods exclude it. The cohort is conditional on confirmed participation/statistical observation and is not the complete universe of players who would have been offered pregame props. Historical pregame roster/inactive vintages remain incomplete.
- No authentic historical lines/prices: no ROI, offered-odds comparison, ticket probability, accumulator return or seasonal success estimate. Prospective genuine quote capture remains necessary for commercial evaluation.
- All outputs are research-only, not selected or activated. No final-period results were used for method selection.

## Reproduction

`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m performance_research.threshold_benchmark` in the original Python 3.14 / PyArrow 24 environment. Immutable manifests bind code, protocol, runtime and inputs. Hashed fit checkpoints reuse completed fits for reporting-only changes; reporting outputs have their own identity. Tests mutate future outcomes, actual opportunities and inherited predictions to verify new forecast independence.

## Validation evidence

One full regression run per runtime: Python 3.12 **536 tests, 49 intentional skips, passed**; Python 3.14 **536 tests, one intentional skip, passed**, including the real authenticated local research entrypoint and all workspaces. The subsequent secondary-reference reporting helper and its additional regression test were checked in the focused threshold/operational set: **25 tests passed** on each runtime (one intentional Python 3.12 runtime skip). Ruff and staged whitespace checks passed. Existing Cloud serving admission and all new immutable study hashes passed. Week 12 exact replay passed during certification; the final no-replay admission recheck also passed. No hosted verification or candidate activation is claimed.
