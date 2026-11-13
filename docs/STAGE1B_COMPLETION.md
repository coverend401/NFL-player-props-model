# Stage 1B completion record

PR #3 was merged as research infrastructure only on 2026-11-13, commit
`15a40282f347a76238ee29b8821c3fe8b3aa0223`. Post-merge regression/release checks
passed (Actions run 43503248475). This completed the approved research scope;
it did **not** approve experimental forecasts or prices for live betting.

The active pointer remains `stage1a-20261113-py314-arrow24-r2`. The production
app, pricing/betting/ledger modules, dependencies, selected release payload,
pipeline, authentication and Supabase configuration were not changed by PR #3.
No Stage 1B code is imported by the production app. A normal Cloud refresh on a
main-branch commit is possible, but this merge introduced no production behaviour.

The standalone research dashboard remains `stage1b_dashboard.py`; hosting it
requires separate approval. Nothing in Stage 1B.1 deploys or hosts it.

The frozen benchmark remains `experiments/stage1b/baseline-20261113-v5` and its
original source package remains unchanged. See `STAGE1B_RESULTS.md` and
`STAGE1B_VERIFICATION.md` for the accepted results, regressions and limitations:
retrospective corrected statistics, conditional observable-participation population,
no authentic odds archive, no proven profitability, small method-selection windows,
wide intervals and passing-yard point-model weakness. The final 2026 week-11 onward
period remains sealed. Retrospective 2022–25 and 2026 weeks 1–10 have already been
inspected and are development/monitoring data, **not untouched tests** for Stage 1B.1.
