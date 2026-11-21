# Cost audit — no new paid resource

15 November 2026. This implementation creates **no subscription, account, hosting app, database, paid runner, API plan, trial, credit purchase, billing setting or billable external integration**. It uses the existing task workspace and installed open-source packages; no additional Codex agent, model API call or paid compute instance is provisioned.

| Existing service | Free constraint / evidence | Code safeguard / exposure |
|---|---|---|
| SportsGameOdds Amateur | Previously authenticated active $0 Amateur; 2,500 event objects per rolling 30 days; documented ten requests/minute, ten-minute refresh | Active Amateur rechecked before uncached requests; local six calls/minute including account checks; lifetime cap ≤2,000 plus provider used-object totals and ≥200 headroom. Reservations precede bounded requests, never reset/refund. No retry, paid fallback or schedule. External account changes are owner-controlled. |
| Streamlit Community Cloud | Existing owner-confirmed free deployed app at the same URL | No new app, upgrade, storage feature, secrets or branch configuration. Manual interactions only. Free resource/sleep constraints can affect availability rather than enable paid capacity. |
| Public GitHub model repository / CI | Repository API confirms `visibility=public`, `private=false`; existing workflow uses standard `ubuntu-latest` runners | No larger runner, workflow, storage plan or paid minutes purchase introduced. Standard public-repository Actions are the existing free path. No private-repository Actions are added. |
| Private GitHub quota repository | Existing owner-created free repository; Contents API used for small state | Only counters/times/proof, no odds/keys/models/account profiles. Conditional SHA writes, bounded conflicts and no reset. Authentication probes are bounded GitHub GETs, consume no SportsGameOdds objects, and do not write counters. GitHub rate limits can stop requests; no paid fallback. |
| Local cache / UI state | Existing ephemeral research host disk and memory | Existing ten-minute cache reuse / 24-hour access-time pruning; new session-only snapshots ≤6 windows / 15 minutes. No durable database, quote export, outcome archive or retention assumption. |
| Supabase | Production remains existing owner configuration | No new database, queries, ledger writes or Supabase usage from this research app. No production credentials needed. |
| Python / charts / browser checks | Already-installed pandas, NumPy, SciPy, Altair, Streamlit and Chromium/Playwright | No dependency/lock changes, paid library, remote font, image service or browser-testing subscription. |
| Codex / existing account billing | Existing task and account entitlement; billing not exposed to the workspace | No extra agent, new paid API, model service or credit/overage purchase invoked. Existing subscription/task consumption cannot be independently priced or certified as £0 from inside this task. |

**Incremental paid infrastructure/resources/services introduced: none.** The architecture has no newly introduced ongoing paid dependency. No billing was enabled or changed. This does not claim visibility into the owner's existing subscriptions, previously enabled billing or unrelated account activity; a blanket £0 account invoice cannot be verified by code.

## Allowance use

No live odds are requested to repeat regression/UI tests: tests use synthetic fixtures and existing public frozen aggregates. The owner's more recent successful hosted collection means older Codex counts are not current usage reports. Do not present the last historical 15/2,500 observation as today's remaining allowance.

The preserved UI reserves at most 16 event objects per uncached request/window even if fewer are returned; cache hits do not reserve again. One request with three books and all returned supported markets still charges by returned events, not by every quote. Examples: a one-event response consumes one provider object but conservatively reserves 16 locally; a complete 12-fixture pass via separate selections can reserve up to 192. The code deliberately double-counts provider usage and lifetime reservations and can stop well before 2,500. No cycle reset is inferred from a calendar date. Account usage shared outside this collector is still governed by the provider's free limit.

If a limit, auth condition, storage proof or response safety guard fails, collection stops. Do not upgrade, replace/reset counters, activate polling, enable paid resources or keep retrying. Unknown additional costs mean that feature remains unavailable.
