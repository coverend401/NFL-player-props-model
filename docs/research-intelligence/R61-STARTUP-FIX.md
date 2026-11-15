# P0 research startup correction — r6.1

## Exception reproduced before modification

Using the actual `odds_value_research.py`, real integrity-validated Stage 1A release and an r5 `sgo_research.market_ui` callable already imported into the process produced exactly:

```
TypeError: render() got an unexpected keyword argument 'compact'
```

The traceback ends at the same caller boundary reported from hosting: entrypoint → dashboard render → Top Picks → `render_collection(slate, release, compact=True)`. The actual hosted TypeError text was not supplied and private Cloud logs are unavailable, so the controlled reproduction establishes this matching failure mechanism, not a direct observation of Cloud's module cache. r5's actual source signature is `render(slate, release)`; r6 required a new optional keyword. A clean interpreter imports the updated callee and misses the warm-import compatibility failure.

## Minimal correction

Top Picks calls the stable **two-positional-argument** collection interface again. Both old and updated imported collection functions accept it. No catch-all hides a TypeError, no safeguard is disabled, and no authentication, secret parsing, quota, provider request, model, dependency or production code is changed. Labels identify r6.1. Existing collection details may appear within the expandable panel after capture; no extra request is triggered by rendering them.

## Verification

- Before-fix reproduction with real entrypoint/release: exact exception above; zero external requests.
- Regression tests exercise the actual entrypoint with real baseline data and configured synthetic root Cloud secrets, including the API key (not a missing-key early return). They preserve a warm two-argument callable and verify the complete collection widgets, all six workspaces, DataFrame/dictionary inputs and no external/provider/quota calls. A cold configured-key startup is also tested. These tests fail against the old three-argument call.
- **117 focused tests passed.** Full-suite result and final-head CI are recorded on PR #8.
- Beyond unit tests, a running Streamlit server executes the real entrypoint with the actual r5 module preloaded across reruns. Chromium at **390px** successfully unlocks a synthetic local password, renders Top Picks with expanded collection and visible Retrieve button, then all six workspaces. Document width = viewport width, zero rendering exceptions. Requests are blocked in the harness so no real provider/quota request is possible.

## One hosted verification step

After the branch updates, **Manage app → menu → Reboot app** for **nfl-props-research.streamlit.app only**, then reopen/unlock it and confirm **r6.1**, Top Picks and the expanded collection controls render without an exception. This restarts the process to remove mixed cached imports; a browser refresh alone may not. Do not reboot/repoint production or alter secrets. No API retrieval is required merely to verify startup.

Hosted private verification remains owner-required if the environment proxy still blocks access. Working r5 tag remains preserved. No new service, paid resource, credential rotation, quota reset, main merge, production change or dashboard development accompanies this P0 fix.

Final local result: **300 full regression tests passed** on Python 3.14 / PyArrow 24.0.0, including the two new real-entrypoint startup tests. **117 focused tests passed**. Ruff and whitespace checks passed. Production main remains `ad6b545e2a0e132d336806aa56a99fbee0e9cd04`; the deployment branch matched r6 before publication. No real API request or quota write was used to reproduce or verify this fix.
