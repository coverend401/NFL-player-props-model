# Weekly learning v1 — research only

This is a functioning capture → reconciliation → diagnosis → candidate test →
retain/reject → forecast-readiness cycle. It does not promise profitable betting
or force an improvement every week. Production, the original nine models,
Supabase, authentication, bankroll and bookmaker quota are outside its write paths.

## Run it

Use the pinned Python 3.14 / PyArrow 24 environment:

```bash
python -m weekly_learning.cli capture
python -m weekly_learning.cli cycle --mode dry-run --week 9 --id 2026-w09-dryrun-v1
python -m weekly_learning.cli cycle --mode auto --id weekly-UNIQUE-RUN-ID
```

The committed dry run is idempotent: rerunning its ID validates/reuses the archive;
it does not overwrite a prediction, spend another holdout, or repeat a model fit.
New attempts use new IDs. Never edit historical bundles to make checks pass.

`auto` freezes the approved slate if it has not already been captured, waits until
its final fixture has passed the conservative eight-hour completion horizon, then
attempts results reconciliation and next-week preparation. An existing genuine
capture is reused after kickoff; a missing pregame capture cannot be backdated.

The results adapter downloads at most five current-season public nflverse files;
forecast preparation adds four required auxiliary/roster/depth sources. Each file
has a 32 MiB ceiling, one attempt, source URL, retrieval times and SHA-256. No old
seasons are redownloaded, no original model is retrained and no bookmaker request
is made. Raw files remain quarantined; season/week predicates precede any result
materialisation. Offline input packs can be supplied with `--sources PATH`.

## State and data integrity

`weekly_learning_state/` is the durable research store. Captures, results,
corrections, candidate decisions and readiness are separate immutable bundles.
Every bundle has file hashes; audit events form an append-only hash chain.
A local exclusive lock rejects concurrent writers. The scheduled job uses one
concurrency group and a normal non-force research-branch git push: a competing
remote update fails instead of overwriting it. An abandoned lock or incomplete
holdout reservation needs inspection, not an automatic reset.

A capture records the original release/model identities, training metadata,
forecast timestamp, actual freeze time and kickoff cutoffs. The original Parquet
forecast and Top Picks files are copied without changing their contents. Roof
scenarios are archived but remain excluded from complete/priced recommendations.
Experimental team/script context is a separate file and is not described as an
input to the champion's internal forecast.

Results require a completed game, an identified player, observed offensive
participation and an observed statistic. Genuine zeros survive. Missing boxes,
missing statistics and no-offensive-snap cases have separate statuses; no snaps
is not proof of inactivity or sportsbook void. Corrections from an upstream
source create a new reconciliation version, never overwrite the forecast.

Error reports include MAE/RMSE, signed bias, true-zero counts, team/position
cohorts, experimental team opportunity/balance discrepancies, playing-time changes
and exact workload-versus-efficiency decompositions where companion count
forecasts exist. The decomposition is arithmetic evidence, not a causal injury
or coaching diagnosis. At-snap lead/trail fractions are included when actual PBP
is available; final-margin probabilities are a different target.

## Candidate and promotion policy

The first prespecified challenger is a half-step market bias correction fitted
only on the 2022–24 archived chronological forecasts. It is evaluated on identical
2026 Weeks 1–10 populations, with paired week bootstrap intervals, paired
week-sign randomisation diagnostics and Holm familywise control across nine
markets. Sign randomisation assumes exchangeable week signs; time dependence and
the inspected dataset prevent a confirmatory interpretation. Probability scores
use hypothetical half-lines and frozen pre-2026 normal scales, not bookmaker bets.

This is a **retrospective proxy evaluation**, not a comparison of live November
weights on their own training games. The initial holdout is explicitly not fresh.
Its reservation binds code/protocol/input/model hashes. Repeated runs of the same
plan reuse the same decision; a different plan cannot silently reuse that block.

The initial diagnostic correction is rejected. It is not a certified deployable
postprocessor. Passing a numerical test alone never activates it. Promotion
requires a fresh prospectively registered holdout, matching registered/evaluated
baseline and challenger models, all nine markets, minimum sample sizes/weeks,
primary-market paired improvement, no material market regressions, probability
safeguards and a compatible existing release that passes exact replay. A rollback
is saved before the research champion registry changes. Unsupported challenger
recipes remain blocked rather than bypassing the original release validator.
A synthetic unit test exercises the accepted certification path; it is not a
claim that any real challenger passed.

## Next forecasts

