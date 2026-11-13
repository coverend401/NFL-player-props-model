# Stage 1C C0–C2 registered research experiment

Scope: approved C0 data contracts, C1 defensive context and C2 team volume/pace/
pass-run/script context only. No C3 teammate allocation, C4 scheme/personnel,
C5 injuries or C6 joint player model. No production integration, dashboard hosting,
paid provider or actual betting claim. Python 3.14 / PyArrow 24 and all existing
pins stay unchanged. Stage 1A and both frozen research archives remain untouched.

## Data and evidence

`research_inputs/stage1c/public-20261113-v3` contains 4,016 team-game observations
from public nflverse PBP and position totals from the SAME player-feature snapshot
used by the frozen Stage 1B.1 benchmark. Original PBP bytes are SHA-256 referenced
in the input manifest; the small development-only aggregates are committed.
Public downloads use the documented nflverse PBP release endpoints. No EPA/CPOE,
upstream fitted expected-opportunity models, actual future line/weather/QB data,
injuries, participation charts, routes or coverage are used. Thus postseason-only
participation cannot enter the experiment. No odds provider is configured.

The source consists of currently corrected historical data. Original publication
versions are unavailable: **every observation and result is retrospective, not
verified pre-decision evidence**. Raw-byte retrieval times are retained, not
backdated. The default contextual availability proxy is kickoff +36h, at least
the existing +8h completed-game bound. This is a conservative modelling assumption,
not proof of publication. The strict contract for verified inputs requires actual
publication/receipt timestamps and provenance; no inputs here qualify for it.
Stress checks will change the proxy to +8h/+72h for frozen-model sensitivity,
not select methods based on those stress outcomes.

Development predicates remove 2026 week 11 onward and all subsequent seasons
BEFORE Parquet outcome columns materialise. Date boundary is additionally guarded
at 2026-11-19T00:00Z. The final period remains sealed, with no unseal flag. Full
source files may be cached as opaque bytes; no sealed values enter derived inputs,
features, diagnostics or experiments. Pre-2022 observations are warm-up/training.

Canonical franchise aliases (e.g. OAK/LV, LAR/LA) are normalised BEFORE aggregation.
IDs are not inferred from names. Fixture states accept future fixture metadata
without same-game outcomes. A separate effective-dated identity contract rejects
missing/ambiguous or not-yet-published roster assignments. Current roster history
is not invented: the scored population still inherits the frozen benchmark's
retrospective player/team/position and observed-participation limitations.

Partial positional box scores are NOT complete defensive totals. Any unobserved
player in a recorded position group makes that group's total unknown. Its state
is decayed without updating production/opportunities; known zero outcomes remain
zero. Whole-team passing totals use existing recorded official team totals rather
than summing an incomplete player panel. Missingness/effective exposure is exposed
to models. This reduces available positional information and may induce nonrandom
feature-source coverage; it never removes player-games from the evaluation.
No missing player outcome is manufactured, repaired or scored as zero.

## C1 implementation

Six historical categories: team passing, QB rushing, RB rushing and receiving
by RB/WR/TE. Opportunity and production per game are separated from production
per opportunity and completion/catch rates. Per-team history decays by .9 per
completed eligible game. Volume shrinks toward explicit weak priors with four-game
strength; efficiency shrinks with 100-opportunity strength. Known-data fraction
and effective exposures accompany estimates. Weak cold-start priors are modelling
constants, not simulated observations or claimed empirical improvements.

Schedule adjustment is **first-order online adjustment**, not a full simultaneous
attack/defence fit: the prior opponent offence's entering-game shrunk efficiency
is subtracted from subsequently observed production. Defensive residuals are then
shrunk. All entering-game expectations in a completion-time batch are computed
before applying any batch outcomes. No end-of-season ratings, future opponents
or current-game outcomes enter an entering-game state. Estimates remain predictive
associations, not causal effects or individual defender assignments.

## C2 implementation

A market-free three-scenario model predicts final margin categories: trailing
by >7, within ±7, leading by >7. Location/scale use only prior team points for/
against and historical margin dispersion, with a df=5 Student distribution.
The scenario is a coarse final-margin proxy for game script, **not an observed or
fully simulated future score path**. No bookmaker spread/total branch is tested
because timestamped market inputs are unavailable.

Team competitive pass/run plays, dropbacks, no-huddle and possession/drive clock
pace come from completed PBP. Pace is a filtered game-clock gap proxy, not
wall-clock snap time. Core plays exclude special teams, two-point tries and the
separate kneel/spike play types; dropbacks include sacks/scrambles. Non-dropback
plays are NOT official rushing attempts; dropbacks are NOT official pass attempts.
C1 official statistics and the nine scoring targets keep their existing semantics.

