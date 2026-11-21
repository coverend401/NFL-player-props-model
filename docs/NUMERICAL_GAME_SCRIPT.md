# Numerical game-script engine — final research results

Final bundle: `experiments/script_adjustment/numerical-20261121-v5`. **Promotion failed; champion retained.**

The engine changes player forecasts numerically. It is not activated in Top Picks, Top 2, probabilities, EV or production.

## What was built

Pregame win/margin models; 15 clock/score occupancy cells; conditional pass, designed-carry, scramble, kneel and other-action models; team volume forecasts; player opportunity shares with coherent caps and unassigned mass; and a residual adjustment projected off the champion inputs to avoid double-counting. Score/clock outcomes are historical targets or hypothetical integration cells, never the actual upcoming script.

Historical teammate pools use only earlier observations and last-observed team/position. Absent observations remain unknown, not zero or inactive. Without historical timestamped roster evidence these are membership hypotheses, not verified active lineups. Live overlays use the certified release eligibility. Their transportability from imperfect historical membership is unvalidated.

## Chronological evidence

55,183 player-market observations, 1,224 games and 7,535 genuine zeros. Development: 2022–24; method selection: 2025; previously inspected diagnostic replay: 2026 Weeks 1–10. Each fit uses strictly earlier available outcomes. No Week 11 outcomes were read.

The historical baseline replicates the champion feature lists and ridge/GBR/naive selection recipe at annual origins. The frozen November 2026 weights cannot be honestly scored on their own training history; they are not used for historical predictions. Auxiliary feature publication/model vintages and historical roster archives are not verified, so this is retrospective evidence, not a verified predecision archive.

### 2025 method-selection errors, unit-scale experimental adjustment

| Market | n | Baseline MAE | Adjusted MAE | MAE gain |
|---|---:|---:|---:|---:|
| completions | 579 | 5.6841 | 5.6778 | +0.11% |
| passing_attempts | 580 | 8.2546 | 8.2351 | +0.24% |
| passing_yards | 579 | 68.0670 | 67.9468 | +0.18% |
| qb_rushing_attempts | 580 | 1.7495 | 1.7509 | -0.08% |
| qb_rushing_yards | 580 | 11.6486 | 11.6179 | +0.26% |
| receiving_yards | 3570 | 18.4284 | 18.4353 | -0.04% |
| receptions | 3574 | 1.4193 | 1.4199 | -0.04% |
| rushing_attempts | 1201 | 3.6086 | 3.5807 | +0.77% |
| rushing_yards | 1201 | 21.6834 | 21.6222 | +0.28% |

Positive gain means lower MAE. No market meets the preregistered 2% threshold and all additional paired uncertainty, Holm (27 scale/market comparisons), season consistency and fresh-final gates. The permitted scale is zero for all nine markets. Full season/market RMSE, bias, probability diagnostics, intervals, ablations and cohorts are in the bundle and CSV. Passing-yard bias worsens; small gains do not establish reliability.

### Game-level performance

| Season | Games | Home-win Brier | Log loss | Margin MAE | Plays MAE | Pass attempts MAE | Carries MAE | Occupancy RMSE / naive |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025 | 272 | 0.2201 | 0.6293 | 10.36 | 6.78 | 6.07 | 5.81 | 0.2942 / 0.2965 |
| 2026 | 137 | 0.2232 | 0.6345 | 9.86 | 6.46 | 6.06 | 5.61 | 0.2859 / 0.2957 |

Win uncertainty is reported in `script-adjustment-summary.json`. State probabilities describe a random offensive play (leading/tied/trailing), not the probability of leading all game. Occupancy improvements over recent team tendencies are modest. Reliability files report probability bands and game/play sample sizes; plays are correlated. Player Brier/log-loss and 90% interval metrics use fixed-scale champion-normal diagnostics at pregame hypothetical half-lines. They are assumption-sensitive comparisons, not certified adjusted distributions or bookmaker returns.

## Data-quality and discarded prototypes

