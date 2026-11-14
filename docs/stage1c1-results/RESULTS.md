# Stage 1C.1 — controlled research diagnostics

Research only. No production activation, independent final test, bookmaker quotes or betting returns. All 2022–25 results below are chronological out-of-sample predictions on previously inspected development data; 2026 weeks 1–10 remain a separate monitoring tier. Week 11 onward remains sealed. Inputs are retrospective revised snapshots, not verified historical T−60 publication archives.

Validated experiment `controlled-20261114-v1`; 55,303 identical eligible player-market games per version; 497,727 forecast rows across nine versions. The frozen Stage 1B.1 reference remains byte-identical. All eight new arms use the same fixed Student-t(5)/penalised sigmoid algorithm and inverse-CDF intervals; this wrapper is a diagnostic control, not a selected production replacement.

## Primary comparison and backbone controls

| version | n | mae | bias | brier | log_loss | coverage90 | width90 | interval_score90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b1_c1 | 2288.0000 | 67.8314 | 6.2974 | 0.1487 | 0.4566 | 0.8794 | 271.3418 | 374.3837 |
| b1_c2 | 2288.0000 | 68.3753 | 6.8356 | 0.1500 | 0.4601 | 0.8789 | 270.7190 | 375.4130 |
| b1_context | 2288.0000 | 68.0901 | 6.2056 | 0.1494 | 0.4585 | 0.8754 | 269.2815 | 375.3392 |
| b1_context_fixed | 2288.0000 | 68.0901 | 6.2056 | 0.1494 | 0.4585 | 0.8754 | 269.2815 | 375.3392 |
| b1_context_legacy | 2288.0000 | 68.0901 | 6.2056 | 0.1494 | 0.4585 | 0.8754 | 269.2815 | 375.3392 |
| b1_none | 2288.0000 | 68.1402 | 7.1953 | 0.1494 | 0.4585 | 0.8785 | 272.2819 | 374.9130 |
| c0_context | 2288.0000 | 68.2255 | 5.4644 | 0.1501 | 0.4602 | 0.8776 | 272.5389 | 374.7242 |
| c0_none | 2288.0000 | 68.4551 | 5.7061 | 0.1505 | 0.4625 | 0.8816 | 276.8256 | 380.5669 |
| frozen_b1 | 2288.0000 | 68.1402 | 7.1953 | 0.1433 | 0.4411 | 0.9065 | 280.4729 | 350.2544 |

Primary paired delta (candidate minus control; negative is better), with 4/8-week block intervals:

| week_block | n | delta | low | high |
| --- | --- | --- | --- | --- |
| 4.0000 | 2288.0000 | -0.0500 | -0.3990 | 0.5367 |
| 8.0000 | 2288.0000 | -0.0500 | -0.3442 | 0.5458 |

Relative passing MAE gain: 0.073%. Preregistered minimum 1% gain plus both interval upper bounds below zero: **NOT cleared**. This is not fresh independent confirmation.

| variant | reference | delta | low | high |
| --- | --- | --- | --- | --- |
| b1_context | b1_none | -0.0500 | -0.3990 | 0.5367 |
| c0_context | c0_none | -0.2295 | -0.5649 | 0.1295 |
| c0_none | b1_none | 0.3149 | 0.0251 | 0.7276 |
| b1_context | c0_context | -0.1354 | -0.3782 | 0.1124 |
| b1_context | b1_context_legacy | 0.0000 | 0.0000 | 0.0000 |
| b1_context | b1_context_fixed | 0.0000 | 0.0000 | 0.0000 |
| b1_c1 | b1_none | -0.3088 | -0.5873 | 0.1290 |
| b1_c2 | b1_none | 0.2351 | -0.0498 | 0.5978 |
| b1_none | frozen_b1 | 0.0000 | 0.0000 | 0.0000 |
| factorial_interaction | (b1ctx-b1none)-(c0ctx-c0none) | 0.1795 | -0.1851 | 0.6755 |

`c0_none−b1_none` isolates the point-backbone change; context comparisons within each backbone isolate added context under the common probability wrapper. `b1_context−b1_context_legacy` isolates reconciled positional data; `b1_context−b1_context_fixed` measures model-choice adaptation. The difference-in-differences row is a backbone/context interaction, not an additional independent experiment. `b1_none−frozen_b1` isolates the probability/interval wrapper because point predictions are identical.

## All nine markets: common-wrapper baseline versus combined context

