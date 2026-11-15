# Separate free research deployment — 15 November 2026

Approved scope: US prices are market research benchmarks, not UK betting availability. No Stage 1A adjustment, production deployment or PR merge. This supersedes the former UK-coverage hosting gate. Primary scalar quotes are recognised when explicitly flagged primary or returned under the documented `includeAltLines=false` request; an explicit alternate flag is never overridden. Raw flag, request scope, exact odd ID, line and timestamps remain available. Medians require matched complete forecasts, paired same-line sides, one primary line per book, fresh timestamps and T−60 eligibility. A book is never counted twice for two sides. A single book is labelled accordingly. The 20% gap flag is only a descriptive review screen, not a fitted threshold or edge.

## Browser steps

1. Open https://share.streamlit.io and sign in with your existing GitHub connection. Click **Create app**, then the option to deploy from GitHub. Create a **new** free app; do not edit the production app.
2. Repository: `coverend401/NFL-player-props-model`. Branch: `sportsgameodds-free-feasibility`. Main file: `odds_value_research.py`. Choose a new research app URL.
3. Open **Advanced settings**. Select **Python 3.14**. Keep the repository dependency pins, including **PyArrow 24.0.0**. Do not select an upgrade or paid resource.
4. In the new app's **Secrets** field, enter the following privately, replacing the placeholders. Do not paste credentials in chat, logs or GitHub. The token must be limited to the private quota repository, Metadata read and Contents read/write. The quota repository is already initialised and verified: do not reset or reinitialise its counter.

```toml
RESEARCH_PREVIEW_PASSWORD = "NEW-SEPARATE-LONG-PASSWORD"
SPORTSGAMEODDS_API_KEY = "YOUR-FREE-AMATEUR-KEY"
SGO_QUOTA_REPOSITORY = "coverend401/nfl-props-research-quota"
SGO_GITHUB_QUOTA_TOKEN = "YOUR-PRIVATE-QUOTA-REPOSITORY-TOKEN"
SGO_PRIVATE_CACHE_TERMS_ACK = "1"
SGO_OBJECT_CAP = "2000"
```

5. Save settings and click **Deploy** for this new app only. No Supabase secrets or production password are required. App content is locked by its separate password before forecasts load. For a public-code repository, the platform page/URL itself may remain publicly discoverable; do not place secrets there. Optionally use Cloud's private sharing controls if available on your free account.
6. Wait for startup. If an integrity/dependency error appears, stop and report the error without secrets. Do not change pins or disable checks. No URL has been created by Codex; use the URL Cloud assigns to your new app.

## iPhone acceptance checks

1. Open the new HTTPS research URL in Safari and enter the separate research password.
2. Open **Market Intelligence**. Select week 10, a future fixture, and FanDuel/DraftKings/BetMGM. Tap **Retrieve selected fixture's market lines**. Only this button calls the provider. Games sharing a kickoff are fetched together; no automatic pagination or polling.
3. Check independent Stage 1A projection, each book's main line, median, signed/absolute/percentage gap, book count, exact side definitions, prices and update timestamps. Two sides count as one contributing book. Missing/stale/scenario-only comparisons do not enter medians. Changing book filters recomputes the median. At capture the Munich test yielded 26 matched markets: 18 three-book and 8 two-book. Availability can change.
4. Open **Investigate disagreement**, then **Game-Script Intelligence** for the same fixture. Compare observed QB/usage evidence with conditional interpretations. Nothing changes forecasts, probabilities or bankroll. The preview does not label market gaps as betting value.
5. Munich's cutoff is **13:30 UK** (14:30 kickoff). Main 18:00 games close **17:00 UK**. Freshness is at most 15 minutes; the provider refresh/cache is ten minutes. Post-cutoff/stale data are not accepted into current benchmarks. Do not portray later observations as earlier evidence.
6. Confirm the production URL still shows `stage1a-20261113-py314-arrow24-r2`. Send only the new research URL and any non-sensitive error message if help is needed. Physical iPhone Safari/authenticated hosting acceptance remains an owner check.

## Free allowance and limitations

Actual post-probe provider usage: **15 / 2,500**, remaining **2,485**; conservative lifetime reservations **17 / 2,000**. No automatic reset. Every uncached fetch reserves 16 objects even when fewer events return; failed/empty requests are not refunded. A full 12-fixture pass via the fixture selector costs up to 192 reserved objects (actual often far fewer); ten such uncached passes reserve 1,920. Grouped kickoff windows and 10-minute cache hits reduce this, but do not continuously refresh. Provider usage plus reservations and safety headroom are checked before each fetch. Six HTTP calls/minute locally, including account checks. The counter is intentionally conservative and may stop well before the provider limit. No scheduled collector, paid resource, archive, settlement or live ledger integration.

Prices/response bodies stay private outside GitHub with short-lived caching; no bulk exports. FanDuel/DraftKings/BetMGM coverage was authenticated for the early fixture, not guaranteed for all 12 games. Frozen descriptive game-script evidence covers all 12. All nine production markets and frozen research benchmarks remain unchanged.
