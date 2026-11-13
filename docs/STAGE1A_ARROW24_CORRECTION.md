# Stage 1A: Cloud-compatible Arrow correction — approval required

## Confirmed cause and platform choice

Production installed our required Arrow 26.0.1, then Streamlit Cloud replaced it.
The owner supplied this build-log message:

> Detected pyarrow 26.0.1 (known segfault, apache/arrow#50471). Replacing with pyarrow<25.

Our exact runtime guard correctly rejected the resulting Arrow 24.0.0 environment.
The earlier possibility of a stale build is superseded by this log evidence.
Repeated reboots with the Arrow 26 lock do not resolve that platform override.

[Apache Arrow #50471](https://github.com/apache/arrow/issues/50471) describes a
bundled mimalloc crash when Arrow is first imported on a short-lived worker and
another thread later allocates. The original report concerns Arrow 25 and notes
that Arrow 24 is unaffected; Streamlit's Cloud policy also rejects our 26.0.1.
These are separate pieces of evidence, not a claim that every Arrow 26 build has
the original defect. Python 3.14 Linux wheels for Arrow 24.0.0 are available.

Keep Streamlit Community Cloud, Python 3.14 and the existing Supabase configuration.
Pin Arrow **24.0.0 exactly**, honouring Cloud's restriction. No memory-pool workaround,
relaxed dependency range, disabled integrity check or authentication change is used.

## Prepared correction

Branch: `fix/stage1a-pyarrow24`.
Candidate: **`stage1a-20261113-py314-arrow24-r2`**.

The only production dependency change is Arrow 26.0.1 to 24.0.0. The other 68 pins,
app, ledger and validation code are unchanged. A comment in the root
`requirements.txt` also changes so Cloud observes a change in its primary
dependency file, rather than relying on monitoring the included custom lock. The normal release builder ran in
a new empty workspace under Python 3.14 / Arrow 24: it downloaded raw data, rebuilt
features, retrained all nine models, generated the slate and Top Picks, and saved
the exact schedule and QB snapshots. It generated new release IDs, timestamps,
source/file hashes and the manifest, then validated the entire bundle. The old
candidate and its manifest are retained unchanged; hashes were not edited to make
old artifacts appear compatible.

The corrected pointer is prepared **on the fix branch only** for atomic deployment
with the dependency lock and complete candidate. Nothing is selected or changed in
the live app until an approved merge. Original root `data/` files are unchanged.

## Evidence

- 55 regression tests passed on Python 3.14 and on the Python 3.12 reference runtime.
- New isolated-process test imports Arrow first on a worker that exits, then runs
  twelve worker allocation/Parquet/pandas cycles. Nulls and true zeros remain distinct.
- Arrow 24 reads and round-trips all five archived Parquet tables from Arrow 26
  without changing values or missingness. All nine archived models load; predictions
  across every eligible training observation agree within `1e-10` across Arrow versions.
- Fresh release: 139,346 raw rows; 185,912 feature rows; nine newly trained models;
  **780 slate rows (566 complete, 214 unpriced roof scenarios); 18 Top Picks**.
- Controlled regression compares every data/forecast row with the previous candidate
  using the original saved fixture context and newly trained models, excluding only
  release ID and forecast/cutoff timestamps. Numeric tolerance `1e-10`.
- The fresh MIN–GB total moved from 41.5 to 42.5 between builds. This changes 37
  projections and one Top Pick value (Justin Jefferson receiving yards: 65.0 to 65.3),
  without changing slate or pick membership. All 780 fresh forecasts replay from the
  new saved context. The original-context replay isolates Arrow compatibility from
  those legitimate live-input changes. Per-row differences are recorded in
  `stage1a-arrow24-context-changes.json`. The initial unconditional equality test
  caught this input change; the final test holds context fixed instead of weakening
  numerical tolerance or ignoring projection columns.
- All predictions and Top Picks replay from the newly trained models; all nine
  Streamlit market smoke cases and unresolved-roof suppression pass.
- Missing/mixed model, future-cutoff and incorrect-projection rejection and temporary
  rollback rehearsal pass. No production database is accessed by these checks.
- Reference forecasts remain Aaron Rodgers / Passing Yards **237.2**, Ladd McConkey /
  Receptions **3.1**; full model comparisons are in `stage1a-arrow24-validation.json`.

No accuracy or profitability improvement is claimed for a dependency correction.

## Other possible Cloud overrides

Only the Arrow override is confirmed by the supplied Cloud log. The traceback
proves the 37 dependencies checked before Arrow matched their pins in that process;
the following 31 were not reached. No authenticated production package inventory is
available here, so absence of further overrides is **not verified**. All 69 packages
match the lock locally and remain mandatory at hosted startup. If any later package
is overridden, the app must stay unavailable and its exact traceback be investigated.
Do not loosen another pin merely to clear the next error.

## Proposed deployment after approval — not performed

1. Recheck green CI on the final fix commit, unchanged production main and disabled
   updater, and candidate deadline **Sunday 15 November 2026, 14:30 GMT**.
2. Approve the corrected lock, complete rebuilt candidate and staged pointer together.
3. Merge the fix PR into Streamlit's tracked main branch. The changed root
   requirements include points to the changed lock, so the new deployment must
   install Arrow 24.0.0; a reboot alone of the old Arrow 26 release is insufficient.
4. Observe installation logs. If Cloud doesn't rebuild automatically, an approved
   reboot can force a build; don't delete/recreate the app or change Python/secrets.
5. Owner authenticates privately: confirm the **new** release ID, Week 10 / 780 rows,
   18 Top Picks, reference projections, roof scenarios unpriced, Supabase (permanent)
   and existing settings. Until that confirmation, hosting is not fully verified.
6. Stop on any mismatch. Regenerate if the activation deadline is missed.

## Rollback limitations

The previous production Arrow 26 candidate is already incompatible with Cloud.
Its pointer is retained as history, but it is **not a working rollback target**:
current source/runtime checks will reject it. Do not force that pointer or change
its manifest. A necessary rollback must restore a complete independently tested
code/data/dependency combination using Cloud-supported Arrow 24, with separate
approval. Preserve the disabled/preparation-only updater and Supabase throughout.
While diagnosing, fail-closed forecasts are preferable to an unverified legacy model.

This correction does not start Stage 1B or authorise any deployment.
