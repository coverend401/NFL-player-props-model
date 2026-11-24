# Performance-first development — PR #8, 24 November 2026

No new dashboard, data service, model activation or production changes.
These are ranked expected-impact priorities, not promised improvements.

| Workstream | Top Picks priority | Top 2/ticket priority |
|---|---:|---:|
| Genuine price universe and calibrated marginals | 1 | 1 |
| Individual workload, role and uncertainty | 2 | 3 |
| Price-aware ranking, abstention and weekly consistency | 3 | 4 |
| Complete-ticket construction and joint dependence | 4 | 2 |
| Additional opponent/game-script complexity | 5 | 5 |

1. **Line-specific probability and price quality — both engines.** Audit the
   existing empirical laws by market, position and probability band; compare
   strictly walk-forward monotone calibration against retained probabilities.
   Use genuine available quotations for price-matched evaluation. Manual/bulk
   capture already exists; no new odds provider is purchased. Without authentic
   lines/prices, report distribution scores only, never ROI or betting hit rates. Distinguish US benchmark prices from prices executable by the UK user.
2. **Player opportunity and consistency — Top Picks first.** Compare the current
   champion, all five existing model families, three fixed recency weights and
   three opportunity-times-efficiency baselines. Use only archived pregame lags.
   Select a method per market using 2025, then report 2026 Weeks 1–10 without
   retuning. Report every market, zero outcomes, missing inputs and position/role
   cohorts, with weekly paired uncertainty. Those periods have already been
   inspected; they cannot support independent promotion claims.
3. **Separate ranking objectives — requires authentic quotes.** Top Picks:
   compare at equal selection counts and bookmaker/odds bands; report weekly
   hit-rate median, lower quartile, variability, calibration, losses and paper
   returns. A high hit probability at a poor price is not a good bet. Test
   abstention and stable-role restrictions as registered alternatives, never by
   picking a favourable week retrospectively. Keep expected value distinct.
4. **Complete-ticket optimisation — Top 2 objective.** Two available candidates
   per game are a candidate pool, not a requirement to put all of them on one
   accumulator. Compare complete tickets at matched leg counts, payout bands,
   quote horizons and fixed weekly paper budget. Learn same-game dependencies
   only from pregame-predicted marginals and later outcomes, with game-cluster
   uncertainty and held-out seasons. No credible joint model means bounds rather
   than a point probability or EV. Actual combined prices are required for ticket
   ROI; individual quoted odds cannot establish a genuine same-game price. Legs must be combinable at one bookmaker; best prices drawn across different books do not constitute an available ticket.
   Seasonal success is a scenario or measured historical ticket sequence, never
   a guarantee. Include unsuccessful/unfinished tickets and all eligible weeks.
5. **Opponent/personnel/game script — gated incremental tests.** Reuse existing
   backbone-controlled results before adding features. Compare additional
   opponent information on identical populations and model backbones. Routes,
   coverage, injuries, alternate-line availability and line movement cannot be
   inferred when their timestamped data is absent. Previously rejected game
   script adjustments remain rejected unless fresh evidence overturns that result.

## This task's first implementation

A bounded offline study in `performance_research` reuses immutable chronological
forecast archives. It fits only experimental calibration maps, not the original
nine models. The protocol is registered before the new run. Point alternatives
and calibration choices are fixed using 2025; inspected 2026 results are diagnostics.
Week 11 onwards is filtered out at read time. A successful result is evidence for
prospective testing, not permission to change the champion or live rankings.

The existing weekly research workflow will run this cached study as a challenger
check. Input hashes distinguish new evidence from replay. It does not turn an
unchanged historical archive into weekly fresh learning; when a newly admitted
forecast/feature/outcome archive is available, a new protocol-bound run is required.
Original prospective holdouts remain protected. Real quote and ticket evaluation
remain explicitly blocked until the required genuine records exist.

## Admission and adoption

Report MAE/RMSE/bias and Brier/log loss/reliability separately: lower point error
is not evidence of better betting probabilities. Use paired two-week blocks and
familywise correction, reporting all tested candidates rather than only winners.
Timing checks validate reconstruction; inherited closing-total availability and
retrospective roster limitations remain prospective-data concerns.

Adoption additionally requires prospective preregistration, objective improvement
on fresh data, sufficient weeks/markets, no important regressions, exact replay and
the existing promotion/rollback gates. Neither Top Picks nor Top 2 objectives
may be replaced by the passing-yards MAE gate alone. Separate selection/ticket
promotion contracts will require authentic quote-level evidence; the existing
forecast promotion rules will not be weakened to accommodate them.

Input-contract clarification before the first successful run: receiving target career averages are not retained in the archive. Opportunity weighting therefore compares the available last-three and last-five means; efficiency still shrinks toward the archived career efficiency. Missing candidate inputs fall back to the champion on the same rows and are counted explicitly, never set to zero.

Comparator clarification after the first diagnostic run: the reconstructed Stage 1A champion and the current enhanced research policy are distinct baselines. The final tables report both. This adds a transparent comparator; it does not change the registered 2025 selection rule, candidate grid or calibration settings after seeing 2026 results. All immutable run records are retained, and neither is an independent holdout.

A separate pregame-input audit found that the legacy slate column `career_avg` actually stores the first model feature, currently a season average (`scripts/build_slate.py:218` and the frozen model configurations). Prospective challengers therefore use the distinct name `captured_season_recent_*`; their inputs are frozen slate season/last-three values rounded to one decimal. They are not pooled with the historical true-career weighting experiment or claimed to validate that different formula. Original artefacts and display semantics are not rewritten in this task.

For commercial selection validation, preregister a small challenger set before new quotes/results arrive. Repeated weekly searches on the same holdout are development, not fresh confirmation. Include abstentions and all scheduled weeks; do not improve reported hit rate by dropping losing weeks or shortening tickets retrospectively. Same-game correlation may help or hurt a ticket depending on price; it is not automatically a penalty.

Market-specific next comparisons, only if simpler empirical baselines fail:
conditional beta-binomial completions/receptions given opportunities;
overdispersed count/hurdle models for attempts/carries and QB rush participation;
compound or empirical signed-yardage distributions for yardage. These are testable
alternatives, not assumed improvements. Player-level spread must shrink toward
role/position evidence when history is thin. No individual confidence or win rate
may be manufactured from a point prediction.

The commercial Top Picks acceptance set must address price quality explicitly:
high-probability propositions with unattractive prices can remain research
comparisons but are not promoted as value recommendations. Candidate price floors
and abstention rules must be fixed before evaluation and compared at matched odds
and selection counts. Top 2 must optimise available whole tickets under payout,
leg-count and paper-budget constraints rather than maximise the number of legs.
