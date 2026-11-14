# Stage 1C.2 — player-opportunity allocation feasibility

**Status: proposed protocol for review, not implementation approval.** No Stage 1C.2 code, new data pipeline, fitting, capture job, dashboard, deployment or paid source is authorised by this document. The thresholds below are proposed preregistered decisions: freeze the approved protocol, source inventories, populations and hyperparameter budget in a separate commit before any full comparison. Do not retune Stage 1C.1 experiments.

Planning baseline: PR #6 was merged for research retention only at `88c6bf94b42b43d8f0dcf9d1e0774e7de72a6ecc`. This document is prepared on the separate `stage-1c2-protocol` branch; it does not modify that baseline or authorise implementation.

## 1. Question, evidence and boundaries

Can pregame player shares improve target/carry opportunity forecasts beyond player-only history and improved team volume, with coherent teammate allocations and no material deterioration in passing yards or the other eight markets?

The motivation is diagnostic, not proof of achievable gains. Stage 1C.1's hindsight strawman target-count MAE changed from 1.8884 to 1.7272 with actual team totals and to 0.7493 with actual shares; those oracle results used outcomes. They must not enter feasible model features, candidate selection or the success endpoint. Its combined passing MAE gain was only 0.073%, below the registered gate; its simpler probability wrapper undercovered passing yards and is not the default for this phase.

Retain T−60 minutes, market-free inputs, Python 3.14, PyArrow 24.0.0, existing leakage/integrity guards and every frozen Stage 1B/1B.1/1C/1C.1 benchmark. Preserve Stage 1A release `stage1a-20261113-py314-arrow24-r2`, production code/configuration, Supabase, authentication and bankroll/ledger behaviour. No schemes, personnel/injury redistribution model, C4–C6, paid provider or production activation is included.

All 2022–25 development and 2026 weeks 1–10 monitoring results have already been inspected. A new protocol does not make them independent. Keep 2026 week 11 onward, all later seasons and the conservative 2026-11-19 UTC boundary sealed. No prospective outcomes may be automatically loaded/scored if they belong to that seal. Any future independent evaluation requires separate data-governance approval; input archiving alone does not authorise unsealing labels.

## 2. Data-quality gate before model fitting

### Outstanding 17 team-games

Create an immutable, field-level discrepancy register with game/team/player/play IDs, original values, evidence URLs/version hashes, retrieval/publication evidence, proposed interpretation and decision. Keep an untouched copy of the original inputs and every old benchmark.

Current differences: one passing attempt, one carry, 35 rushing yards and 105 receiving yards in absolute aggregate. HOU 2024 week 15 has the carry/rushing discrepancy; PIT 2025 week 2 the attempt discrepancy; fifteen receiving cases involve incomplete multi-lateral structured credits. First investigate definitions, nullification/deletion/two-point handling, sack/spike/kneel conventions, stat corrections, team identities and lateral ownership. Compare structured PBP with official gamebooks/box scores and original descriptions where available. Sources sharing upstream data are not independent corroboration.

Correct only a uniquely supported credit/identity/rule interpretation. Require an official credit record or unambiguous play-level evidence reconciling the official total, plus a hand-checked regression fixture. Do not allocate a residual to the most plausible player, force balance or assume an unparsed lateral chain. Preserve ambiguous cases as unknown; zero unresolved cases is **not** a success requirement. Revised official credits remain retrospectively corrected unless historical publication is verified.

Use separate versions for corrected credit ledgers and feature-history overlays. Frozen evaluation labels never change silently. If a published label is conclusively wrong, retain the original primary benchmark/population, quarantine the affected field from primary new count scoring, and present a separately labelled corrected-label sensitivity analysis with its exact membership/counts. No dropping difficult games to make a model win. Nine-market fallback coverage must remain complete.

### Missing box versus zero

Audit the 106 QB, 475 RB, 3,028 TE and 2,092 WR active missing-box records already identified, field by field and season by season. Classify:

