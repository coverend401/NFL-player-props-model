# Stage 1A coordinated release: ready for review, not deployed

Candidate **`stage1a-20261113-py314-r3`** is staged at `release_candidates/stage1a-20261113-py314-r3`. It is inactive: **no `active_release.json` has been written in the checkout**, no production data files were replaced, and `main` remains at `0c6029002be0820c0502d957372d5261610ba927` at the final read-only check.

## Recommendation: retain Python 3.14

Production is already on Python 3.14. The safest tested route is to **keep that setting**, pin the dependencies, and use models freshly trained on the same Python minor version. The candidate was built on **CPython 3.14.10**, scikit-learn **1.9.1**, joblib **1.6.0**, NumPy **2.5.4**, SciPy **1.18.1**, pandas **3.1.1** and Streamlit **1.67.0**. All direct/transitive versions are pinned in `requirements-production.lock`. The guard requires matching package versions and Python 3.14; compatible patch updates are allowed.

Evidence:

- A clean Python 3.14 environment installed the entire pinned stack from available wheels and passed `pip check`.
- **51 automated tests passed on Python 3.14 and 51 on the Python 3.12 reference environment.**
- All nine original production model files and nine earlier Python-3.12 Stage 1A files loaded and round-tripped on Python 3.14 without scikit-learn version-mismatch warnings. Across both interpreters with the same pinned libraries, sampled predictions differed by at most **0**, within `1e-10` tolerance. This is evidence for those files, not a guarantee for arbitrary pickle/library versions.
- The original `main` application code plus its original data/model files rendered and accepted odds on the pinned Python 3.14 stack.
- The candidate's **nine models were trained natively on Python 3.14**, not merely relabelled as compatible. Every forecast and Top Pick was reproduced from the exact saved inputs and models, and the production app exercised all nine complete markets and scenario suppression in isolated storage.

There is no demonstrated benefit that justifies a forced downgrade to 3.12 here. [Streamlit's official runtime-change instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/upgrade-python) require deleting/redeploying an existing app to change Python. Avoid that disruption. If a future runtime migration is required, first validate a separate app with approval; do not delete the working app to experiment.

## Prepared payload

| Item | Result |
|---|---:|
| Raw weekly player records | 139,346 |
| Engineered feature records | 185,912 |
| Fresh trained models | 9 |
| Weekly slate rows | 780 |
| Complete forecast rows | 566 |
| Unpriced roof-scenario rows | 214 |
| Top Picks (complete rows only) | 18 |

The payload includes 13 required data/model files, two exact input snapshots (schedule and QB1 mapping), and a manifest. All 13 artifacts carry the same release ID and are SHA-256 checked. The manifest also binds source hashes, package versions, build times, fixture kickoffs and the retained legacy fallback hashes. All nine models have one shared training timestamp, compatible feature schemas and cutoffs strictly before prediction.

- Source/build code commit: `388bdee2da0e9f0841b5054256c6ae3ce1fd57a0`.
- Build began: `2026-11-13T14:39:35.823497+00:00`.
- Payload built: `2026-11-13T14:40:59.168334+00:00`.
- Validation finished: `2026-11-13T14:42:01.500873+00:00`.
- **Select before `2026-11-15T14:30:00+00:00` — Sunday 15 November 2026, 14:30 GMT.** After that first fixture starts, regenerate a new candidate. Do not override expiry.

These are fresh-data release counts, not an accuracy improvement or a direct comparison with the audit's older frozen snapshot. Stage 1A's modelling/calibration/availability limitations remain; this is not approval for live betting.

## Release safety

- Building starts in an empty temporary workspace: stale models cannot survive a skipped training market. Every required model/file must exist and validate before an immutable candidate directory is promoted.
- The app resolves one release pointer per rerun, verifies the whole bundle/runtime before loading forecasts, and uses immutable paths in its caches. It cannot mix half an old release with half a new one. Failure stops forecast loading.
- Selection and rollback use a lock, expected-current ID and atomic pointer replacement. Started games are removed on rerun; an older already-active bundle does not suddenly show past games as upcoming.
- Fault-injection checks rejected a missing model, future training timestamp, wrong release ID and an incorrect projection even when its file hash was recalculated. A real-bundle rollback rehearsal restored the verified legacy data and left a synthetic bet-storage marker unchanged. No live database was queried or changed.
- The scheduled job on the development branch has **read-only repository permissions**, builds a complete candidate, and uploads only that candidate. It contains no commit/push/deploy step and never changes the active pointer.
- January raw-data refresh now follows the NFL season rather than requesting nonexistent next-calendar-year statistics.

**Important:** the old scheduled updater on `main` is still unchanged because no production change was authorised. Until the replacement is approved/merged, its existing Tuesday 09:00 UTC auto-push behaviour can still run. If the review/cutover is delayed, obtain explicit approval to pause that old job; this preparation has not disabled it. Recheck `main` and regenerate if its code/data changed before cutover.

## Remaining review/preflight actions

The technical candidate checks passed. It is **ready for review**, not selected or deployed. Before cutover: approve the exact candidate and the merge/auto-deployment together, confirm live bet/settings backups or persistent storage, verify the existing private settings, and check the deadline/current `main` again. Production hosting and connected storage have not been exercised with live credentials.

Use the [non-technical release checklist](STAGE1A_RELEASE_CHECKLIST.md) for the approval, selection, merge, verification and rollback sequence. The [machine-readable report](stage1a-release-report.json), [fault/rollback results](stage1a-release-rehearsal.json), and [candidate manifest](../release_candidates/stage1a-20261113-py314-r3/manifest.json) contain the detailed evidence.

For a first-release code rollback, the tested application baseline is Git commit `0c6029002be0820c0502d957372d5261610ba927` with the original model/data files and **this tested Python 3.14 dependency lock**. Do not blindly revert to floating requirements or restore the old automatic data-push workflow. Code and dependency rollback must be reviewed together; ledger files and secrets are never part of the release payload.
