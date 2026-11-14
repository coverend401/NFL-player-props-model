# SportsGameOdds free-only integration — Phase 1 evidence report

Review date: 2026-11-14. Branch: `sportsgameodds-free-feasibility`.

**Gate: UNRESOLVED / NOT PASSED. Stop before Phases 2–5.** This is not a finding that Amateur definitely excludes NFL props. It is a finding that the available evidence does not establish free entitlement, a usable UK bookmaker, the exact allowance or data-use rights. No adapter, value-analysis extension, Streamlit section, scheduled collector, paper ledger or database resource has been implemented/activated.

The requirement is **$0 ongoing operation**: no paid API, hosting/database plan, upgrade, paid trial or automatic subscription fallback. The earlier prospective proposal's paid budget options are superseded for this project.

## Evidence reviewed and limitations

Official public pricing/documentation and API hosts `sportsgameodds.com` and `api.sportsgameodds.com` are blocked by the execution environment's proxy. Read-only access to those exact domains has been requested. Failed proxy connections are not provider 401/403 responses and establish nothing about free-plan entitlements.

No `SPORTSGAMEODDS_API_KEY` or official-SDK default `SPORTS_ODDS_API_KEY_HEADER` is configured in this development environment. Production Streamlit secrets were not inspected or changed. No authenticated provider response or genuine bookmaker quote has been obtained. All probe test responses are explicitly synthetic, not NFL coverage evidence.

First-party GitHub material **was** accessible:

