# Weekly learning — research operations

The operational runbook is [Week12 operations](../docs/WEEK12_OPERATIONS.md).
Production, Supabase, bankroll, authentication, bookmaker quota and the original
nine trained models remain outside this pipeline's write paths.

```sh
python -m weekly_learning.cli preflight
python -m weekly_learning.cli capture
# Existing historical demonstration: idempotent replay, not a new test period.
python -m weekly_learning.cli cycle --mode dry-run --id 2026-w09-dryrun-v1
# After the prospective settlement gate:
python -m weekly_learning.cli cycle --mode auto --id UNIQUE-TUESDAY-ID
# Fresh inference/personnel before the next slate, without settling unfinished games:
python -m weekly_learning.cli prepare --id UNIQUE-FRIDAY-OR-SUNDAY-ID
```

Use the pinned Python 3.14 / Arrow 24 environment. Recurring jobs are not activated.
Review-only default-branch registration templates are in `ops/`. Manual research
CLI runs are available now. Selection is a separate explicit command; no cycle
selects a candidate or changes the production/default-v1 research pointer.

## Audit and scientific limits

Captures, results, readiness, selections and reports are separate immutable
bundles under `weekly_learning_state/`, with hashes and append-only audit events.
A local lock rejects concurrent writers; normal non-force GitHub pushes preserve
concurrent remote updates. Quarantine and unadmitted sources are not published.

The original demonstration reconciled 708 previously replayed Week 9 forecasts
across 15 games, including 103 observed zeros. Its population was already scorable;
it is not evidence of complete prospective coverage. The market-bias challenger
was rejected. Reusing that cached decision does not consume another holdout or
claim new improvement. No new candidate is fitted by this operational integration.

The genuine Week 11 capture was frozen on 20 November before T−60. It retains all 618
rows, 568 complete forecasts, 50 labelled roof scenarios and 22 Top Picks. Roof
scenarios are not settlement targets or priced picks. The earliest authorised
results access is 24 November 12:00 UTC, additionally requiring confirmed finals
and matching NFL/ESPN scores. Missing box scores, unknown participation and actual
zeros remain distinct. The benchmark final period remains sealed for fitting and
method selection; admitted operational results are not a fresh historical test.

The prospective v2 contract is separate from the original training/v1 contracts.
Every candidate requires unchanged model provenance, cutoff-safe features,
versioned roster/eligibility decisions, deterministic forecasts/Top Picks/Top 2
and descriptive current-fixture research. Failures preserve the last certified
release; expired forecasts are not relabelled current. See the runbook for
explicit selection, rollback and the remaining scheduling approval.