The current Week 11 bundle is reused and exactly replayed, not falsely described
as newly generated. It has 618 rows, 568 complete forecasts, 50 roof scenarios,
22 Top Picks and 22 currently eligible Top 2 selections.

The operational adapter refreshes current-season features using the existing
feature functions, dated roster/depth evidence and frozen models. It delegates
certification to the existing inference builder/validator. Missing identities,
required sources, unknown eligibility, wrong fixture weeks, stale data or failed
replay stop downstream selection. Only a passed compatible research bundle can
update `research_active_inference.json`; the previous pointer is archived first.
The production pointer and model files are never updated. A newly promoted model
parent is selected in an isolated function namespace, without mutating the
production builder or its active pointer.

## Week 12 blocker: do not confuse settlement with unsealing research

The existing 2026 Week 11 onward seal is still enforced. No operational settlement
exception has been approved. Week 11 outcomes therefore cannot currently be read
for learning or used to generate Week 12 features. The original frozen inference
validator also rejects Week 11 outcome inputs. Week 12 is correctly reported as
blocked; no stale Week 11 slate is relabelled as Week 12.

Before operational Week 12 use, the owner must approve a separate prospective
settlement policy and a narrowly versioned compatible inference admission rule,
while leaving the frozen benchmarks/final evaluation sealed. Then run one actual
source/eligibility/certification cycle. That live fresh-source path has **not**
been claimed verified by the historical dry run. No repeated Codex session is
needed for the scheduled capture/report cycle once these one-time gates and
workflow registration are resolved; genuinely new model recipes still need
compatible certification and fresh evaluation evidence.

## Scheduling and £0 safeguards

`.github/workflows/weekly_learning.yml` provides Tuesday 12:00 UTC reconciliation,
Friday 10:00 UTC capture and Sunday 07:00 UTC capture, plus manual dispatch. Before
games finish the automatic mode captures and waits; it does not poll for results.

GitHub registers schedules/manual dispatch workflows on the **default branch**.
This workflow is on PR #8 only, so its schedules are **not active**. A separate
approved research-infrastructure merge is required to register it. The PR trigger
runs only the cached historical dry run on same-repository changes. No merge,
manual workflow dispatch or legacy updater activation was performed here.

Only standard public-repository Linux jobs are allowed; private-repository jobs
fail closed by the workflow condition. No paid runners, new accounts, API keys,
Actions artifact storage or dependency caches are introduced. Durable state uses
the existing free repository, not expiring artifacts or a new database. GitHub
step summaries are free. No additional billing is enabled. Existing account
usage/remaining allowance is not available and is not claimed verified.

## Access and rollback

Open the existing authenticated research app and select **Weekly Learning**.
It shows the last cycle, accuracy by market, recurring patterns, rejected
candidates, current champion and next-slate blockers. Historical/readiness dates
remain visible; expired readiness is not presented as current certification.
Hosted authentication remains owner-only; local tests are not hosted verification.

For a research forecast rollback, inspect the corresponding
`weekly_learning_state/selections/<cycle>/previous_pointer.json`, validate the
referenced release again, and restore only the research pointer in a reviewed
research-branch commit. A model rollback uses the archived champion record and
unchanged model-parent hashes. Never reset the learning audit or bookmaker quota.
The pre-engine recovery commit is `2761318`; the first dry-run code/data checkpoint
is `28f17f2`. Existing Stage 1A / Week 11 rollback releases are preserved.

Read-only replay is also available:

```bash
python -m weekly_learning.cli replay --id 2026-w09-dryrun-v1
```

It verifies every saved reconciliation row and all nine markets' point/probability
arithmetic against immutable inputs. It does not spend a new holdout or change
state. The new next-week bundle is frozen immediately after certification and
before research selection, so a Tuesday build cannot miss Thursday's capture.
Raw-source hashes and approved origins are verified before materialisation;
forecast inputs older than 48 hours, missing past-fixture completion evidence or
missing team-game totals fail closed. Source snapshots and forecasts stay distinct.
Selection is the final atomic operation after all report/audit writes succeed;
a failed job cannot persist a new pointer through the scheduled workflow.

The source/feature adapter was exercised end to end offline using the already
downloaded Week 11 inputs. The separate `weekly-offline-rehearsal-20261120` bundle
is certified (618/568 rows, 12 fixtures, 22 Top Picks, exact replay) and unselected.
Its participation-identity losses are recorded by position in source provenance,
following the existing Stage 1A processing rules without inventing mappings.
The HTTP downloader and future Week 12 data admission have not been represented
as live-verified by this rehearsal. Calendar-sensitive archive tests are pinned to
Week 11 and a historical clock, independently of the changing current default.
