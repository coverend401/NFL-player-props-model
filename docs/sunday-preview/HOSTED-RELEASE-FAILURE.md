# Hosted release failure: obtain the actual rejection before correcting it

**Update:** The owner identified certifi drift. The managed environment is now
covered by [separate serving-runtime recertification](CLOUD-RUNTIME-RECERTIFICATION.md).
Follow that document for current verification; the original diagnostic history below
does not mean that production's old dependency lock has been changed.

The owner's authenticated hosted error is real. Green CI and a successful local
render do not establish hosted availability. The app's existing catch combines
all release-loader and initial-parquet failures into "Approved release
unavailable. Research comparison disabled." That message alone does not identify
which guard failed or prove which checkout the host is running.

Expected configuration for the existing research app:

- Repository: `coverend401/NFL-player-props-model`
- Branch: `sportsgameodds-free-feasibility`
- Entrypoint: `odds_value_research.py`
- Python: `3.14`; pinned packages from `requirements.txt` and
  `requirements-production.lock`, including PyArrow `24.0.0`.
- Pointer: `research_active_inference.json` (default), selecting
  `research-week11-frozen-20261120-r2`.
- The default pointer's approved manifest SHA-256 is
  `2ef8e0a19da56705e31d3af0f72b1b4dd71bd3a3a5d5a8c8fc4a5016d0e1a021`.
- The enhanced selection bundle is
  `research_selection_releases/enhanced-sunday-20261121-v1` (522 rows).
  Its parent certified bundle has 618 rows, including 50 roof scenarios and
  non-Sunday forecasts. These counts are deliberately different.

The pointer, manifests, parent model bundle and enhanced forecast files are
present in the expected Git checkout and validate locally. The deployed
checkout, runtime and actual hosted rejection remain unverified until observed
through the hosted diagnostic or owner-supplied settings/logs. No claim is made
that a missing-pointer reproduction establishes the actual hosted cause.

## Owner action on the existing research app

1. Allow the research branch update to apply, or reboot **only the research app**.
   Do not change production settings or secrets.
2. Log in using the existing research password. Expand **Authenticated deployment
   diagnostics**, above the generic error. It is available even when release
   admission fails. It must show `hosted-release-preflight-r2`.
3. Read the **actual commit, branch, repository and Python version**. If the Git
   metadata is unavailable, inspect the app's GitHub configuration in Community
   Cloud and report those fields. Do not infer its branch from GitHub CI.
4. Click **Check approved release loading** once. This repeats the real admission
   and initial parquet read, without network calls, model fitting or data writes.
5. Share the diagnostic JSON only. Do not share passwords, API keys, tokens or
   the complete Streamlit Secrets contents.

`RESEARCH_POINTER_MISSING`, `RESEARCH_POINTER_HASH_MISMATCH`,
`RESEARCH_SOURCE_HASH_MISMATCH`, package/runtime mismatch and missing-artifact
failures have distinct codes. Package failures show only the pinned package name
and expected/installed versions. Unknown failures show an exception type rather
than raw exception text or paths. Credentials, environment values and raw
tracebacks are not displayed.

If the panel is absent, that itself establishes that this diagnostic update has
not reached the hosted process; check the configured branch and reboot before
assuming the latest commit is deployed. Do not change model files or disable
admission to remove the error. A PASS from this preflight must be followed by an
authenticated check that the actual enhanced cards and manual comparison render.

## Regression coverage

The actual `odds_value_research.py` is tested with a deliberately missing pointer:
after authentication it reproduces the exact generic error, and the on-demand
diagnostic identifies `RESEARCH_POINTER_MISSING`. Forecasts remain blocked.
Additional tests cover runtime/source/hash classification, secret redaction and
unchanged failure behaviour. The certified entrypoint and validator source files
are unchanged, so no provenance hashes or approval metadata are rewritten.
