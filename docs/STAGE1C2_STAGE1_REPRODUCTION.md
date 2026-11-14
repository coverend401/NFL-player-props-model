# Stage 1C.2 Stage 1 — data audit reproduction

Scope is data quality and feasibility only. **Stage 2 fitting remains unauthorised.** No allocation learner, model-fitting command or production activation is included. The approved protocol's 2% opportunity thresholds, paired/season/coherence and all-market safeguards remain unchanged for a later separately approved study.

Use the unchanged Python 3.14 / PyArrow 24.0.0 dependency lock:

```bash
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
python -m unittest discover -s tests -v
python -m stage1c2_stage1.validate research_inputs/stage1c2/data-quality-20261114-v6 --replay
python scripts/report_stage1c2_stage1.py research_inputs/stage1c2/data-quality-20261114-v6
python scripts/validate_release.py release_candidates/stage1a-20261113-py314-arrow24-r2 --app-smoke
```

The CI data-audit step performs the same full data-decision replay. It does not retrieve changing upstream files. The runtime/source/payload manifest, frozen benchmark reference, original feature-label hash, final-period predicates and semantic guards are all verified. Replay recomputes accepted event-credit repairs, team/player reconciliation, count-history classifications/overlays, roster timing coverage and snap/ID decisions from committed bounded snapshots. It never fits a model.

Full ETL regeneration additionally requires the original exact byte caches, including raw PBP with the hashes recorded in the frozen Stage 1C manifest. The new public-source cache inventory includes raw filenames, URLs, source asset metadata, actual retrieval times and raw-byte SHA-256 hashes. Preserve `/tmp/stage1c-pbp` and `/tmp/stage1c2-evidence`; current downloads of the same URLs are not guaranteed to reproduce these bytes.

With those caches, a new immutable audit directory can be built using:

```bash
python -m stage1c2_stage1.build --output /tmp/YOUR_NEW_DATA_AUDIT_ID \
  --cache /tmp/stage1c2-evidence --pbp-cache /tmp/stage1c-pbp
```

No existing output can be overwritten. New builds are **not** permission for fitting. Historical revised membership/status and later-discovered ID mappings remain explicitly retrospective; unknown publication times remain missing, not a +36h proxy labelled verified. No optional final-period or fitting flag exists.

Data decisions and boundaries:

- Only two exact, evidence-reviewed `no_play` events are included; no blanket relaxation of nullified-play filters.
- Intermediate lateral additions contain only described yard credits, preserve signs and final fumble adjustments, and create no opportunities/catches.
- Each of 12 internally accepted team-games must reconcile both individual and team credits. Five disagreements remain unknown; no residual allocation to force balance.
- Every original `_official` player field and the frozen evaluation population remain unchanged. The source-backed missing-count overlay is separate and carries no verified historical usable timestamp.
- Snapshot materialisation excludes 2026 week 11 onward and later seasons before column loading. Minimal permanent-ID pairs contain no current team/status/position or future performance fields.
- A missing ID is not classified as a confirmed absent player. Conflicting ID sources stay unresolved. New-history identity candidates require review before any future use.
- The active Stage 1A bundle, production app, probability methods, Supabase/authentication and bankroll/ledger functionality are untouched. All earlier research packages and benchmark archives remain frozen.

See `STAGE1C2_SOURCE_AUDIT.md` for source-specific limitations and `stage1c2-stage1-results/REPORT.md` for the quantified no-go recommendation. No genuine betting returns or forecast-performance improvement is claimed from a data-only audit.