Scenario-conditioned historical volume and dropback share shrink toward team
priors; opponent plays allowed contributes to volume. Mixture expectations account
for scenario volume/share dependence. A three-component NB2 count mixture supplies
team play/dropback dispersion, with a weak 62-play/100-variance cold-start prior.
Its scenario and count quality are tested separately against simple prior/league
forecasts. It is uncalibrated research context, not a joint player outcome engine
or a new live betting probability. All counts are used only as pregame context.

## Identical-population ablations and chronology

Six versions, plus the exact frozen Stage 1B.1 comparator:

1. `player_control`: historical player features only.
2. `c1_opportunity`: control + defensive opportunity/production per game.
3. `c1_efficiency`: control + shrunk efficiency/catch rate and exposure.
4. `c1_schedule`: control + online schedule-adjusted efficiency/residuals.
5. `c2_volume`: control + market-free pace/volume/pass-share/script context.
6. `c1_c2`: union of registered C1/C2 context, without duplicate columns.

Each version scores all 55,303 original player-market rows: 49,034 development
(2022–25) plus 6,269 already-viewed 2026 monitoring rows. Zeros are retained,
unknowns are not reclassified, and a missing fixture join fails rather than
silently reducing the sample. All nine markets are reported; passing-yard MAE is
the primary endpoint. The data have already been inspected during prior stages,
so this is development evidence, not a new independent test.

Direct regression is deliberately simpler than a new joint model. Each ablation
has the SAME model budget: career mean, StandardScaler+Ridge(alpha100), and
HistGradientBoosting(100 iterations, 7 leaves, min-leaf30). Select on Y−2 only;
require the inherited 2% MAE gain and paired week-block upper difference <0 before
replacing career mean. Refit before Y−1. Thus comparison to `player_control`
isolates adding fixture information under a common recipe; comparison to archived
Stage 1B.1 also includes a recipe change and must not be attributed wholly to
fixture features. There is no outer-year choice of a preferred family.

Preserve annual rolling origins: distribution fit Y−1 weeks 1–6, calibration
7–10, probability/interval selection 11–18, evaluate Y. Labels must be available
strictly before the next phase. Player/fixture states update with available past
games; point-model parameters do not refit inside the outer year. Weekly parameter
retraining is not mixed into this experiment.

All families share a newly fitted probability wrapper: support-correct normal,
scaled empirical and Student residual CDFs, fixed 15% Student tail mixture,
identity/penalised monotone sigmoid calibration; selection is on the separate
prior window, against a normal default with .005 log-loss gain, no Brier increase
and paired upper difference <0. Do not transfer archived calibration to new point
models. Intervals compare held-out normal and .05/.95 conditional quantiles with
nonnegative conformal expansion using the prior calibration period. Select CQR
by prior interval score with >=85% coverage and >=1% score gain. Count support,
signed yardage and integer push partitions are retained. Intervals need not equal
the selected CDF quantiles, temporal exchangeability is not asserted, and separately
priced player marginals do not establish joint attempts/completions coherence.
These limitations require later approved work, not hidden C6 implementation.

## Reporting and acceptance

Report MAE/RMSE/bias, sample counts/zeros, Brier/log loss/reliability, interval
coverage/width/score by market, version and season. Include paired four-week
bootstrap differences against BOTH Stage 1B.1 and player control; uncertainty
conditions on fitted decisions and is exploratory, not full-pipeline or multiplicity-
adjusted significance. Report per-position source completeness and C2 intermediate
volume/scenario performance. Preserve regressions and all family outputs.

A feature family's retention claim needs useful improvement over the common
player control as well as scrutiny against Stage 1B.1. Proposed minimum meaningful
primary gain: 1% MAE or .005 absolute log loss with a paired upper difference below
zero, without material Brier/bias/season/cohort or coverage harm. Report mixed
results instead of automatically promoting a pooled winner. No claimed numerical
benefit is presumed. Do not revise this protocol after the full run to pass a gate.

Sources/protocol/input hashes must be committed before the full experiment.
Immutable IDs, full source/runtime/payload hashing, row/outcome/timestamp checks,
model replay and CI protect reproducibility. The raw PBP hashes reference public
sources; byte integrity does not certify historical publication authenticity.
No genuine quotes/bets/profit/ROI exist. No merging, deployment, new dashboard,
experimental production prices, paid data or C3–C6 work is authorised.
