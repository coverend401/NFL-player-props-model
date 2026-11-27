# r8: event-specific full-slate research

## Verified incident evidence

The owner's r7 hosted statuses on 15 November 2026 establish:

| Fixtures | Observed pipeline result |
| --- | --- |
| NE–DET | Retrieved; previously matched bookmaker research |
| BUF–NYJ, CAR–NO, HOU–CLE, JAX–TEN, MIN–GB | Requested main kickoff window; HTTP response rejected by `UNSAFE` before JSON parsing, event/player matching or price eligibility |
| SEA–LV, PIT–CIN, LAC–BAL | Not requested after the earlier failure; also subject to r7's three-uncached-window limit |

`Client._request` in r7 used the same `UNSAFE` diagnostic for either an HTTP body exceeding **8 MiB** or the supplied API credential appearing in that body. The rejected body and byte count were not persisted. It is therefore impossible to prove which branch fired from the supplied statuses. A large multi-event player-prop response is a plausible mechanism, not an established provider-coverage gap. Prior authenticated discovery identified seven main-window NFL events, including the five desired fixtures; this does not verify their US player-prop prices. No new live provider request was made for r8 diagnosis.

Timezone, matching, missing markets, pairing, freshness and rendering could not explain those five specific failures: they occur after the guard that stopped the response. The three later games supply no evidence of provider absence. No claim of nine-game bookmaker coverage is justified.

Read-only inspection confirmed that the existing private ledger retains its prior lifetime reservations, conditional-update proof and `manual_review_required` halt. Its private counter is a conservative reservation total, not a verified current provider usage/remaining allowance. r8 preserves this halt, every reservation and the counter. It neither retries through it nor provides a reset/recovery button. Fresh live coverage remains blocked pending separately authorised reviewed recovery.

## Collection architecture