| market | version | n | mae | bias | brier | log_loss | coverage90 | width90 | interval_score90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| completions | b1_context | 2288.0000 | 5.5299 | 0.5885 | 0.1361 | 0.4189 | 0.8798 | 21.0341 | 30.9117 |
| completions | b1_none | 2288.0000 | 5.4974 | 0.9640 | 0.1328 | 0.4101 | 0.8802 | 20.9017 | 30.8230 |
| passing_attempts | b1_context | 2288.0000 | 8.1323 | 1.0785 | 0.1337 | 0.4099 | 0.8807 | 32.0992 | 46.5747 |
| passing_attempts | b1_none | 2288.0000 | 8.0317 | 1.0497 | 0.1310 | 0.4029 | 0.8855 | 32.0983 | 46.3204 |
| passing_yards | b1_context | 2288.0000 | 68.0901 | 6.2056 | 0.1494 | 0.4585 | 0.8754 | 269.2815 | 375.3392 |
| passing_yards | b1_none | 2288.0000 | 68.1402 | 7.1953 | 0.1494 | 0.4585 | 0.8785 | 272.2819 | 374.9130 |
| qb_rushing_attempts | b1_context | 2288.0000 | 1.8163 | 0.1265 | 0.1990 | 0.5865 | 0.9471 | 7.5096 | 9.5551 |
| qb_rushing_attempts | b1_none | 2288.0000 | 1.8029 | 0.0632 | 0.1980 | 0.5843 | 0.9484 | 7.4467 | 9.4747 |
| qb_rushing_yards | b1_context | 2288.0000 | 12.0591 | 0.5599 | 0.2207 | 0.6329 | 0.9510 | 79.4235 | 92.1508 |
| qb_rushing_yards | b1_none | 2288.0000 | 11.9029 | 0.3105 | 0.2196 | 0.6310 | 0.9467 | 78.1906 | 91.6696 |
| receiving_yards | b1_context | 14112.0000 | 19.2263 | 0.5965 | 0.2087 | 0.6064 | 0.9510 | 118.1806 | 140.4070 |
| receiving_yards | b1_none | 14112.0000 | 19.0025 | 0.0668 | 0.2082 | 0.6056 | 0.9468 | 115.4935 | 139.4150 |
| receptions | b1_context | 14112.0000 | 1.4979 | 0.1366 | 0.1968 | 0.5785 | 0.9610 | 6.1468 | 7.5400 |
| receptions | b1_none | 14112.0000 | 1.4811 | 0.1245 | 0.1946 | 0.5737 | 0.9588 | 5.9995 | 7.5287 |
| rushing_attempts | b1_context | 4685.0000 | 3.8616 | 0.1056 | 0.1766 | 0.5260 | 0.9328 | 15.9345 | 20.4211 |
| rushing_attempts | b1_none | 4685.0000 | 3.8554 | -0.0447 | 0.1764 | 0.5258 | 0.9300 | 15.9022 | 20.5426 |
| rushing_yards | b1_context | 4685.0000 | 22.5847 | 0.5836 | 0.1968 | 0.5787 | 0.9215 | 112.9477 | 152.2818 |
| rushing_yards | b1_none | 4685.0000 | 22.5632 | 0.1486 | 0.1975 | 0.5811 | 0.9202 | 113.4993 | 153.5932 |

Full nine-version metrics, RMSE, zero counts and all season-level metrics (including monitoring) are in `all_markets.csv` and `all_seasons.csv`; exhaustive position/history/returning-gap/zero cohorts are in `all_cohorts_seasons.csv`. Probability-band reliability and paired 4/8-week uncertainty remain in the immutable experiment. Three hypothetical pregame half-lines per game are correlated probes, not bookmaker quotes or three independent bets.

## Prespecified RB receiving-yards subgroup

| metric | week_block | n | delta | low | high |
| --- | --- | --- | --- | --- | --- |
| absolute_error | 4.0000 | 4685.0000 | -0.1172 | -0.3184 | 0.0846 |
| absolute_error | 8.0000 | 4685.0000 | -0.1172 | -0.3883 | 0.0904 |
| brier | 4.0000 | 4685.0000 | -0.0007 | -0.0026 | 0.0008 |
| brier | 8.0000 | 4685.0000 | -0.0007 | -0.0034 | 0.0011 |
| log_loss | 4.0000 | 4685.0000 | -0.0020 | -0.0059 | 0.0014 |
| log_loss | 8.0000 | 4685.0000 | -0.0020 | -0.0074 | 0.0020 |
| interval_score | 4.0000 | 4685.0000 | 2.8713 | 0.0472 | 5.3360 |
| interval_score | 8.0000 | 4685.0000 | 2.8713 | -0.8725 | 6.1388 |