| State | Evidence and handling |
| --- | --- |
| Observed positive/zero | Published finite statistic with established participation; retain the value. |
| Source-backed opportunity zero | Participation established and the complete relevant event/count ledger reconciles; infer only that count field, with provenance. |
| Missing/unresolved | Incomplete feed, credit, identity or participation; retain missing, never zero-fill. |
| Verified pregame inactive | Timestamped inactive status available before T−60; zero allocation for that scenario, but a sportsbook void is separate. |
| Unknown availability | No verified predecision status; retain uncertainty and unknown allocation, not a retrospectively known inactive flag. |
| Not on the predecision team universe | Do not silently add a player because they later appeared; record membership/unknown-pool failure. |

A confirmed zero target/carry does not by itself prove zero yards: laterals can create exceptional production. Recover production only from its own complete ledger. No box row alone proves neither inactivity nor a zero. In-game injury exits are outcomes, not pregame features. Record known positives, recovered zeros, unresolved values and identity ambiguities by position, statistic and season. Report coverage before/after and how many player-history windows are affected.

Frozen-history versus evidence-repaired-history is a separate ablation with unchanged point recipe and scoring population. Individual recovery uses only information whose availability precedes each later forecast; no later position/roster/stat correction is relabelled as historically known. Retrospective corrected-ledger results and publication-verified results stay separate.

### Required data and availability

| Input | Existing availability | Additional requirement / constraint |
| --- | --- | --- |
| PBP, team totals, player features and participation | Hash-frozen revised snapshots and preserved raw cache; retrospective | Original-byte matching, discrepancy review, field-level provenance; do not silently refresh upstream releases. |
| Historical snap/usage/count histories | Partially complete; confirmed zero counts recoverable | Prior-game only, release/receipt timing or explicit +36h retrospective proxy; no postseason-only data treated as in-season evidence. |
| Full team/player identity and membership | Same-game retrospective identities available | Need dated roster/transaction/activation snapshots for genuinely feasible teammate universes, including non-prop players, arrivals and departures. Current rosters and actual participants cannot substitute. |
| T−60 availability/inactives | No verified historical archive established | Timestamped official evidence received before cutoff; uncertain/late announcements cannot be backdated. No credentials or removal of authentication needed. |
| Plays/dropbacks/attempts/carries/targets | Existing market-free C2 predictions and official totals | Validate count definitions and the pregame bridge, with only past training/calibration information. |
| Routes, schemes, coverage, injuries, bookmaker lines | Not needed for the bounded initial study | Exclude; no paid provider, synthetic prices or historical betting returns. |

A reliable historical roster universe is the main feasibility risk. **Do not normalise shares over the scored prop players or use the current game's realised participants as a pregame roster.** If membership cannot be reconstructed as of cutoff, permit a clearly labelled retrospective conditional-participation diagnostic only. Retain an unknown-player pool and the frozen forecast fallback for affected games. Such results cannot clear the live-feasibility gate. Input provenance/coverage is frozen before score inspection; do not backfill a roster from the outcomes.

## 3. Architecture: data overlay, counts, shares and production bridge

Proposed isolated modules (names illustrative): `stage1c2/contracts`, `reconciliation`, `histories`, `universes`, `team_counts`, `shares`, `allocation`, `evaluation`, `artifacts`. These are a design only; no package is created now.

Data contracts carry event time, source publication/receipt time where verified, usable-at time, correction/version ID and evidence tier. Replay builds each fixture state strictly before its T−60 cutoff. Stable IDs plus dated franchise membership prevent trades/returns/season boundaries from borrowing future identities. Document the offseason policy and uncertainty for new players rather than using later participation to fill it.

### Count definitions and coherent allocations

