# Stage 1C.1 — Data Quality and Controlled Matchup Diagnostics

Registered before the full comparison. All choices below and `stage1c1/protocol.json`
are committed before fitting; no post-result tuning. Implementation-only smoke
checks reproduce archived point identity and exercise numerical/integrity contracts.
These already-viewed 2022–25 development / 2026 weeks 1–10 monitoring periods are
NOT a fresh independent test. The final 2026 week-11 onward period stays sealed,
including all subsequent seasons. T−60 remains the decision horizon.

Scope: approved reconciliation, backbone-controlled comparisons and diagnostic
error accounting. No C3 allocation engine, C4 scheme, C5 injury or C6 joint player
model. No paid source, dashboard hosting, production/model/probability/database/
bankroll change or merge/deployment authorisation follows from this work.

## 1. Data and reconciliation rules

Reuse the EXACT original PBP cache hashes recorded by Stage 1C, and the immutable
Stage 1B.1 player-feature snapshot. Do not silently download revised replacements.
Parquet season/week/type predicates exclude sealed outcomes before materialisation.
Raw PBP bytes remain outside the repository; committed small aggregates and source
hashes support exact model replay. Exact ETL re-generation requires the matching
original PBP bytes because upstream release URLs can change.

Construct event credits for actual pass attempts (excluding sacks), completions,
passing yards, carries (including kneels/scrambles), targets, catches and receiving
and rushing yards. Exclude no-plays, deleted plays and two-point attempts. Laterals
can credit yards without another carry/target/catch. Preserve signed yardage.
Known incompletions have zero passing yards; unknown credits are NOT zero-filled.

Canonicalise franchise aliases before joining stable player IDs with same-game
historical position records. Do not infer identity from names or future rosters.
Compare totals with recorded official team fields and observed player box scores,
retaining actor/credit/position failures and every discrepancy. These totals and
PBP often share an upstream source: reconciliation establishes internal consistency,
not independent truth or genuine historical publication timing.

A previously incomplete positional group is recovered ONLY when its relevant
team category's counts/yards reconcile, parsed credit identities are known and
observed player credits agree. Otherwise retain the original complete total or
leave the group unknown. No forced residual allocation or guessed lateral chain.
Player opportunity zeros can be confirmed from a fully reconciled count ledger
plus recorded participation; absence from a missing box score alone is insufficient.
The original evaluated player-game targets/eligibility are NEVER repaired or added.

All new context remains **retrospective reconciled, not publication-verified**.
Keep the +36h source proxy and existing +8h completion minimum. Current retrieval
cannot be backdated into a verified source archive. Postseason-only participation,
coverage, injury and bookmaker inputs remain excluded. Market-free forecasting
continues; genuine quotes/returns remain unavailable.

## 2. Eight controlled study arms plus frozen reference

All arms use the identical 55,303 eligible player-market rows/outcomes across all
nine markets. No scoring-population reduction for missing positional data.

| Arm | Point recipe | Context | Positional source |
|---|---|---|---|
| b1_none | Frozen Stage 1B.1 point engine, exactly reused | none | irrelevant |
| c0_none | Frozen Stage 1C player-only point engine, exactly reused | none | irrelevant |
| b1_context | Original Stage 1B.1 selection/refit recipe | C1+C2 | reconciled |
| c0_context | Original Stage 1C selection/refit recipe | C1+C2 | reconciled |
| b1_context_legacy | Original Stage 1B.1 recipe | C1+C2 | conservative Stage 1C |
| b1_context_fixed | Stage 1B.1's previously selected point class/hyperparameters, refit with context | C1+C2 | reconciled |
| b1_c1 | Original Stage 1B.1 recipe | C1 only | reconciled |
| b1_c2 | Original Stage 1B.1 recipe | C2 only | reconciled |

The original frozen Stage 1B.1 point/interval/probability arrays are a ninth
reference version, not a refitted or altered benchmark. The native no-context
point predictions must match that archive exactly (tolerance 1e-10). The C0
no-context points must match the previous player control. Only point estimators
are reused, not old probability calibration under a different model.

Stage 1B.1 passing-yard recipe retains its six fixed lag/Ridge candidates and
prior-selection 2%/bootstrap gate. Other markets retain the original career mean,
Ridge(alpha1) and 200-tree gradient boosting (depth3, learning rate .05, seed42),
selected by prior-season MAE as in the original recipe. This is a controlled legacy
policy, not a newly relaxed gate. Stage 1C retains career mean / scaled Ridge100 /
100-iteration histogram boosting and its existing admission rule. Do not optimise
these budgets or add RB-specific fitting/weights based on inspected results.

Point selection: Y−2; refit strictly before Y−1. The fixed-choice arm uses only
the original choice already made before the Y−1 distribution period, not an
algorithm picked from Y's evaluation scores. Source states update only with
available past games; no current/future player outcomes enter features.

## 3. One probability methodology, fixed initially

Every new arm uses the SAME Student-t(df5) residual CDF and penalised monotone
sigmoid calibration. Location/bias and residual SD are estimated on Y−1 weeks
1–6 after point fitting; sigmoid on weeks 7–10, penalty .01, slope [.25,4],
intercept [−3,3]. There is NO probability-family or calibration-method selection.
Different point models legitimately get their own residual/calibration parameters
under the identical algorithm and disjoint dates.

