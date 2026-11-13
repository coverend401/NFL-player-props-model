# Stage 1A release checklist — approval required

**Nothing in this checklist has been merged, selected for production, deployed or changed in the live app.** Preparation and scheduled jobs only create candidates. The candidate ID and deadline are recorded in the accompanying release report.

## Recommended runtime

Keep the existing **Python 3.14** production setting. The candidate is built and tested on Python 3.14 with the exact package versions in `requirements-production.lock`, including scikit-learn and joblib. Python 3.12 remains a regression/compatibility reference, not the proposed production target.

Changing to 3.12 would introduce a hosting migration without a demonstrated benefit for this release. [Streamlit's official guidance](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/upgrade-python) says an existing Community Cloud app must be deleted and redeployed to change its Python version. Do not do that as part of this preparation. If a later change becomes necessary, validate a separate app first and obtain approval for the cutover; do not delete the working app to experiment.

## Before approving a release

1. **Review one named candidate.** Match its ID, forecast week, counts and activation deadline with the release report. Green tests do not establish betting profitability.
2. **Check the live app is still working.** Keep its Python 3.14 setting. Confirm the app entry point and branch, and preserve its private settings securely; do not paste secrets into chat or commit them.
3. **Protect betting history.** Export/back up bets and settings and confirm whether storage is persistent. Local SQLite storage on Streamlit can disappear on a restart. The release does not migrate, reset, copy or overwrite the live ledger. Connected production storage is not exercised by local smoke tests.
4. **Check the candidate is still timely.** It must be selected before its earliest listed fixture starts. If the deadline has passed, rebuild and recheck a new candidate; do not override the expiry guard.
5. **Give explicit approval covering the candidate, selection and production cutover.** Merging into the app's tracked branch may automatically rebuild/deploy the app. Do not treat “merge” and “deploy” as safely separate actions on Community Cloud.

## After approval — not performed yet

6. **Prepare the selection for review on the development branch.** The owner runs the dry-run validation, then the guarded selection command below. It creates one small `active_release.json` file; it does not push or deploy. Commit that file on the existing branch and wait for green CI again. The full versioned bundle is already staged with the code; never copy individual model files into production.
7. **Merge/deploy only at the approved time.** Use the approved PR/commit, unchanged Python 3.14 and the pinned dependencies. The app checks every selected artifact and runtime before loading forecasts. A partial or mismatched release displays an unavailable message instead of mixing files.
8. **Check the live result.** Confirm the displayed release ID, forecast week, one complete market lookup, one unresolved-roof scenario, and the existing betting history/settings. Scenario-only rows must not produce prices or Top Picks. No automated real bet is placed by this release.
9. **If a check fails, stop using the new forecasts and follow rollback below.** Do not repair a live release by replacing isolated files.

## Weekly updates

The Tuesday 12:00 UTC GitHub Actions job is now **preparation-only**. It starts from an empty data/model directory, builds all required files, verifies the full result and uploads a candidate for review. Its token is read-only: it cannot push to `main`, change the selected release or deploy the app. Each weekly candidate therefore needs a separate approved selection. This intentionally replaces automatic production data pushes; unattended production publishing is not enabled.

Once a release is selected, games that have already started are removed from the app's slate and picks on rerun. When no future fixtures remain, no forecasts are shown; the app does not fall back to stale predictions.

## Rollback

- Keep the previous Git commit, selected-release ID and complete bundle. Every selection records the previous pointer; the original legacy data files are retained unchanged and hashed.
- **Forecast-only rollback with compatible code:** after approval, use the guarded rollback command below, commit the pointer change on the development branch, rerun CI, then approve/merge that rollback. Switching the pointer is atomic. It does not modify the ledger or any release files.
- On the first release, rollback can return to the retained legacy forecast files only if their recorded hashes still match. The app clearly labels this as legacy data; it is not a claim that the original modelling errors have been corrected.
- **Code or dependency failure:** restore the complete previously approved code/dependency/selection commit, not only the data pointer. Validate that combination in isolation before approving its merge/deployment. Do not downgrade Python or delete the app as an improvised rollback.
- An expired previous bundle may have no remaining future fixtures; an empty forecast view is safer than stale betting recommendations. Regenerate a fresh candidate before restoring normal forecast coverage.

## Owner command reference

Run these only in the matching, pinned Python 3.14 environment. Replace `CANDIDATE_ID` and `CURRENT_ID` with the reviewed values (`legacy` before first selection).

```bash
# Preparation only: does not select, commit, push, merge or deploy.
python scripts/prepare_release.py --id CANDIDATE_ID
python scripts/validate_release.py release_candidates/CANDIDATE_ID --app-smoke

# Default dry run: creates no selection file.
python scripts/activate_release.py release_candidates/CANDIDATE_ID --expected-current CURRENT_ID

# Only after explicit approval: create a LOCAL selection for review.
python scripts/activate_release.py release_candidates/CANDIDATE_ID --expected-current CURRENT_ID --write-pointer

# Only after explicit rollback approval: create the LOCAL rollback selection.
python scripts/activate_release.py --rollback --expected-current CURRENT_ID --write-pointer
```

These commands never commit, push, merge, dispatch a production workflow or change Streamlit settings. Those actions remain separately controlled. If the release code/runtime differs from an older bundle, use a coherent code rollback rather than bypassing validation.
