# Hosted collection diagnostics (research preview r3)

The owner confirms Python 3.14.10 / PyArrow 24.0.0, authentication and both dashboards start on https://nfl-props-research.streamlit.app. Authenticated Cloud logs and that host's credentials are not accessible to Codex. The original generic warning does **not** establish an exact root cause.

## Verified findings

- The old catch handler discarded every collection failure, including GitHub read/write HTTP failures. New allowlisted codes and fixed operator guidance expose the gate and collection stage without raw exception text, response bodies, account identifiers, paths, headers, URLs or credentials. Streamlit logs record only the fixed code and stage; unknown errors receive UNKNOWN, not a traceback.
- The old research entrypoint copied secrets into process environment. The revised path reads root-level Streamlit secrets directly (or preconfigured environment variables), passes the quota token explicitly, trims surrounding token/repository whitespace, and blocks a missing hosted token before calling GitHub or SportsGameOdds. The local `gh` fallback is not treated as hosted authentication. All settings belong in this research app, not the production app. The legacy nested API-key location remains supported.
- A separate reproduced bug validated newly retrieved quotes against the pre-network clock. Because captures arrive later than that clock, successful collection could produce zero comparisons. Freshness now uses a post-request clock, with no relaxation of timestamps, age or T−60 constraints.
- Read-only quota inspection during investigation found 17 reserved objects, conditional-update verification true and no halt. This rules out an already exhausted lifetime counter or existing halt at that inspection, but **does not prove the Streamlit host's token has access**. Managed Codex GitHub access is not equivalent to an independent host's personal token. No new SportsGameOdds events were requested for this investigation.
- At investigation time the early fixture was still before 13:30 UK. An expired T−60 window removes a fixture from the selector; stale provider odds affect benchmark inclusion after collection, rather than normally causing a GitHub collection failure. All cutoffs remain enforced.

## Update the existing research deployment

1. Check PR #8's final-head CI. The branch remains `sportsgameodds-free-feasibility`; entrypoint remains `odds_value_research.py`. Do not merge or change the production app.
2. Streamlit Community Cloud normally detects commits to that configured research branch and updates automatically. Open the research app and confirm its caption says **research preview r3**. If it still shows r2, use that research app's **Manage app → menu → Reboot app**. Do not recreate the app, reset quota or reboot production. A reboot can clear ephemeral cache, but not the private durable budget.
3. In **Settings → Secrets** for this app, keep the root-level names from DEPLOY-US-BENCHMARK.md. Do not share their values. `SGO_PRIVATE_CACHE_TERMS_ACK` is the string `"1"`; optional cap is an integer string from 1 to 2000. No Supabase secrets are needed.
4. Unlock the app, open Market Intelligence and expand **Collection diagnostics (no credentials shown)**. Confirm the four required secret names say configured. This checks presence only, not validity.
5. Select a T−60 eligible fixture and at least one US bookmaker. Click Retrieve **once**. On failure, report only the bracketed code and displayed stage. The logs also contain `Research collection blocked: code=... stage=...`. Do not send keys, tokens, raw response bodies or unrestricted logs.

## Interpret the code

- `CONFIG_TOKEN`: missing research quota token. Add the existing scoped token to this app's secrets.
- `GITHUB_READ_401` / `GITHUB_WRITE_401`: rejected/expired token; inspect its status privately.
- `GITHUB_READ_404`: repository/state not found **or** the token lacks selected-private-repository access. Check resource owner `coverend401`, selected repository `nfl-props-research-quota`, and Metadata read. The repository must remain private with existing `quota.json`.
- `GITHUB_WRITE_403`: read may work but write permission/rate limit does not. Fine-grained token needs **Contents read/write** on only that private repository. Inspect GitHub rate-limit/approval status privately. Do not broaden access to production.
- `CONFLICT`: conditional writes conflicted repeatedly. Wait before retry; do not remove CAS protection.
- `RATE`: wait at least 60 seconds before one manual retry.
- `HALTED`, `UNVERIFIED`, `STATE`, `BUDGET`, `UNSAFE`: stop and report; never clear, reset or replace the counter to force collection.
- `PROVIDER_AUTH` / `PROVIDER_RATE`: provider 401/403/429 triggers the existing durable halt. Stop for manual review; no automatic retry.
- `TERMS`, `BOOKS`, `CONFIG_CAP`: correct the indicated input/configuration; no provider request is made for these preflight failures.
- `UNKNOWN` / `SCHEMA`: report code/stage for investigation; no raw sensitive exception is displayed.

No change to the production application, dependency versions, private database, model artefacts, probability methods, sealed periods or frozen benchmarks. Hosted collection remains unverified until the owner retries and supplies the diagnostic or confirms successful retrieval.

## Regression evidence

Python 3.14 / PyArrow 24.0.0 focused suite: **86 tests passed**, including eight new hosted-path tests. These cover root-level secrets without an environment-copy bridge, missing-token fail-closed before network/local-gh fallback, GitHub read/write 401/403/404 classifications, unchanged 409 conflict handling, unknown/network exception redaction, visible/logged safe codes, and post-network capture timing. Ruff and whitespace checks passed. The original hosted exception still requires the owner's new safe diagnostic; no successful remote retrieval is claimed.