Allocate three distinct official opportunity ledgers: passer attempts, receiving targets and rush attempts (including QB carries). Bridge C2 plays/dropbacks to these counts using training-only ratios/models; sacks are not passing attempts, throwaways/spikes may not have a target, and carries include the audited kneel/scramble conventions. Validate each identity rather than imposing a convenient but false play-count equation.

For each team and ledger, define a complete **pregame** universe U plus an explicit unknown/unassigned bucket. Expected counts satisfy:

`N_hat_i = T_hat * s_hat_i`, with all shares/counts nonnegative and `sum_U(s_hat_i) + s_hat_unknown = 1`.

Thus all named players plus the unknown bucket sum to the same team count. Do not force all opportunities onto WR/TE/RB prop candidates: include other eligible positions and unpriced players. Non-targeted pass attempts are a separate ledger category, not fabricated receiver targets. Unknown credits, unresolved roster membership and forecast entrants remain explicitly unassigned; they are never converted into someone else's outcome.

Verified predecision inactives receive zero share in the corresponding scenario; all-inactive/empty universes allocate to the unknown bucket and trigger fallback. Availability uncertainty uses only approved predecision information, not actual later activity. No injury-causation model or detailed teammate injury redistribution is introduced here. Known inactivity is an input-state constraint, not an inferred sportsbook settlement rule.

Coherence is required for expected opportunity allocations. Independent marginal probability methods retained below do **not** constitute a coherent joint player-outcome distribution; do not claim joint betting/portfolio probabilities. No new multinomial/Dirichlet-multinomial distribution is silently introduced in this phase.

### Controlled arms

Keep a frozen native Stage 1B.1 reference, and a player-only recipe with original versus corrected history. After the history audit, freeze one common history source for every arm in the primary allocation comparison; keep source effects separate from allocation effects.

| Arm | Team count | Player share | Purpose |
| --- | --- | --- | --- |
| P: player-only | Independent native player-history forecasts | Not a team allocation | Strong existing forecast reference; explicitly report its incoherence. |
| A0: coherent control | Past-only team count baseline | Shrunk recent-share baseline | Common coherent control for V/S/VS; contrast with P includes factorisation and must not be called a pure coherence effect. |
| V: team-volume-only | Frozen market-free C2 count/bridge recipe | Same baseline share | Isolates team volume. |
| S: player-share-only | Same baseline team count | Learned pregame shares | Isolates share learning. |
| VS: combined | Same C2 count/bridge recipe as V | Same share model as S | Tests combination and the interaction. |

Two deterministic matched controls prevent repeating the earlier backbone confounding: (a) independent player opportunity forecasts passed through the same efficiency bridge, and (b) those exact opportunity outputs normalised to the baseline team count with the same unknown-mass rule. Their difference measures the normalisation/team-total constraint intervention without changing the efficiency learner. Compare the bridged independent control with the native nine-market reference separately; that gap includes the factorised production bridge and is not attributed to shares. For passing/carry counts, the independent count engine is the frozen Stage 1B.1 count-point recipe; for targets (no frozen target model exists), preregister a single scaled Ridge(alpha=100) on the same past-only lag/usage features, trained on field-validated target labels, with a training-prior fallback. No additional target-backbone search. These controls do not enter the V/S/VS feature-selection grid or create an extra success endpoint. Report count and downstream errors for every control.

Baseline team counts use trailing-five official team games, with training-only league/franchise shrinkage. Baseline shares use prior **team** games, including confirmed active zeros, shrunk to a training-only position/role prior and the unknown bucket. Distinguish confirmed inactive/no-membership from active zero or missing; expose days since last observation and counts of known observations. Do not drop zero-opportunity games or use only games with a positive target/carry.

Bounded share candidate: one regularised compositional log-linear/softmax score model, with expected count loss grouped by team-game and an explicit unknown category. Team-game grouped fitting must not treat teammates as independent records. Partial unknown credits contribute to an aggregated unknown count only when the team total is verified; otherwise mask the unresolved likelihood contribution without creating zeros. A negative residual, over-allocation or positive credit for a verified-inactive player is an explicit source conflict, not a value to clamp to zero. The compositional fitting loss does not by itself establish a calibrated joint outcome distribution. A learned share is conditional on a valid pregame universe.

