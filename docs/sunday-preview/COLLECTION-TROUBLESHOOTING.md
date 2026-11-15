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

## r4 — quota authentication selection and transport

A real hosted `GITHUB_READ_401` confirms GitHub rejected authentication **before** private quota state was read. It is not evidence of exhausted SportsGameOdds allowance, a cutoff failure or a missing Contents write permission. An active token in GitHub settings does not prove the same byte string reached GitHub from the host.

Two replacement paths were found and removed:

- The generic secret helper preferred process environment over Cloud Secrets. For the quota credential specifically, **root-level Streamlit Secrets is now authoritative**; environment is used only when that key is absent. An explicitly empty/malformed Cloud value fails closed rather than falling back to a different credential. This is scoped to the quota token; research authentication and production settings are untouched.
- Requests can consult `.netrc` and replace an explicitly provided Authorization header if no explicit auth object is supplied. GitHub quota requests now use an explicit Bearer AuthBase object, which assigns exactly `Authorization: Bearer <selected-token>` during request preparation. Network proxy/TLS defaults remain enabled, redirects remain disabled, and unrelated GitHub/SGO credentials are not selected. Only surrounding whitespace is trimmed; quotes, Bearer prefixes and embedded whitespace are rejected, never guessed away.

No evidence proves either replacement happened on Streamlit. Codex's managed GitHub proxy can supply its own repository identity, so its successful quota access did not independently authenticate the owner's PAT. The r4 changes make the independent hosted credential path explicit and testable without displaying any token part, length, hash or fingerprint.

### Existing app update

1. Keep the same research app, branch and entrypoint. After the PR #8 branch update, wait for Community Cloud to rebuild; confirm **research preview r4**. If necessary, use **Manage app → menu → Reboot app** on the research app only. No main merge, token rotation or counter reset.
2. In this research app's **Settings → Secrets**, keep the existing token under the exact root-level name `SGO_GITHUB_QUOTA_TOKEN`. Correct TOML uses one pair of syntax quotes around the existing token value, not literal extra quotes inside the value. Do not include `Bearer `, a whole assignment as the value, a multi-line block, or a nested table. Preserve all other secrets. Do not paste the token in chat or GitHub.
3. Unlock r4 and open Collection diagnostics. It should say **recognised format; source: Streamlit Secrets**. This is a local shape/source check, not a claim of validity. Missing and malformed are distinguished without a GitHub call. Supported current PAT formats are checked without printing their actual prefix or any credential-derived identifier.
4. Select a T−60 eligible fixture and Retrieve once. A malformed-value diagnostic means no GitHub request was sent. A continuing `GITHUB_READ_401` means GitHub rejected a recognised-format token using the explicit Bearer path; report only that code and source label. Do not broaden permissions, regenerate the token, clear quota or keep retrying. We must investigate the remaining external credential/host issue without pretending it is resolved.
5. On success, confirm fresh benchmark cards and the unchanged production baseline. Read permission success does not substitute for the atomic write/conflict protections, which remain mandatory.

r4 focused validation: **94 tests passed**, including eight credential-resolution/transport regressions added to the hosted-path coverage. Tests verify authoritative Cloud secret selection, environment fallback only when absent, empty/malformed values failing closed without credential substitution, outer-whitespace-only normalisation, exact prepared Bearer headers with `.netrc` override prevented, no redirects, explicit empty-token rejection, and safe genuine-401 classification. No real credentials or quota writes are used by these tests. Ruff and whitespace checks pass; final-head CI remains a separate gate.

## r5 — distinguish managed identity, parsing and real authentication

**Observed controls:** within Codex, GET `https://api.github.com/user` returned 200 with no explicit authentication and also with a deliberately invalid synthetic credential sent through explicit AuthBase. Therefore this task's managed network can substitute GitHub identity. The previous private persistence/CAS proof remains a valid repository/storage proof, but is **not proof the configured PAT authenticated**. No proxy/TLS bypass or token rotation was attempted. An independent direct PAT test is not possible through that managed boundary; it must run on the research host.

