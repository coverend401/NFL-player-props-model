# SportsGameOdds Phase 1 — free account and bounded test runbook

**Stop conditions:** no paid subscription, upgrade, credit-card trial, API purchase or automatic scheduled collector. Do not paste any key, dashboard screenshot containing a key, account email or billing identifier into chat/GitHub. This prepares verification, not the integration.

## 1. Restore read-only network access

Allow `sportsgameodds.com` and `api.sportsgameodds.com` in this task's environment settings, then save/apply. The first hosts official pricing/docs; the second hosts the API. If another redirect is blocked, identify that exact host before requesting a further change; do not use a proxy to bypass the policy.

## 2. Create only a genuinely free account

1. Open the [official pricing page](https://sportsgameodds.com/pricing/) in your own browser and use its free Amateur signup link.
2. Confirm the account has $0 recurring cost and that there is no required card, paid upgrade or automatic paid conversion. If signup only offers a paid/card trial, stop and report that constraint.
3. Read the current Amateur feature list, monthly object definition/allowance, request limits, refresh delays and data retention/commercial/display rules. Save a non-sensitive reference/version or terms link; do not assume a free API key grants all markets.
4. If the account initially receives a Pro/Rookie trial, do not use trial coverage as Amateur evidence. Select/confirm Amateur or wait for the free tier; the prepared probe rejects other tiers.
5. Use the account's API-key section to copy the key privately. Exact current dashboard labels could not be verified because the site is blocked here.

## 3. Bind the key to development only

Preferred for this Codex task: add a **research secret environment variable** named `SPORTSGAMEODDS_API_KEY` to the development execution environment and save/apply it. Never put the literal value in a chat message, tool argument, GitHub issue/PR, source file or command history.

Do not change production Streamlit secrets for this Phase 1 test. A GitHub Actions repository secret is not automatically available in the current shell. If local development is used, inject the environment variable through your local secret manager; do not commit a .env or secrets.toml. Future dev-only Streamlit support is Phase 2/4 work and has not been implemented.

The probe uses `SPORTSGAMEODDS_API_KEY`, not the generated SDK's default `SPORTS_ODDS_API_KEY_HEADER`, so the SDK cannot accidentally add a query-string key. It sends only an HTTP header to the fixed HTTPS host, with redirects disabled.

## 4. Run the account-only preflight

Once you have verified the account is genuinely free and the domains are allowed:

```bash
/workspace/.venvs/nfl-props-314-arrow24/bin/python scripts/probe_sgo_free_account.py \
  --account-only --output /tmp/sgo-amateur-account-check.json
```

Choose a new output filename if it already exists. The command consumes at most **one account-endpoint request**, with no odds calls, retries or pagination. Whether this endpoint counts towards a particular allowance still needs provider confirmation. No API subscription is created by the command.

The report is owner-readable only and outside the repository. It deliberately excludes account email, customer ID, key ID and the key. Review only its sanitised tier/limit fields and timestamps. Unknown limits remain null, not zero or unlimited. A numeric max-entities value is an account-reported entity limit, not yet proof of the provider's definition of a billed object. An `Amateur` response still leaves `gate_passed=false`.

HTTP 401/403/429, redirects, malformed JSON, an echoed credential, a missing limit schema or any non-Amateur account stops verification. Errors do not print response bodies or URLs containing a credential. Do not retry into a quota limit or upgrade to solve an entitlement failure.

## 5. Bounded live NFL coverage test specification (not yet executed)

Only after reviewing current free entitlements/rights and understanding quota units:

1. Read account usage and record the before state. Determine whether usage calls themselves count. Confirm tier remains Amateur.
2. Obtain valid provider bookmaker IDs from its official catalogue/support response. Do not invent `williamhill` or `unibet` IDs. Establish whether each is the UK product rather than a US/international variant. Global `/markets` support is not automatically plan entitlement.
3. Select one upcoming **unstarted** NFL fixture using `leagueID=NFL`, `started=false`, `ended=false`, a bounded startsAfter/startsBefore window and `limit=1`. The SDK says limit counts Events, not necessarily billable objects. Keep `includeAltLines=false`, `includeOpenCloseOdds=false` and include opposing odds only for the agreed main-line test.
4. Use documented returned market/odd/player IDs for the seven categories; do not guess them from English names. Apply the selected bookmaker filter and request the smallest supported payload. No player/game results, historical stats or sealed outcomes are requested.
5. Inspect `byBookmaker` for genuinely offered `available` quotes: original odds, per-book overUnder line, side, main-line flag and lastUpdatedAt. Do not use aggregate `bookOdds`, `fairOdds` or `bookOverUnder` as that bookmaker's actual offer.
6. Record each category as available, absent, not offered yet, entitlement denied, schema incomplete or jurisdiction unverified. Retain no raw quote payload until retention rights are confirmed. Credentials/URLs must be redacted and any permitted evidence archive must remain private.
7. Read account usage afterward, including the cost of those checks, and compare actual charged entities/requests. Do not assume unchanged prices or filtered-out markets are uncharged. Obtain the reset schedule and refresh policy separately.
8. If budget and entitlement permit, repeat once for a second fixture and check a few lines/prices in the user's UK sportsbook interface. No automated bookmaker scrape or account login sharing. Do not keep retrying empty markets.
9. Calculate six-snapshot and lean two-snapshot monthly budgets with measured object cost/headroom. Return evidence for the gate review. If any material free/UK/rights/budget condition is unsupported, stop before the adapter/UI.

The account probe intentionally has no automatic event-test switch because object charging and free entitlement remain unverified. This test specification is ready to execute only when those preliminary checks make a bounded call safe. A later probe extension would be Phase 1 verification work, not permission to build the adapter prematurely.

## 6. Review boundary

Passing synthetic tests or seeing a free-key marketing page is not a live trial. No phases 2–5 start until the documented Phase 1 gate passes. If Amateur cannot provide meaningful genuine UK NFL props, report that and retain the working Stage 1A app unchanged. There is no paid fallback. No real bets, bankroll changes, Supabase writes, scheduled API polling or sealed-result review are authorised.

Questions for provider support if the documentation remains ambiguous (not sent on your behalf):

- Does the actual $0 Amateur tier include bookmaker-specific NFL player props for the UK William Hill or Unibet product, with all seven requested stats and both sides/lines/timestamps?
- What is the exact monthly entity/object allowance, how do filtered and repeated requests count, which account endpoints count, and when/how do all limits reset?
- What is the actual Amateur data-refresh delay rather than a recommended client polling interval?
- May this personal authenticated application retain original quotes and derived paper/CLV records for a season, and what private-display/commercial/public-redistribution restrictions apply?

Do not send an API key with those questions, and do not accept a paid-trial demonstration as proof of Amateur coverage.