This subgroup was preregistered after its promise was observed previously. It is not an untouched replication. Fits remain pooled; no segment-specific tuning, weighting or deployment was performed. Season-level subgroup results are supplied without selecting favourable seasons.

## Feature stability, redundancy and effective information

| market | variant | block | mean_delta | minimum | maximum | context_used_fraction |
| --- | --- | --- | --- | --- | --- | --- |
| completions | b1_context | c1 | 0.0357 | -0.0344 | 0.1788 | 0.8000 |
| completions | b1_context | c2 | 0.0299 | -0.0795 | 0.1496 | 0.8000 |
| passing_attempts | b1_context | c1 | 0.0628 | 0.0000 | 0.1585 | 0.8000 |
| passing_attempts | b1_context | c2 | 0.0564 | -0.0961 | 0.1880 | 0.8000 |
| passing_yards | b1_context | c1 | 0.4268 | -1.0847 | 2.6043 | 0.6000 |
| passing_yards | b1_context | c2 | -0.0256 | -1.5917 | 1.1228 | 0.6000 |
| qb_rushing_attempts | b1_context | c1 | 0.0025 | -0.0106 | 0.0195 | 0.6000 |
| qb_rushing_attempts | b1_context | c2 | 0.0005 | -0.0329 | 0.0236 | 0.6000 |
| qb_rushing_yards | b1_context | c1 | 0.0041 | -0.0279 | 0.0683 | 0.4000 |
| qb_rushing_yards | b1_context | c2 | -0.0215 | -0.1547 | 0.0451 | 0.4000 |
| receiving_yards | b1_context | c1 | 0.0354 | -0.0169 | 0.0795 | 1.0000 |
| receiving_yards | b1_context | c2 | -0.0017 | -0.1767 | 0.1785 | 1.0000 |
| receptions | b1_context | c1 | 0.0027 | -0.0032 | 0.0080 | 1.0000 |
| receptions | b1_context | c2 | -0.0032 | -0.0141 | 0.0039 | 1.0000 |
| rushing_attempts | b1_context | c1 | 0.0815 | 0.0141 | 0.2466 | 1.0000 |
| rushing_attempts | b1_context | c2 | 0.0151 | -0.0226 | 0.0503 | 1.0000 |
| rushing_yards | b1_context | c1 | 0.3582 | -0.0241 | 0.7623 | 0.8000 |
| rushing_yards | b1_context | c2 | 0.0261 | -0.0646 | 0.1284 | 0.8000 |

Permutation diagnostics use only the prior year's weeks 11–18, moving whole fixture-side blocks within week and position kind. Positive delta means worse error after permutation, not proof of causality. Correlated features, few independent team games and distribution shift limit interpretation. A career/lag fallback ignores context entirely; zero sensitivity is then structural, not evidence that the feature is intrinsically useless.

2,480 training-only feature-pair records have |correlation| ≥ .95 (repeated across folds/arms, not distinct independent findings). Standardised linear coefficients and feature standard deviations are archived; tree models do not receive invented coefficients.

| source | kind | median_kish_games | p10_kish_games | median_weighted_opportunities | median_staleness_days |
| --- | --- | --- | --- | --- | --- |
| legacy | pass | 18.9956 | 18.8719 | 332.1893 | 6.9583 |
| legacy | rec_RB | 13.2836 | 10.8761 | 39.7465 | 7.1215 |
| legacy | rec_TE | 6.9861 | 4.7037 | 26.3938 | 16.9583 |
| legacy | rec_WR | 9.3977 | 6.8333 | 95.2865 | 13.8368 |
| legacy | rush_QB | 18.4571 | 17.4007 | 39.7676 | 6.9583 |
| legacy | rush_RB | 13.2836 | 10.8761 | 152.7414 | 7.1215 |
| reconciled | pass | 18.9956 | 18.8719 | 332.1893 | 6.9583 |
| reconciled | rec_RB | 18.9939 | 18.8420 | 56.3852 | 6.9583 |
| reconciled | rec_TE | 18.9898 | 18.7836 | 69.1053 | 6.9583 |
| reconciled | rec_WR | 18.9925 | 18.8117 | 186.4778 | 6.9583 |
| reconciled | rush_QB | 18.9956 | 18.8719 | 41.0161 | 6.9583 |
| reconciled | rush_RB | 18.9951 | 18.8719 | 216.6273 | 6.9583 |

