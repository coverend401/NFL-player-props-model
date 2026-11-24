# Performance-first development — PR #8, 24 November 2026

No new dashboard, data service, model activation or production changes.
These are ranked expected-impact priorities, not promised improvements.

1. **Line-specific probability and price quality — both engines.** Audit the
   existing empirical laws by market, position and probability band; compare
   strictly walk-forward monotone calibration against retained probabilities.
   Use genuine available quotations for price-matched evaluation. Manual/bulk
   capture already exists; no new odds provider is purchased. Without authentic
   lines/prices, report distribution scores only, never ROI or betting hit rates.
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
   ROI; individual quoted odds cannot establish a genuine same-game price.
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