**Official format evidence:** GitHub's [authentication documentation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github) identifies the `github_pat_` prefix for fine-grained PATs. Its [official public Markdown source](https://github.com/github/docs/blob/main/content/authentication/keeping-your-account-and-data-secure/about-authentication-to-github.md) was retrieved through GitHub's public Contents API when the docs website was unreachable from this environment. This source documents token prefixes, not the full application regex used by r4. A normal alphanumeric fine-grained PAT already matches r4; no evidence establishes that a legitimate PAT in the owner's Cloud app actually violates the regex. We cannot inspect that hosted secret. **Do not infer actual token corruption or validity from that old generic code.**

r5 treats credentials as opaque rather than imposing a prefix, alphabet or length contract. It retains header-safety/type checks and delegates authentication to GitHub. Safe local failures distinguish: `TOKEN_TYPE`, `TOKEN_QUOTES`, `TOKEN_SCHEME`, `TOKEN_WHITESPACE`, `TOKEN_HEADER`, and missing `CONFIG_TOKEN`. No character, prefix, length, hash, fingerprint or account identity is returned. Normal TOML quote delimiters are removed by parsing and do not fail validation; literal extra quotes inside the parsed value are not silently repaired. Only surrounding whitespace is trimmed. Streamlit root Secrets remains authoritative over environment values; there is no string conversion of token tables/numbers or alternate-identity fallback.

**Before creating a hosted quota store**, the explicit-token GitHub transport now makes an invalid-credential negative control to `/user` (must return 401), followed by the supplied token's `/user` request (must return a valid authenticated response). If the invalid control succeeds, `AUTH_SUBSTITUTION` stops collection **before the real token or quota state is read/written**. If the control is inconclusive, it also stops. This intentionally blocks the managed Codex path rather than mislabelling it a PAT success. Valid-format real-token 401 becomes `TOKEN_REJECTED`; actual-user 403 becomes `AUTH_PERMISSION`; repository 403/404 remain separate repository-access diagnostics. Even a successful auth probe does not replace private repository, stored proof, halt, allowance, conditional-write or T−60 checks.

### Existing research app: exact r5 check

1. Keep the same app, branch and entrypoint. Wait for the automatic branch update and confirm **research preview r5**. If it stays on r4, **Manage app → menu → Reboot app**, research app only.
2. Do not rotate, reset or broaden access. Open Market Intelligence → **Collection diagnostics**. The status now says **header-safe string; source: Streamlit Secrets** or a specific local reason code. A header-safe string is not a claim of validity.
3. Click **Check GitHub authentication (read-only; no odds)** once. It makes only GET requests to GitHub: the negative control, real authentication and private quota-state read. No SportsGameOdds call, GitHub counter write, CAS proof replacement or budget reset occurs. A private ephemeral SQLite cache may be opened locally; this does not change durable quota state.
4. Report only the diagnostic code and source label, or confirm the success message. `TOKEN_TYPE` means a string/table/type issue; `TOKEN_QUOTES` means extra literal quotes, not normal TOML syntax; `TOKEN_SCHEME` means an added Bearer prefix; whitespace/control/non-ASCII receive separate reasons. Do not send screenshots of Secrets or quote any token content.
5. `TOKEN_REJECTED` means the host's negative control behaved correctly but GitHub rejected the supplied opaque token. That is not a quota or cutoff issue. `AUTH_SUBSTITUTION` means a credential-substituting intermediary prevents independent verification: stop. `GITHUB_READ_403` / `GITHUB_READ_404` after successful user authentication mean repository access still needs investigation. Do not force collection or change quota protections.
6. After a successful read-only test, select a T−60 eligible fixture and Retrieve once. Collection repeats authentication verification and all existing atomic quota safeguards. Writes are proven only by the actual protected quota operations, not by the read-only test.

This adds two bounded GitHub GETs to each store setup/manual collection. They consume no SportsGameOdds objects, require no paid service and are not scheduled or automatically polled. The deliberate invalid control is not retried. No app-specific credentials or account details are printed, stored in the quota repository or committed.

r5 focused validation: **102 tests passed**, including opaque header-safe values, specific safe parsing reasons, normal TOML delimiters, auth substitution rejection before real credential/quota access, expected negative-401 then authenticated GET-only behavior, distinct real 401/403 handling, and factory fail-closed. A live synthetic control confirmed the new verifier returns `AUTH_SUBSTITUTION` in Codex. No actual token was used by that live control; no counter writes or SportsGameOdds requests were made. Full local regression and final-head CI are reported separately on PR #8.