1. [Official player-props example](https://github.com/SportsGameOdds/player-props-analyzer): advertises NFL passing/rushing/receiving yards and receptions, alongside other sports; links to a free API key; its rate table lists Amateur (free), 10 requests/minute and "1 game at a time". Its default example is NBA. This is not an explicit current seven-market Amateur/UK entitlement matrix.
2. [Official live tracker](https://github.com/SportsGameOdds/live-odds-tracker): also lists Amateur at 10 requests/minute and recommends a 60-second polling interval. Recommended client polling is **not** a confirmed provider price-refresh guarantee.
3. [Official Python SDK](https://github.com/SportsGameOdds/sports-odds-api-python): defines events, players, markets, bookmaker-specific prices/lines, timestamps and `/account/usage`. Optional fields and global support types do not prove the free plan supplies those fields.

The source inventory records URL, retrieval/file-save evidence, content hash and blocked/accessible status. Source code MIT licences do not confer odds-data retention, commercial-use or redistribution rights.

## Requested confirmations

| Question | Verified documentation evidence | Live Amateur response evidence | Decision |
| --- | --- | --- | --- |
| NFL player props included in Amateur | First-party example advertises NFL props and a free tier, but no explicit per-tier NFL prop entitlement was obtainable | None | Unverified; do not infer access from marketing examples or a free key |
| William Hill access | No accessible authoritative Amateur bookmaker list | None | Unverified; do not guess bookmaker IDs |
| Unibet access | No accessible authoritative Amateur bookmaker list | None | Unverified; do not guess bookmaker IDs |
| UK sportsbook jurisdiction | Brand name is insufficient; US/international variants may differ | None | Must identify exact UK product and independently compare sample lines/prices |
| Both Over and Under | SDK has side IDs and includeOpposingOdds query support | None | Schema capability only; same-book/line pairs unverified |
| Actual bookmaker lines/prices | SDK has byBookmaker odds/overUnder/available/isMainLine | None | Must use bookmaker-specific values, not aggregate bookOdds or fairOdds |
| Player identifiers | SDK exposes playerID/statEntityID and event players | None | Real NFL mapping coverage unverified |
| Update timestamps | Bookmaker objects have optional lastUpdatedAt | None | Presence, granularity, timezone and freshness unverified |
| Exact monthly allowance | Account schema exposes per-month max-entities/current-entities and request counters | None | Numeric allowance and what counts as an object remain unknown |
| Request limits | Two first-party examples list 10 requests/minute for Amateur | None | Published example, not account-confirmed current contract; other interval limits unknown |
| Refresh interval | Tracker recommends 60-second client polling | None | Actual free-tier feed cadence/delay unknown |
| Reset policy | No verified reset period/timezone, shared-key/account scope or over-limit behaviour | None | Unknown; no collection schedule can be approved on guessed resets |
| Retention/commercial restrictions | SDK software licence available, provider data terms inaccessible | None | Unknown; no feed-data archive or redistribution authorised |

### Seven canonical markets

| Canonical market | General NFL mention in the accessible official props example | Amateur + UK bookmaker + usable two-sided quote |
| --- | --- | --- |
| Passing yards | Yes | Unverified |
| Passing attempts | Not established by the example | Unverified |
| Passing completions | Not established by the example | Unverified |
| Rushing yards | Yes | Unverified |
| Rushing attempts | Not established by the example | Unverified |
| Receiving yards | Yes | Unverified |
| Receptions | Yes | Unverified |

A missing example is not proof a market is unsupported. Generic NFL props are not proof that attempts/completions or either requested bookmaker are free. QB rushing uses the same two canonical rushing types, with player position matched separately; there are nine model markets but seven provider categories. No market identifiers, player identities or odds have been fabricated.

## Free-budget feasibility

The six-observation schedule previously discussed would require up to **16 games × 6 = 96 event snapshots per NFL weekend**, approximately **384 per four-week month**, before discovery, usage checks, pagination or retries. A lean two-observation design would require 32 per weekend / 128 per four-week month.

These are event snapshots, **not confirmed billed objects**. The SDK explicitly says `limit` bounds the number of Events returned; it does not say that one returned Event costs one object or that filters reduce billing. If a snapshot cost one object, six-observation monthly use would be 384 objects plus overhead. At 100 charged objects per snapshot it would be 38,400 plus overhead. Neither is a measurement of this provider.

For provider-confirmed monthly budget B, reserved headroom R and measured discovery/account overhead H, the candidate bound is `snapshots <= floor((B - R - H) / observed_charged_objects_per_snapshot)`. It also needs the actual per-minute/hour/day/request limits and documented reset semantics. Repeated unchanged responses might still be charged; assume nothing until documented and measured.

**Estimated actual object consumption per NFL weekend: unverified.** The request-count plan is calculable, but free affordability cannot be confirmed without the allowance, object definition and before/after usage evidence. No claim is made that a 500-, 2,500- or other object allowance applies.

If a free account supports only a small subset of fixtures/snapshots, propose an explicitly bounded free pilot rather than silently attempting the full schedule. If meaningful UK NFL coverage or the intended rights are unavailable free, stop. No paid fallback is permitted. Any future hard limiter must persist across restarts and all clients, reserve budget before calls, stop on unknown/exhausted state and prevent UI reruns from making unbounded requests. This limiter is a Phase 2 deliverable only after the gate passes; it is not implemented by the account probe.

## Prepared Phase 1 test — not an integration

`scripts/probe_sgo_free_account.py` is an **account-only**, manually invoked preflight. It uses the documented `/v2/account/usage` endpoint and `x-api-key` header, no SDK installation or query-string key. It makes at most one request, never follows redirects/retries, never requests odds, rejects a non-Amateur/inactive account and discards echoed credentials/error bodies. It saves only a whitelist of tier and numeric/unknown limit fields, outside the Git repository with owner-only file permissions. Email, customer ID and key identifiers are discarded. It always records `gate_passed=false` because an account tier alone is not prop/UK/licensing proof.

The current generated SDK initialises both header and query credential options from the same default environment variable. The prepared probe deliberately avoids that path and does not install or invoke the SDK. Never put credentials in URLs, command arguments, logs or repository files.

Safe account/key setup is in `FREE_ACCOUNT_AND_TEST_RUNBOOK.md`. The probe is ready for account verification **once network access and an owner-confirmed free Amateur key exist**, not for an odds-comparison live trial. No actual API coverage test has run.

## Gate acceptance before feature development

Require all of the following evidence, with sensitive account data excluded from Git:

- Current official plan/billing evidence that Amateur is $0 recurring, no paid trial/card/auto-upgrade is required, and applicable data-use/retention/display terms permit the intended private research and authenticated UI.
- An authenticated account report showing actual Amateur tier/limits, plus documented object charging/reset/refresh rules. A paid/trial response does not count as free evidence.
- Genuine pregame NFL prop responses on that tier for at least one specifically verified UK-accessible bookmaker. William Hill/Unibet are priorities, not assumed valid brand aliases. Document every one of the seven market results; if only partial coverage is available, return it for review before changing the requested scope.
- Bookmaker-specific line/price, both sides where offered, real event/player IDs and timestamp/freshness evidence; reject consensus/fair odds substituted for book quotes.
- A measured, no-upgrade collection budget that fits the exact free allowance with headroom, including metadata/usage calls and all planned clients. No hypothetical object total can pass this check.

A single empty response could reflect posting time rather than entitlement: check the documented pregame window and two suitable fixtures without uncontrolled retries. Missing rights or unresolved billing/jurisdiction remains a stop condition. Synthetic tests never satisfy these acceptance criteria.

## What was and was not built

Built: this evidence matrix, a secure account-only verification probe, seven mock-based probe safety tests, a credential/setup runbook and a bounded live-coverage test specification.

Not built because the gate is unpassed: modular odds adapter; decimal/fractional conversion integration; player/projection matching; EV calculations; mobile Odds & Value page; scheduled collection; prospective paper storage/settlement. No paid/free cloud resource, subscription or production secret was configured. The real bankroll and Supabase ledger are untouched.

Python 3.14 / PyArrow 24.0.0 pins, Stage 1A nine models/forecasts/auth/settings, the disabled legacy updater, all prior benchmark code/archives and the sealed 2026 week-11 onward period remain unchanged. The Phase 1 probe has no result/statistics endpoint and cannot inspect sealed outcomes. Any later paper settlement still needs a separate seal policy. The current proposal branch is not a production deployment.