Use only lagged opportunity shares, known prior usage/snaps, observation counts, recency and dated team membership. No current-game snap, route, count, injury-exit or actual starter variable. Candidate budget proposed: history window {3,5,8} team games and regularisation {1,10,100}, nine combinations; selection in prior windows only, deterministic tie-breaking toward the stronger-regularised/simpler configuration. Baseline shrinkage uses one training-fitted empirical-Bayes prior shared across arms, not extra outcome-selected grids. With fewer than three field-validated same-team historical games, use the training-only position prior/unknown pool rather than fitting a personal trend; report this fallback separately. Trades/arrivals have no invented same-team history. With fewer than eight independent weeks or 40 scoreable player-games in a required selection phase, keep the coherent baseline and mark the candidate unselected. These are minimum computational guards, not evidence of adequate statistical power. No RB-specific fit, weight or deployment rule.

Test share forecast reliability against baseline shares using team-weighted compositional log score/cross-entropy, count MAE and absolute share error. Exclude true zero team denominators from conditional share scoring (report them separately); count forecasts still include those games. Do not score a marginal share as if it were a bookmaker event probability. Report per-season/position stability, turnover/returning/limited-history cohorts, concentration, unknown mass and fallback frequency. Diagnose whether nominal share improvements translate into actual target/carry gains rather than relying on hindsight ratios.

### Preserve all nine market safeguards

Target/carry counts are the first intermediate endpoints. For point predictions in the nine existing markets, use one common, training-only efficiency/production bridge per market across A0/V/S/VS: passing yards/completions per passer attempt, rushing yards per carry, receiving yards/receptions per target, with frozen shrinkage/fallback rules and separately handled non-opportunity credits. Do not change the efficiency learner between arms to manufacture an allocation gain. Evaluate the bridge against the frozen direct player model; the bridge itself may be the bottleneck. Passing attempts and both rushing-attempt markets use allocated counts directly.

First test original versus corrected histories with the original native point recipe. Then test allocation arms with common histories/efficiency methods. Report both contrasts; do not conflate repair, backbone, team-volume, share or probability changes. Retain a full-row frozen forecast fallback when features/universe/bridge are unavailable, chosen by predecision data quality, not realised error. Publish every fallback count and its errors.

## 4. Probability methodology and chronological evaluation

Initially lock each market/fold to its **original frozen Stage 1B.1 distribution/calibration and interval recipe**, including its historically selected family/retention decision. Do not use Stage 1C.1's fixed Student/sigmoid wrapper. Do not choose a new probability family after seeing allocation scores.

Holding methodology constant does not mean recycling residuals/calibrator parameters from a different point model. Re-estimate the required residual, dispersion and calibration parameters for each arm under the same frozen algorithm using only its prescribed prior residual/calibration windows. If a retained family contains an autonomous point component (e.g. an incumbent count model or dense quantile learner), freeze/document whether and how it consumes the allocation signal before fitting; no silent use of the old mean under a new-model label. If no valid adapter exists without changing methodology, retain unchanged original probabilities for that market and label the count/point comparison **point-only**. It cannot clear probability-readiness gates. Register exact adapters and tests before experiments; no post-result adapter choice.

Use the existing outer seasons 2022–25 as inspected development and 2026 weeks 1–10 as separately reported inspected monitoring. Point/share choices use Y−2, refit strictly before Y−1; residual fit Y−1 weeks 1–6, calibration weeks 7–10, weeks 11–18 only for the existing prior-window gates/diagnostics. Keep team-game grouping and all temporal availability checks. Static learned artifacts must precede the first outer decision. Historical lag states may update sequentially with newly completed and available games; they cannot be globally recomputed using later outcomes.

