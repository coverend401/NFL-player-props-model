# Week 12 prospective research operations

This path is research-only. Production pointers, original training/v1 inference
validators, nine frozen models and historical benchmark readers are unchanged.
No SportsGameOdds calls, subscriptions, paid storage, secrets or retraining.

## Settlement admission

The owner's 21 November instruction authorises operational settlement, not use
of protected observations for historical method selection. The earliest access
is **24 November 2026, 12:00 UTC**. Every genuinely captured fixture must also
be past its Tuesday-noon/eight-hour conservative availability threshold.

1. Validate immutable predecision capture and T−60 timing before HTTP.
2. Download the official schedule into quarantine; read fixture metadata only.
3. Make one bounded ESPN scoreboard request. Match team identities/kickoffs;
   require every fixture final before reading any scores. Postponements, missing
   matches and unfinished games fail closed.
4. Read NFL scores only after finality; require exact agreement with ESPN.
5. Fetch player/team/snap observations after finality. Keep missing results
   separate from genuine observed zeros. No zero-filling for absent box scores.
6. Persist only admitted outcomes and future fixture/personnel metadata. Record
   download digests, scoped-file digests and a time-stamped admission receipt.
7. Reconcile frozen forecasts into a new immutable report. Do not overwrite
   forecasts, previously consumed holdouts or retrospective experiment decisions.

Admissions form a chronological, hash-linked chain. Later releases require all
protected historical games to be covered by this chain. A later corrected score
that disagrees with an existing receipt fails certification rather than rewriting
history. No new challenger is fitted or promoted by this operational integration;
the previous rejected challenger is reported explicitly as a cached decision.

## Commands (Python 3.14, pinned Arrow 24 environment)

```sh
python -m weekly_learning.cli preflight
python -m weekly_learning.cli preflight --refresh-fixtures
# Run after the settlement gate, not before:
python -m weekly_learning.cli cycle --mode auto --id week11-prospective-first
# Friday/Sunday: fresh personnel and inference from the latest admitted week
python -m weekly_learning.cli prepare --id week12-friday-refresh
```

An early run writes a waiting report without results requests. A completed run
archives reconciliation, then refreshes target-week roster/depth evidence and
builds a candidate with the existing frozen champion. Target-week starter
evidence must be dated on/after the admitted settlement date; a fresh download
of last week’s unchanged depth chart alone does not pass. Failed source, eligibility
or certification stages preserve the last certified release. The actual failure
is recorded; no stale candidate is labelled current.

The **prospective_frozen_model_inference_v2** contract requires original model
hashes/training timestamps, an admitted outcome receipt, cutoff-safe features,
versioned eligibility replay, exact player forecast/Top Picks replay, deterministic
Top 2 and descriptive game research. It does not claim to pass the old W11-only
contract. Descriptive final-margin groups are not calibrated future game-state
probabilities; player projections are not adjusted by them.

## Selection and rollback

Automatic cycles prepare and freeze candidates but **do not select them**.
After certificate review and before every applicable T−60 deadline:

```sh
python -m weekly_learning.cli select --candidate research_inference_releases/weekly-CYCLE-ID
```

This is an explicit operational action, not performed in this change. It writes
only `weekly_learning_state/selected_research.json` and archives the previous
selection. The old `research_active_inference.json` remains unchanged. The app
validates the overlay and falls back to its certified W11 bundle on failure,
with a warning. Expired forecasts remain historical research, not current bets.
Rollback restores the archived operational pointer via a reviewed research commit;
removing that pointer restores the unchanged original research default. Never
rewrite a release, capture, admission or learning report. No production rollback
or Supabase action is involved.

## Scheduling: approval still required

The research workflow has manual and reusable entry points, **no active cron**.
PR checks run the existing idempotent dry run, not protected results collection.
`ops/weekly-learning-manual-registration.yml` is the minimal default-branch
registration template. `ops/weekly-learning-recurring-registration.yml` separately
proposes Tuesday noon settlement, Friday 10:00 and Sunday 07:00 UTC
inference refreshes. Friday/Sunday reuse the latest admitted results week,
refresh sources and personnel, and do not attempt to settle unfinished Week12. Neither template
is active. Register/merge only with owner approval. GitHub requires registration
on the default branch; manual CLI execution on the research branch works now.

Only standard public-repository GitHub-hosted Linux Actions are permitted. No
artifact/cache storage, hosted service or provider key is used. Jobs persist
only research state/admitted sources/new research releases by a normal push;
concurrent updates reject the push. Quarantine/unadmitted sources are excluded.
Account-level billing settings are not changed or assumed verified. No new
paid infrastructure or usage-based service is introduced.

## Current readiness

Preflight on 21 November verified the existing genuine W11 capture and retrieved
16 Week12 fixtures using metadata columns only. W11 outcomes were not read.
Week12 fresh eligibility, forecast counts and certification cannot be claimed
until settlement and the fresh source gates pass. Roof ambiguity stays labelled
and excluded from pricing/Top Picks by the existing inference logic. A missing
source or insufficient roster evidence is a real blocker, not permission to reuse
W11 predictions or eligibility. A human review/selection remains intentional.