Kish ESS counts decayed games, not independent plays or players. Better coverage cannot create verified publication timestamps. C2 team-volume inputs are unchanged by positional reconciliation.

## Hindsight-only team-volume / player-share / efficiency error accounting

| market | n | base_mae | team_opportunity_mae | individual_opportunity_mae | actual_team_individual_opportunity_mae | actual_share_individual_opportunity_mae | oracle_team_only_mae | oracle_share_only_mae | oracle_efficiency_only_mae | team_shapley | share_shapley | efficiency_shapley | exceptional_shapley | full_oracle_mae | zero_opportunities | incoherent_shares |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| completions | 2288.0000 | 5.6032 | 5.9557 | 8.0785 | 4.2462 | 5.2383 | 4.1666 | 3.8755 | 5.1298 | 2.2940 | 2.0587 | 1.2505 | 0.0000 | 0.0000 | 62.0000 | 0.0000 |
| passing_attempts | 2288.0000 | 8.0785 | 5.9557 | 8.0785 | 4.2462 | 5.2383 | 4.2462 | 5.2383 | 8.0785 | 4.5353 | 3.5432 | 0.0000 | 0.0000 | 0.0000 | 62.0000 | 0.0000 |
| passing_yards | 2288.0000 | 68.4405 | 5.9557 | 8.0785 | 4.2462 | 5.2383 | 59.5721 | 50.7645 | 54.5932 | 21.5704 | 20.5372 | 26.3329 | 0.0000 | 0.0000 | 62.0000 | 0.0000 |
| qb_rushing_attempts | 2288.0000 | 1.8509 | 6.0324 | 1.8509 | 1.7563 | 0.7816 | 1.7563 | 0.7816 | 1.8509 | 0.4381 | 1.4128 | 0.0000 | 0.0000 | 0.0000 | 260.0000 | 0.0000 |
| qb_rushing_yards | 2288.0000 | 12.2076 | 6.0324 | 1.8509 | 1.7563 | 0.7816 | 12.2228 | 9.5652 | 7.9617 | 1.2996 | 4.6599 | 6.2473 | 0.0008 | 0.0000 | 260.0000 | 0.0000 |
| receiving_yards | 14112.0000 | 19.7131 | 5.8406 | 1.8884 | 1.7272 | 0.7493 | 19.1969 | 15.4085 | 13.7086 | 2.4247 | 7.6765 | 9.6108 | 0.0011 | 0.0000 | 1639.0000 | 0.0000 |
| receptions | 14112.0000 | 1.4995 | 5.8406 | 1.8884 | 1.7272 | 0.7493 | 1.4263 | 0.8955 | 1.2901 | 0.2372 | 0.8391 | 0.4231 | 0.0000 | 0.0000 | 1639.0000 | 0.0000 |
| rushing_attempts | 4685.0000 | 3.8639 | 6.0197 | 3.8639 | 3.1932 | 2.0781 | 3.1932 | 2.0781 | 3.8639 | 1.3744 | 2.4895 | 0.0000 | 0.0000 | 0.0000 | 310.0000 | 0.0000 |
| rushing_yards | 4685.0000 | 22.8250 | 6.0197 | 3.8639 | 3.1932 | 2.0781 | 20.1457 | 17.8430 | 16.0472 | 4.9014 | 8.3335 | 9.5901 | 0.0000 | 0.0000 | 310.0000 | 0.0000 |

These are explicit hindsight substitutions in an unfitted five-game ratio strawman, NOT improvements to the fitted Stage 1B.1/C1 models and NOT forecasts available to a bettor. Four-factor Shapley accounting averages all 24 orders and reconciles the reduction in absolute error, including exceptional zero-opportunity lateral production. When opportunities are zero, efficiency is unobserved and stays at its feasible estimate. Share is similarly unobserved when team opportunities are zero. No oracle enters model selection, probabilities or a deployment bundle. Oracle headroom is not evidence that a feasible allocation model can realise it.

## Scope and next decision

Retain data contracts, reconciliation and diagnostics as research infrastructure. Do not activate the combined context or diagnostic probability wrapper based on these inspected development results. Resolve residual stat-credit inconsistencies and obtain reproducible pre-decision roster/usage provenance before any allocation feature is labelled live-valid. If separately approved, a bounded C3 feasibility experiment should compare team-volume-only versus player-share-only versus their combination on identical rows, with prior-window selection and the final period sealed. Current oracle accounting can prioritise that question but cannot answer it. No C3–C6 implementation, paid odds provider or dashboard hosting is included.