Freeze the existing 55,303 player-market rows/outcomes/timestamps (49,034 development, 6,269 monitoring) and every old archive. Report all nine markets on identical rows, including original genuine zeros. Opportunity endpoints use deduplicated player-games within each ledger, not double-counted receiving-yard/reception or passing-yard/attempt/completion rows. Unknown opportunity labels stay unknown; freeze the common count-scoreable mask before fitting and report its coverage against the full eligible denominator. No per-arm population reduction. A separately labelled expanded zero-history/coverage analysis must not replace the frozen primary evaluation.

Metrics: MAE/RMSE/bias, team total error, count deviance/appropriate log score, share error and team-weighted compositional score; plus all-nine-market Brier/log loss, reliability by probability band, 90% interval coverage/width/interval score, sample sizes and observed zeros. Report market, season and predefined position/history/returning cohorts. Returning gaps are not verified injury status. Report field-specific missingness, unknown allocations, as-of universe failures and fallbacks. Use paired four/eight-week block intervals retaining whole team-games/teammates; uncertainty remains conditional on fitted choices and inspected data. No fabricated odds, ROI or realised betting results.

## 5. Proposed preregistered gates

Thresholds are proposed before new experiments, not promises of attainable improvement. They must be approved/frozen along with the executable protocol, adapters and masks.

**G0 — implementation/provenance, hard gate:** all integrity/temporal/source/frozen-benchmark checks pass; every feasible allocation sums to its team count within 1e−8; no negative allocations; verified inactive allocations are zero; unknown buckets explicit; no actual-participant roster construction. Synthetic fixtures cover missing/zero/inactive, trade/return, byes, season boundaries, zero team counts, late status, lateral/stat corrections, incomplete universes and full replay. No hard requirement to resolve all 17 cases; unsupported corrections fail this gate.

**G1 — feasibility coverage:** target and carry count-label coverage must each be at least 95% of the corresponding frozen development population and reported by season/cohort. If not, finish as a data-quality result, not a successful modelling comparison. Require complete provenance on every roster record labelled publication-verified. Report retrospective and verified universes separately; a roster-timing proxy cannot clear live feasibility, regardless of score. No forecast-row loss is permitted because fallback maintains the original nine-market denominator. Before full model fitting, assess detectable effect sizes using training-only paired errors and independent week counts; insufficient power makes the result inconclusive rather than a reason to lower thresholds or open the seal.

**G2 — co-primary opportunity accuracy:** VS versus A0 must reduce target-count MAE and non-QB carry-count MAE by at least 2% each; both paired upper differences must be below zero with four- and eight-week blocks. Use 2,000 paired moving-week-block replicates per block length with seed 41017, retaining whole team-games and teammates, and never joining a block across season boundaries. For each endpoint/block, centre weekly paired error differences under the zero-effect null, resample those blocks and compute the lower-tail one-sided bootstrap p value as (1 + number of null replicate means no greater than the observed mean)/(2,001). Take the larger p value across four/eight-week blocks, then apply Holm at family alpha .05 across the two co-primary endpoints. Report unadjusted two-sided 95% paired intervals as well. The exact season-stratified resampler and null-centering fixtures must be registered before fitting. Require the sign to favour VS in at least three of four development seasons for each endpoint. Do not count the 2026 monitoring tier as an extra independent confirmation. Insufficient observed weeks for either block or any adjusted-test failure makes the result inconclusive. Also compare VS with P and report QB/pass-attempt counts; beating a weak coherent control alone is not enough for retention.

**G3 — share contribution:** S must beat A0 and VS must beat V on count MAE with a four/eight-week upper paired difference below zero for at least one co-primary ledger; require a matching improvement in team-weighted held-out compositional score and favourable count-error direction in at least three development seasons. Treat this as gated exploratory evidence, not an additional independent discovery or a licence to select a segment. If only V helps, conclude that share learning was not established and retain the simpler volume result for research only.