Official sources consulted: [GET events](https://sportsgameodds.com/docs/endpoints/getEvents), [official OpenAPI schema](https://sportsgameodds.com/openapi.json), and the official odds documentation. Documentation is distinct from authenticated evidence.

1. Reuse permitted fresh private/session quotes first. Load event identity catalogues separately; discovery cannot masquerade as price evidence or supersede an earlier quote.
2. Discover upcoming NFL fixtures in a bounded UTC window using the documented small `points-home-game-ml-home` response shape. Do not require `oddsAvailable` during discovery. At most two pages of 16 events; follow opaque `nextCursor` unchanged, even on a short page. Repeated/no-progress cursors stop safely. An exhausted page cap is labelled partial, not provider absence.
3. Match unique away/home identities and kickoff within 60 seconds. Keep provider event IDs/aliases and catalogue retrieval timestamps. Event identity is not injury/availability evidence.
4. Request prices for at most **two specific event IDs per batch**, prioritising earliest eligible kickoffs without fresh matched prices. All three US research books remain supported. A player-ID response filter is used only when every complete forecast player in the batch maps uniquely to an observed provider identity; otherwise omit it, rather than silently lose unmatched legitimate players. All supported canonical markets remain available to normalisation; no wildcard market filter is invented.
5. Official documentation says event IDs override event-selection filters. Therefore locally recheck NFL/pregame status, requested ID/alias, both teams, kickoff, absence of results and T−60. Recheck the decision cutoff after foreground rate waiting, before sending a request. Unrelated or post-cutoff responses never become recommendations.
6. Retain the existing account-tier/usage preflight **before every uncached event request**, CAS reservation, no refunds/reset, £0 account requirement, 2,000-object conservative cap, 200-object headroom and six provider HTTP calls/minute. Controlled foreground waits (25-second chunks, six-minute total budget) are not polling or retrying. Any failed request stops subsequent new requests.
7. Keep the original 8 MiB and credential-echo guards. Record only safe response byte counts and distinct `RESPONSE_SIZE_LIMIT` / `CREDENTIAL_ECHO` codes. Never log the body or any credential fragment.

### Conservative bounds

For `n ≤ 16` eligible fixtures, at most `32 + n` reserved objects and `2 × (2 + n)` provider HTTP calls. This upper bound allows two discovery pages plus individual-event retrieval, although the implementation batches two events. For the current nine fixtures: **41 objects, 22 HTTP calls maximum**. With one discovery page and five two-event price batches: **25 reserved objects, 12 HTTP calls** before cache savings. A maximum 16-fixture slate has a 48-object/36-call bound. Failed attempts remain counted conservatively; actual quota accounting always comes from the private atomic ledger and provider account preflight. An estimated bound is not a promise of availability or an actual usage report.

## Recommendations and cache

Top Picks places ranked WATCH comparisons first, or explicitly labelled PASS comparisons when no positive estimate exists. Every unpriced/unsupported-price fixture can show a complete independent Stage 1A model candidate. Top 2 by Game uses distinct players: eligible WATCH comparisons first, then honestly labelled PASS comparisons; absent usable priced comparisons it falls back to model-only forecasts. It never forces a second player or adds a fictional line, side, probability or EV to model-only cards. Model-only ranking is projected production rank within market, not betting value or an independently validated confidence measure.

Against the actual unchanged Stage 1A bundle at pre-cutoff validation: **780 rows, 566 complete forecasts, nine eligible fixtures, two distinct-player model-only candidates in each (18 cards)**. This is forecast coverage, not demonstrated bookmaker coverage. Existing player usage/pressure context, missingness, residual-scale uncertainty and qualitative matchup hypotheses remain available on expandable cards. No forecast or probability is adjusted.

Dynamic fixture states distinguish accepted no-event/no-market responses, matching failure, stale/eligibility exclusions, safety rejection, unattempted/partial discovery and fresh bookmaker research. Technical evidence is collapsed. No stale historical snapshot is promoted as a current quote. New event-ID responses supersede only their requested event/book scope, including empty/withdrawn responses; an update for one game cannot erase a different game at the same kickoff. Provider aliases survive permitted cache restoration. Old superseded quotes do not reappear.

The existing owner-only local cache is reused: 10-minute disk reuse, unchanged 15-minute provider/session age ceiling, original timestamps, 24-hour pruning. Catalogue/audit metadata are private and limited to 24 hours. No odds enter the quota repository. Streamlit local storage is ephemeral: reopen within the same running host can restore permitted files, but host replacement/redeployment may lose them. No durable odds archive or indefinite retention is claimed. No automatic provider calls on page load.

Parlay Research remains research-only: valid leg-price arithmetic is labelled an arithmetic product, never an actually quoted parlay. No combined probability or EV is inferred; same-game, teammate, opposing-selection and missing/expired/PASS/model-only restrictions remain enforced.

## Deployment and recovery

The research entrypoint remains `odds_value_research.py`, on PR #8's existing deployment branch. r7 is preserved at tag `research-r7-working-20261115` / commit `2238b81`. Main, Stage 1A artefacts, Python 3.14, PyArrow 24, authentication, Supabase, bankroll settings, frozen benchmarks, the sealed outcome period and the disabled legacy updater are unchanged.

After branch deployment, on iPhone open the existing research URL, authenticate, and confirm **r8**. Open **Top 2 by Game**: all still-eligible complete-forecast fixtures should show up to two cards. Expand a card for measured evidence, hypotheses and limitations. Collection controls and diagnostics remain collapsed. The existing ledger halt will still block collection; do not edit/reset it or repeatedly press collection. A separately approved, CAS-protected halt-only recovery must preserve counters, all reservation records and verification state before a small live test can establish new coverage. The Munich cutoff stays 13:30 UK; main Sunday fixtures 17:00 UK. Late data cannot become pre-cutoff evidence.

## Cost and outstanding limitations

Incremental cost **£0**. Existing Streamlit Community Cloud, GitHub repository/quota storage and SportsGameOdds Amateur allowance only; no services/accounts/subscriptions, paid compute purchase, schedules, billing, infrastructure upgrades or dependency changes. Hard application cap remains below the 2,500-object rolling 30-day provider allowance; no reset or assumption of rolling budget renewal is introduced. No API polling, public credentials or raw-response logging. The private lifetime policy can stop earlier than provider allowance. No guarantee of bookmaker completeness, UK availability, actual bet acceptance, injury confirmation, calibrated betting profitability or same-game joint probabilities is made.
