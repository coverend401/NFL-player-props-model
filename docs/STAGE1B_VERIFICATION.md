# Stage 1B verification record

Final experiment: `experiments/stage1b/baseline-20261113-v5`.
Scientific code/protocol commit: `5131b6c2` (full SHA in the manifest).

- Python 3.14.10 / pyarrow 24.0.0: **98 tests passed** (55 existing, 43 Stage 1B).
- Python 3.12 reference / pyarrow 24.0.0: **98 tests passed**.
- All 69 installed packages match the unchanged production lock; dependency check passed.
- Experiment CLI validates source/input/payload hashes, full model availability,
  chronology, sealed final period and absence of fabricated betting results.
- All 45 bundles load in an independent process, including career-mean baselines.
- Dashboard AppTest passes and market/period switches produce no exceptions.
- Chromium/Playwright local preview renders the final v5 archive with no app errors.
  Preview: `stage1b-dashboard-preview.png`. The local preview server was stopped.
- New-code Ruff F checks and `git diff --check` pass.
- Source/config edits or a changed input during an experiment abort promotion;
  scientific code must be committed before a run starts.
- Regression tests cover pregame feature timing, unknown outcomes versus zeros,
  byes/season boundaries, delayed availability, sealed final data, future evaluation
  label mutations, CDF support/calibration/push arithmetic, EV/Kelly, evidence/rule
  provenance, naive/late timestamps, unsupported odds formats, missing probabilities,
  concurrent stake reserves, first-loss drawdown, immutable captures and serialization.

The audit confirms no changes to `app.py`, `pricing.py`, `betting_engine.py`,
`performance.py`, `ledger.py`, production training/feature scripts, requirements,
`release_utils.py`, `active_release.json`, `data/` or either release candidate.
No Supabase table, authentication, bankroll setting or Cloud configuration was read
or modified by the new lab. Existing production tests use isolated fixtures.

CI repeats the test matrix, existing Stage 1A release/app checks, and the new
research-archive/dashboard checks. See the PR's final-head check results for status.

Passing software checks does not imply all probability families improve or that
live betting is justified. The documented completion/attempt regressions and
unavailable authentic odds/final outcomes remain scientific limitations.