**G4 — primary production-market harm safeguards (research, not activation):** passing-yard MAE must not deteriorate by more than 1% versus frozen Stage 1B.1; its four/eight-week one-sided 95% upper relative-harm bounds must remain below +1%. For every other market the corresponding MAE margin is +2%. Across all nine markets also require log-loss upper harm < +0.01, Brier upper harm < +0.005, and interval-score upper relative harm < +2%. Use the stricter of the two block results. Relative-harm bootstrap statistics resample candidate and reference errors jointly and recompute their MAE/interval-score ratio in every replicate; do not treat the reference denominator as known. Upper one-sided 95% harm bounds use the 95th percentile; improvement intervals above use two-sided 95% bounds. Inspected-data uncertainty remains exploratory, not independent confirmation. To claim a passing-yard accuracy improvement, separately require at least 1% lower MAE and both upper paired differences below zero. Report all nine outcomes even if a gate fails; do not retroactively widen margins or choose only passing seasons.

Bias safeguards: absolute bias must not worsen by more than 1% of the corresponding frozen market's MAE. Report nominal-90 coverage error, interval width and proper interval score together; narrowing with worse undercoverage is not a success. A >2 percentage-point increase in absolute coverage error or failure of the +2% interval-score harm margin triggers a no-retention-for-probability-use flag. Do not invent a composite confidence score. Existing overcoverage is not a target to preserve through arbitrarily wide intervals. Report uncertainty and small-cohort limits instead of declaring every descriptive subgroup significant.

**G5 — interpretation:** clearing these gates justifies further research, not live betting or an independent profitability claim. No experiment may select on sealed outcomes. An unavailable/invalid probability adapter or lack of historically verified roster inputs blocks probability/live readiness even if count MAE improves. Research infrastructure may still be retained with failed/inconclusive gates transparently archived. No automatic promotion, segment switch or deployment follows.

## 6. Estimated effort, checkpoints and deliverables

Indicative engineer/researcher days, conditional on public evidence availability; elapsed time can increase if archive evidence is unavailable. These are planning estimates, not a delivery promise.

| Work package | Complexity | Estimated effort | Dependency / stop decision |
| --- | --- | --- | --- |
| Review 17 discrepancies and immutable credit decisions | Medium–high | 2–4 days | Stop each case at unsupported evidence; do not force closure. |
| Missing-box/zero history audit and as-of overlay | High | 3–5 days | Field-specific participation/credit provenance; no silent target repair. |
| Dated teammate universe and timing audit | High; largest risk | 3–7 days | If historical membership cannot be established, explicitly downgrade to retrospective diagnostics. |
| Team-count bridges, coherent control and bounded share learner | High | 4–6 days | Approved universe/contracts and original-versus-repaired-history ablation. |
| Frozen-method probability adapters, all-market safeguards | High | 3–5 days | Per-market adapter registration; point-only fallback if impossible without methodology changes. |
| Chronological study, regression/replay, reports and review PR | Medium–high | 3–5 days | No seal access or post-score retuning. |

Total sequential effort approximately **18–32 working days**, with data quality/timing audit first. Existing fitting runtime does not determine this effort. At the first checkpoint, present discrepancy decisions, recovered-zero counts, universe coverage and the exact adapter/population inventory; unresolved data feasibility can stop modelling before time is spent fitting.

Expected deliverables after a separate implementation approval: new research-only branch/namespace, versioned evidence and history overlays, immutable protocol/source hashes, bounded count/allocation arms, all nine-market/season/cohort reports, explicit verified-versus-retrospective and hindsight-versus-feasible classifications, replay/regression tests and a review PR. No production code, active release, Supabase, authentication, bankroll, dashboard hosting or provider configuration changes. A separate approval would still be needed for any later merge/deployment.
