# Week 11 — final research integration

## Selected research default

`research_active_inference.json` now selects **`research-week11-frozen-20261120-r2`**. The certified manifest hash is unchanged: `2ef8e0a19da56705e31d3af0f72b1b4dd71bd3a3a5d5a8c8fc4a5016d0e1a021`.

- **618 rows across 12 remaining Week 11 fixtures**.
- **568 complete forecasts across 11 fixtures**.
- **50 TEN–DAL roof-scenario rows**, excluded from Top Picks and bookmaker pricing.
- **22 model-only Top Picks**; Top 2 by Game displays 22 distinct-player research cards across complete fixtures. These are not verified bookmaker value.
- Phase 1 dark navigation and three-sentence football commentary are included. Detailed technical evidence remains expandable.

Production still resolves `active_release.json` and **`stage1a-20261113-py314-arrow24-r2`**. No production defaults, data, models, validation rules, dependencies, authentication, Supabase or bankroll settings changed. The research setting cannot change production's resolver. Week 10 and all previous rollback points remain present.

## Fixture verification

On **20 November, 16:26 UK**, one bounded download of the public nflverse schedule was checked using **fixture columns only**, with no Week 11 outcome columns materialised. All 12 IDs, home/away teams and kickoffs matched the certified snapshot. This was a relevant fixture verification, not an outcome/feature refresh; no certified input was replaced.

There are ten games on UK Sunday 22 November, plus MIN–SF at 01:20 Monday and CIN–WAS at 01:15 Tuesday. Earliest Sunday kickoff is 18:00 UK; its T−60 decision cutoff is 17:00. Already-started IND–HOU is absent from upcoming recommendations. Eligibility, pricing and view-time cutoff guards remain enabled. TEN–DAL is scenario-only until verified roof evidence is incorporated in a newly certified snapshot.

## Phase A and C checks

- **8 focused integration tests passed**, covering research/production default separation, current entrypoint loading and explicit historical Week 10 compatibility fixtures.
- **1 additional focused scenario test passed**, exercising TEN–DAL exclusion from Top Picks and pricing with synthetic quotes only. A final focused safety-text check also passed after replacing the old fixed Munich cutoff with the selected slate’s actual cutoff and identifying inference certification explicitly; no second full suite was run.
- **One complete local regression run: 387 tests passed**, Python 3.14, in 251.370 seconds. It was not restarted or rerun. This includes unchanged model hashes, inference exact replay, Top Picks replay, outcome sealing, roster eligibility and original production guards.
- An execution transport interruption reattached to that same run; no test process was restarted.
- **390px Chromium check passed**: eight readable navigation options, four multiselect options, selected controls, natural-language cards, expandable details, 11 model-only Top Picks starting cards and 22 Top 2 cards; no stale Week 10 warning or horizontal overflow. Lowest measured option contrast **8.15:1**. No provider retrieval was clicked.
- The initial browser driver's five-second section wait expired while Streamlit was visibly still rendering under concurrent regression load, with no exception. Only the browser check was repeated with a longer observation window after the suite finished; no product code or full-suite retry was used.

Historical rendering tests explicitly request their original frozen training release; current-default tests independently assert Week 11. Their retained old-date fixtures are not offered as current forecasts.

## Phase B — halt retained, diagnostic not executed

The private quota ledger was inspected read-only using the existing managed GitHub identity. This is **not** a new claim that the hosted PAT was authenticated. The schema, historical reservation sum, unique reservation identities, persistent halt and existing conditional-update proof passed review. Private before-state and SHA are saved outside this public repository; no quota field was changed.

The old `UNSAFE` response was discarded and its legacy diagnostic conflated response size and credential echo. A smaller request does **not** establish retrospectively which occurred. Therefore the review does not authorise normal collection or automatically clear the halt.

A non-executed plan is saved privately at `/workspace/scratch/week11-quota-review-20261120/single-event-probe-plan.json`:

1. Obtain separate approval for any halt-only recovery/probe. Recheck the original state SHA and every historical record first; use CAS and preserve counters/reservations and safeguards.
2. Require a **verified current Week 11 provider event ID**, e.g. for MIA–BUF. It is currently absent; expired Week 10 IDs are not reused. Discovery calls require their own explicit bounded approval if an ID cannot be supplied.
3. Existing free-Amateur/account-usage preflight, then **one event-ID price request**, `limit=1`, FanDuel/DraftKings/BetMGM, main lines and both sides. Without discovery: maximum **two provider HTTP calls and one new reserved event object**. Failed responses never refund/reset reservations.
4. Keep the six-call rate limit, headroom/cap checks, unchanged 8 MiB/credential-echo guards, no-results and future T−60 matching. Stop/re-halt on failure; no automatic retries or full-slate collection. Keep other collection sessions closed during any separately approved diagnostic window.

**Required recovery decision:** whether to authorise that tightly bounded diagnostic and a single atomic halt-only transition after the fresh-state check, explicitly acknowledging the unresolved legacy size-versus-echo cause. This integration has executed neither. Provider usage/remaining allowance was not queried; a local reservation counter is not the provider's balance.

## Rollback, push and hosted verification

The exact previously deployed research head, `14fcd32`, is preserved as tag **`research-pre-week11-20261120`**. Existing r8/r7 and older rollback points remain. The smallest research-data rollback removes/reverts only `research_active_inference.json`, restoring the preserved Week 10 resolver; it must be visibly treated as stale for current betting. A whole research-code rollback can be prepared from the tag without touching main or production. No database reset or credential change is involved.

This validated integration is approved for a single push to PR #8's existing `sportsgameodds-free-feasibility` branch. Existing public-repository standard CI runs automatically; do not retrigger it unnecessarily. CI status should be read from the final PR head, not inferred from the local run.

The branch push updates the existing research Streamlit app. Authenticated hosted content requires owner verification; local Chromium/AppTest success is not hosted verification. In the existing app, confirm Week 11, no stale Week 10 warning, 11 complete-fixture research coverage and 22 model-only Top 2 cards. Collection must remain halted; do not press retrieve as part of release verification. Reboot **only the research app** through Manage app if it still shows cached older code. No production settings should change.

## Remaining limits and £0 controls

Roster evidence is the captured 20 November snapshot, not Sunday inactive confirmation. Unresolved players are excluded, and later roster/elevation or roof updates require a new evidence version and certification. No bookmaker coverage or live betting value was established. Local model/feature provenance and exact replay are certified; calibration/profitability are not.

No model retraining, paid resource, new account, subscription, dependency, new hosting/database, provider polling or schedule was introduced. The existing model repository is public and uses standard free Linux CI; the legacy updater remains manually disabled. SportsGameOdds calls: **zero**. Quota writes: **zero**. No Codex/provider account balance was verified. Additional infrastructure/operating cost introduced: **£0**.
