# Reproducing Stage 1C.1 without touching production

Use Python 3.14 and the existing pinned `requirements.txt` / validated lock (including PyArrow 24.0.0). Do not replace production release files, run the weekly updater, select a release, open the final period or supply a paid-provider credential.

```bash
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
python -m pip check
python -m unittest discover -s tests -v
python -m stage1c1.artifacts experiments/stage1c1/controlled-20261114-v1 --replay
python scripts/report_stage1c1.py experiments/stage1c1/controlled-20261114-v1
python scripts/validate_release.py --all-candidates --app-smoke
```

The archive validator recursively verifies all frozen baselines, runtime/source/input/payload hashes, identical eligible labels/populations, cutoff ordering, common probability methodology, separated hindsight outputs and the full 360-model matrix. Replay recomputes every candidate point forecast, interval and probability from the saved models and committed small inputs. CI runs the same replay on Python 3.14. Python 3.12 exercises portable unit tests but intentionally skips runtime-pinned archive tests; it is not the release target.

The preregistered scientific source commit is `f589ef3`. Model fitting requires clean committed scientific sources and a new immutable ID:

```bash
python -m stage1c1.runner --id YOUR_NEW_RESEARCH_ID
```

Do not rerun with changed settings to optimise the observed development outcomes. A changed scientific question requires separate approval and protocol registration. The existing experiment directory cannot be overwritten.

Exact aggregate ETL regeneration also requires the original raw PBP bytes whose hashes are recorded in the input manifest. The upstream release URLs can serve revised bytes; current downloads are not automatically equivalent. Raw caches were preserved outside Git. The committed aggregates suffice for exact saved-model replay but cannot establish historical publication authenticity.

## Production and research separation

PR #5 was merged at `d90f4629cf4681ef575e3889954d8b37704bf36b` as research retention only; its main-branch CI run `43523137545` passed. The owner confirmed that the authenticated app still loads Stage 1A release `stage1a-20261113-py314-arrow24-r2`. Stage 1C.1 is developed separately from that commit.

Stage 1C.1 changes only its new research namespace, input/archive bundles, tests, reports, documentation and the existing CI workflow's additional validation step. The app, release selector/loader, dependency pins, active release, trained production models, data, frozen research packages/archives and production Streamlit configuration remain unchanged. No Supabase tables, authentication, ledger or bankroll setting is accessed or changed. The weekly updater remains disabled. Nothing in the production app imports Stage 1C.1.

This work does not authorise a merge, deployment, dashboard host, paid source, experimental pricing activation or C3–C6 implementation. The final 2026 week-11 onward period remains sealed, including subsequent seasons.

## Completed local validation

- Python 3.14: 169 tests passed, no skips; includes archive matrix/population, payload tampering and relabelled-oracle rejection with a recomputed hash.
- Python 3.12 reference: 169 tests run, nine intentional runtime-pinned archive skips; all remaining tests passed.
- All 360 saved models replayed successfully, with point forecasts, intervals and probability probes matching the committed archive at 1e−12 tolerance.
- Manifest/source/input/runtime/semantic validation passed for nine versions and 55,303 identical player-market games per version; 49,034 development games and 6,269 monitoring games are kept separate.
- Dependency compatibility: `uv pip check` checked all 69 installed packages successfully. The managed local virtual environment has no pip module; CI's standard Python environment uses `python -m pip check`.
- Production candidate validation and Streamlit local smoke passed: nine models, 780 slate rows and 18 Top Picks; all production predictions replayed. Rollback rehearsal passed with the local test ledger marker unchanged. Archived incompatible candidates are checked for integrity but remain ineligible for selection.
- Ruff undefined/unused-name checks, formatting and Git whitespace checks passed. The production and frozen-benchmark path diff against `d90f462` is empty.
- GitHub main was reconfirmed at `d90f4629cf4681ef575e3889954d8b37704bf36b`, with no active workflow runs and the weekly updater `disabled_manually`, before opening this research PR. The additional PR CI results should be checked on its final head.

Execution recovery used the existing task/workspace and preserved the running experiment process, cached inputs, commits and branches. No reset, re-clone, task replacement, production change or merge was needed.