Use stable log-CDF/log-survival arithmetic and numerical optimisation, preserving
CDF endpoints and signed yardage. Counts are censored at zero with integer-support
rounding. Obtain 90% integer quantiles by inversion of this SAME calibrated CDF;
no separate quantile/interval selector or mislabelled confidence band. The residual
SD describes the pre-calibration Student component; it is not asserted to equal
final calibrated predictive variance or the point forecast's confidence.

The frozen reference's original probabilities remain intact. Its comparison with
b1_none isolates a wrapper change on identical points. Only comparisons WITHIN
the common methodology identify feature/backbone effects; never attribute a raw
reference wrapper difference solely to matchup data. Separate player marginals
are not a new joint attempts/completions model or a production pricing proposal.

## 4. Inner-window feature diagnostics

Y−1 weeks 11–18 are reserved for sensitivity diagnostics, not additional method
selection. Reject diagnostic calls on outer-year data. Record the maximum label
time. Permute C1/C2 blocks five times (seed741011), within season/week/position-kind,
moving whole fixture-side blocks together so teammates are not shuffled separately.
No refitting. Delta MAE measures predictive sensitivity, not causal effects;
correlated blocks and distribution shifts limit permutation interpretation.

On point TRAINING data only, report high absolute feature correlations (>=.95),
standardised linear coefficients where defined, feature scales and whether the
chosen point engine ignores context (career mean/lag blend). Do not interpret a
single coefficient as a proven matchup effect. No diagnostic changes the model.

Report raw valid-history counts, weighted exposure and Kish game ESS=(sum w)^2/
sum(w^2) for legacy and reconciled histories, using the same .9 game decay and
as-of cutoffs. Weighted games/exposures are not independent sample counts; source
completeness and actual source-publication evidence remain different concepts.

## 5. Opportunity chain and hindsight-only accounting

Reconcile competitive plays/dropbacks with official attempts/carries/targets.
Use an UNFITTED five-game historical ratio strawman for diagnostic T_hat*S_hat*E_hat:
team count from C2 volume with a past official-count/bridge ratio shrunk by100
exposures toward a training-only pooled ratio; individual share from five prior
fully observed games; efficiency from those past production/opportunity totals.
Undefined priors fall back to pools formed strictly before Y−1. This is not a
learned allocation engine, does not normalise teammate shares, and is not a
candidate point forecast or a new production model. Report its MAE separately
from the stronger fitted benchmark; its errors need not equal the fitted model's.

Oracle substitutions use actual team count, actual individual share and actual
production/opportunity for error accounting ONLY. Four-factor Shapley reductions
average all24 substitution orders for team volume, player share, efficiency and
exceptional non-opportunity credit (e.g. lateral yards with no target). Keep an
unobserved efficiency at E_hat when individual N=0; a zero-opportunity game does
NOT establish zero efficiency. Likewise keep S_hat when the team has zero count.
These conventions prevent attributing absent opportunities to an invented efficiency
or share error. Positive production with zero opportunity is retained separately,
not divided by zero or discarded.

Save all16 corners, factor reductions and source/feasibility flags in a separate
`oracle_diagnostics.parquet`, classified HINDSIGHT_ONLY, candidate_forecast=false.
They have NO betting probabilities, fair prices, ROI or promotion status. Missing
or incoherent observed source fields must be flagged with coverage counts, not
silently converted to zero. No oracle column enters any fitted candidate feature
matrix. Perfect-information bounds and interactions do not demonstrate what is
predictable at T−60, and cannot by themselves justify C3.

## 6. Endpoints and interpretation

Primary: b1_context minus b1_none passing-yard MAE. Report the 2x2 backbone/feature
interaction, c0_context−c0_none, c0_none−b1_none, b1_context−legacy, the fixed-choice
contrast, C1-only/C2-only, and frozen/common-wrapper contrast. Paired game/week
bootstrap with fixed four- and eight-week blocks,500 replicates. Intervals are
exploratory conditional on fitted decisions, not multiplicity-adjusted proof.

Secondary prespecified cohort: RB receiving yards. Keep the original pooled WR/
TE/RB market fit; do not optimise or selectively deploy that segment. Report
all positions, all markets and each season, with MAE/RMSE/bias, Brier, log loss,
reliability, interval coverage/width/score, zeros and sample sizes. No pooled
winner hides season or monitoring reversals. The old returning-gap definition
includes offseason and is not verified injury status.

For a retention recommendation require a useful primary gain (>=1% MAE, paired
upper differences below zero at BOTH block lengths) without material probability,
bias or interval/cohort harm. Secondary/cohort findings require confirmation,
not a retrospective model switch. No outcome from this already-viewed dataset
becomes a new independent test. Do not tune or open the sealed final period.

C3 is justified only conditionally: reliable opportunity data, useful/validated
team counts, and consistent evidence that learnable player-share variation is an
important remaining bottleneck. Oracle share error may reflect unpredictable
injury exits/role changes; actual pre-decision roster/usage evidence must exist.
If efficiency or poor team counts dominate, recommend more bounded work instead.
No C3–C6 code, provider purchase or production change is authorised here.

## 7. Reproduction

Separate namespace `stage1c1/`; original Stage 1B/1B.1/1C packages and archives
are frozen. Commit sources, protocol and reconciliation inputs before fitting.
Use immutable experiment IDs, exact runtime/source/input/baseline/payload hashes,
full identical-population and oracle-separation guards, saved-model replay and CI.
Stage 1A remains on Python3.14 / Arrow24. No app imports this package.
