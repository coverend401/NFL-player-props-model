# Free SportsGameOdds integration: resumed evidence review

Reviewed 14 November 2026. £0-only; no subscription, hosting/database upgrade or paid fallback.

**Documentary feasibility gate passed for isolated development. Live NFL coverage, UK jurisdiction, account entitlements and collection remain unverified.** Network restrictions are now resolved. Earlier blocked observations are retained in `SOURCES.json`; they were proxy failures, not API evidence. No key is configured in this Codex environment and no authenticated odds request has been made.

## Official documentation versus live evidence

| Requirement | Documentary finding | Actual account/quote evidence |
|---|---|---|
| NFL player props on Amateur | Pricing's Amateur card explicitly includes NFL and Player Props (included checkmark icons inspected) | Not yet tested |
| Free bookmakers | FanDuel, DraftKings, BetMGM, Caesars, ESPN BET, Bovada, Unibet, PointsBet, William Hill | Account/book/market availability unverified |
| UK relevance | William Hill and Unibet names included | Provider IDs do not prove UK sportsbook versions, availability to a UK account or matching settlement rules |
| Seven markets | Global market catalogue contains `passing_yards`, `passing_attempts`, `passing_completions`, `rushing_yards`, `rushing_attempts`, `receiving_yards`, `receiving_receptions` | NFL × bookmaker × seven-market coverage unverified; no claim all seven exist at either bookmaker |
| Both sides and actual lines | Game `ou` odd IDs have `over`/`under`; each `byBookmaker` quote has American `odds`, `overUnder`, `available`, `isMainLine`, `lastUpdatedAt` | Completeness/freshness not yet tested |
| Identity and timing | Event ID, NFL team IDs, provider player ID/name/team, kickoff, bookmaker update timestamp; client adds retrieval timestamp | No verified GSIS crosswalk; exact unique name/team/fixture matching only, otherwise unmatched |

The API account endpoint is reachable and returns **401 without a key**. This is connectivity/authentication evidence only. The current client uses documented `/v2/account/usage` and `/v2/events`, not unofficial endpoints. Public documentation and SDK schema examples are not genuine bookmaker quote evidence. Synthetic unit-test payloads are clearly labelled.

Sources: [pricing](https://sportsgameodds.com/pricing), [market catalogue](https://sportsgameodds.com/docs/data-types/markets), [bookmaker catalogue](https://sportsgameodds.com/docs/data-types/bookmakers), [odds schema](https://sportsgameodds.com/docs/data-types/odds), [events](https://sportsgameodds.com/docs/endpoints/getEvents), [usage](https://sportsgameodds.com/docs/endpoints/getUsageData), [rate limits](https://sportsgameodds.com/docs/info/rate-limiting), [terms](https://sportsgameodds.com/terms). Retrieval hashes/statuses in `SOURCES.json` are observation evidence, not original publication times.

## Allowance, refresh and collection budget

Pricing: **2,500 top-level objects per rolling 30-day period from first use; 10 requests/minute; 10-minute feed update frequency; unlimited monthly request count.** An event is one object regardless of its books/markets, and every response has a minimum one-object charge. Pricing says account-usage requests do not count. A 429 stops this client; no retry/upgrade.

The public pricing FAQ and rate guide disagree about the shared hourly object ceiling (250,000 versus 300,000). We do not resolve that by assumption: enforce the actual account's stricter limits and much smaller local limits. The actual provider interval-end timestamp is mandatory; there is no calendar-month reset assumption. Both current camelCase and older kebab-case usage schemas are supported; conflicting values fail closed.

Illustrative **six snapshots × 16 games = 96 event objects/weekend**, 384 over four weekends (480 over five). Each uncached fetch also checks account usage; normally 12 HTTP requests/weekend for six batches, plus a one-off account probe. A ten-minute cache avoids repeated collection on reruns. This is a proposed manual trial budget, **not an activated schedule**, and does not guarantee each game has props at every snapshot.

Each request reserves its maximum 16 objects even for empty/error/partial responses; no refunds or automatic pagination. Budget test uses provider-reported consumption **plus all local reservations** (deliberate over-counting), capped at 2,000 and at least 200 below the reported monthly allowance. Thus 96 returned + 96 reserved = approximately 192 budget units/weekend, before other uses. All HTTP calls are capped at six/minute including usage calls. One private durable SQLite quota store must cover every collector using this key. External use of the same key can exhaust the allowance; account preflight and 429 halt protect against that, but simultaneous external clients cannot be made atomic by our store. Do not share the research key across collectors.

## Data use and retention

Terms version 3 (23 June 2026) grants subscription-term use and permits end-user applications with independent material value. It prohibits standalone data feeds, bulk exports, database access, resale/redistribution, competing-model training and public service benchmarks without permission. Broad derivative-work language needs clarification before expanding distribution or making a public historical quote archive. The rate guide recommends caching; that is **not** a perpetual data-retention licence.

On termination/expiry: cease data use and delete obtained data, including cache/backups, within 30 days (subject to narrow stated exceptions). The implementation provides a private short-lived pregame cache only; old quote-cache entries are pruned on access/write after 24 hours. The owner must remove remaining cache files on expiry/termination; inactive processes cannot perform automatic deletion. Quota counters contain no quotes. Provider notices are retained/displayed; there is no quote export or public API benchmark. Paper payload preparation exists, but archival and settlement deliberately remain disabled pending separate retention/seal approval. No results endpoints or sealed outcomes are requested.

Free account signup must explicitly select **$0 Amateur**, not a paid trial. Terms allow payment information to be requested even for free plans and some trials convert to paid; we cannot promise no card will be requested. Do not select any chargeable/trial option or enable overages. No account/resource has been created by Codex.

## Current decision

Continue offline/synthetic development; ready to prepare a controlled authenticated coverage test after the owner configures a free key and approves a private durable trial store. **Not yet ready for automated Community Cloud operation:** its ephemeral local disk cannot certify durable quota accounting. No production Supabase tables/resources were touched. A free persistent deployment design and data-use/UK-variant confirmation remain separate approval decisions. Do not purchase anything to resolve these gaps.