The first development filter omitted `qb_kneel` and `qb_spike` play types; official rush/pass counts now include them. Six historical team-games still disagree with official player-derived attempts/carries (no unsupported corrections). The original participant-based historical pool also used eventual game membership in normalization; its apparent large passing gains were discarded. A regression test now requires future participation changes to leave the pregame teammate pool and allocations identical. Exact projection removes components already explained by champion inputs; numerical projection noise is not rescaled into a signal. These were correctness fixes, not outcome-driven tuning. Only the corrected v4 results are retained as evidence.

55.3% of assigned historical capacity belongs to potential teammates without scored participation/box evidence for that fixture. This is not an inactive rate. It quantifies unresolved membership and explains why mathematical allocation coherence alone cannot justify promotion. Cold historical roster/inactive availability remains a material blocker to certified player allocation.

## Numerical demonstration

- Chuba Hubbard receiving_yards: **22.10 → 22.53 (+0.43)**, experimental only.
- Chuba Hubbard receptions: **3.10 → 3.06 (-0.04)**, experimental only.
- Chuba Hubbard rushing_attempts: **17.10 → 18.21 (+1.11)**, experimental only.
- Chuba Hubbard rushing_yards: **67.70 → 73.46 (+5.76)**, experimental only.

These are a separate overlay of the 568 complete certified Week 11 forecasts, not a replacement release. All 618 original rows, 50 labelled TEN–DAL roof scenarios, 22 baseline Top Picks, original model hashes and training timestamps remain untouched. Roof scenarios are not adjusted/priced/recommended. The new overlay was genuinely frozen before kickoff; it is not backdated to the original forecast.

## Week12 and weekly operation

The bundle contains an early 16-fixture / 32-team Week12 preview from the existing timestamped fixture plan and permitted history through Week10. **No Week12 player candidate has been generated, certified or selected.** It awaits the authorised 24 November12:00 UTC settlement gate, confirmed finals, fresh roster/depth evidence and original v2 inference certification. No stale Week11 player eligibility is reused.

The existing weekly CLI now creates a separate experimental capture after champion certification, before T−60, and evaluates it only against admitted completed results. It records game-state/team-volume accuracy and workload/efficiency error identities separately; missing results are not zeros. If no predecision challenger capture exists, it never reconstructs one after results. Data/model failures preserve the champion and record an experimental blocker. No automatic promotion, fitting on the sealed benchmark, schedule activation or real-money action is added.

After the authorised cutoff, use the existing operational command:

```sh
python -m weekly_learning.cli cycle --mode auto --id UNIQUE-CYCLE-ID
python -m script_adjustment.validate --replay
```

The optional current-season play-by-play refresh is one bounded free nflverse download per new admitted snapshot, with no retries; cached immutable packs are reused. All protected games must match admission and official opportunity totals. It never calls SportsGameOdds or changes quota. Tuesday/Friday/Sunday default-branch scheduling still needs the previously documented separate approval.

## Access, rollback and cost

In the existing password-protected research app choose **Game Intelligence → Numerical game-script research**. Expand the forecast comparison and select a fixture/player. **Weekly Learning → Numerical challenger: weekly monitoring** shows prospective reports once games have settled. Current Top Picks and Top 2 remain champion-only.

No new account, paid service, API subscription, hosting, database, dependency or billing feature was introduced. No bookmaker requests were made. Public nflverse sources and existing infrastructure were used. Original release/rollback pointers, production, main, Supabase, authentication and bankroll settings are unchanged. Rollback is the prior research code commit `7dd469e`; original certified bundles never need alteration.

## Cross-CPU numerical replay

v5 preserves all fitted model, forecast, input and metric bytes from v4; v4 and the original pregame capture remain immutable. No refit or method reselection occurred. An alternative BLAS CPU kernel reproduces a maximum 3.55e-15-point margin difference. Recomputed experimental floats use absolute tolerance 1e-10 with zero relative tolerance; this is numerical reproducibility, not bitwise cross-CPU equality. Tests reject larger differences, missing/nonmissing changes and identity changes. Hashes, identities, dtypes, timestamp rules, original champion baseline and all original release validators remain strict.

The complete local regression passed 450 tests before this isolated portability correction. Focused tests also exercise the alternative CPU kernel. Final GitHub checks must be inspected before review readiness is claimed; the initial Python3.14 CI traceback is unavailable because the proxy blocks official log redirect domains.
