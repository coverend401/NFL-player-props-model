# r7 — recommendations first, existing research app

Target remains https://nfl-props-research.streamlit.app, `odds_value_research.py`, deployment branch `sportsgameodds-free-feasibility`, PR #8. No new app, credentials, services, subscriptions, accounts, dependency or production/main change. r6.1 is preserved at tag `research-r61-working-20261115` (`fc62f80`).

## Landing experience

Top Picks restores recent permitted captures and immediately displays ranked experimental WATCH cards. Collection controls, quota bounds, diagnostics, coverage details and policy text follow the cards in labelled, collapsed sections. Each card shows player/fixture, exact prop/direction, book/line/price, independent forecast, unchanged legacy probability/EV, classification, ranking reason, observed context, opponent proxy or explicit missingness, principal risks and original update/expiry times. Supporting evidence expands per card.

No fresh eligible prices → model-only cards immediately, with **no inferred book, line, Over/Under direction, odds, probability or EV**. These rank high projected production within each market (ordinal rank relative to that market's population), not betting value or confidence. Different units are not ranked by raw yardage versus receptions. A player appears once on the model-only landing list. An all-PASS priced set is a valid outcome, not grounds to manufacture a WATCH.

## Safe one-action slate capture

Open **Refresh prices — slate-wide collection**. Before the button is pressed, the app displays eligible fixtures/window count and a conservative bound:

- **At most three uncached kickoff windows / 48 reserved objects / six SportsGameOdds HTTP calls per click.** Account checks count toward HTTP slots. Each window retains the existing limit of 16 events and immutable reservation before retrieval. Cache hits reduce actual calls/consumption; the displayed worst case does not assume they will remain fresh.
- Earliest decision deadline first, then windows covering most fixtures, then chronological tie-break. Up to eight days ahead, only active-slate fixtures with complete forecasts, before T−60. Same-kickoff games are fetched together.
- Existing active-Amateur verification, private GitHub atomic conditional writes, proof flag, halt, rate limits, provider usage plus lifetime reservations, 2,000 maximum local cap and safety headroom remain mandatory. No counter reset/refund, GitHub odds storage, paid fallback, new quota authority or bypass.
- Cache reuse can cover additional windows without provider calls. One click can be **partial**: three uncached windows, existing rate/budget, missing provider events/prices or errors can prevent full coverage. Additional clicks use fresh cached windows and may request remaining ones, subject to the same rate/cap guards. No waiting, retries, background polling or automatic pagination.
- Any collection failure stops further new requests, preserves completed captures and reports safe status. Cache storage failures do not refund reservations. Cutoffs are rechecked between windows, not only at click time. Modified attempt limits cannot exceed the displayed bound.
- **Advanced — per-fixture retrieval and diagnostics** preserves the working two-positional-argument collection interface, including warm r5/r6.1 import compatibility. No new keyword is required from that callable.

Coverage reports fixtures with at least one fresh paired eligible price versus eligible fixtures, missing fixtures and reasons, provider continuation flags, original retrieval times and exclusions. It never promises all seven markets or every fixture was retrieved. One cursor is not proof all remaining records exist; no automatic pagination follows it.

## Permitted cache reuse

The existing private SQLite cache on the same free host is reused across browser sessions without a network request. Recovery requires a private mode-600 owner file outside the repository, authenticated Amateur pregame data and original timestamps, with a reuse age below ten minutes. Past-result payloads, started events and unsafe records are rejected. Cached does not mean freshly retrieved.

Only expired **cache rows** are pruned at 24 hours; calls, reservations, controls and durable GitHub quota state are not changed. Session captures retain the existing 15-minute/six-window bound; merged captures keep original times and prefer the latest coherent book pair. Model/quote freshness and T−60 guards run again before ranking. Expired captures are excluded and separately labelled as removed, not displayed as current opportunities. Quote data is never put in the quota repository or production Supabase.

Free-host disk is ephemeral and may be lost on redeployment/restart. There is no promise of permanent odds retention, new database, paid storage or historical archive. With no usable cache, the model-only fallback remains operational. Reopen/rerun an idle phone before acting; there is no hidden provider polling or claim that an idle screen updates itself.

## Top 2 by Game

At most two distinct players per fixture, taking the highest quoted-price experimental WATCH per player. Different books of the same selection do not fill both places. If only one WATCH exists, show one. If fresh prices exist but all are PASS, show no forced pick. Where a fixture has no eligible fresh prices, up to two complete model-only research candidates may appear, explicitly unpriced. Incomplete/scenario-only or closed fixtures do not earn replacement recommendations. Each card includes usage/form evidence where available, opponent context or missingness, model and book comparison where supported, and risks. Neither a second pick nor a matchup effect is invented.

## Parlay Research

Selections come from Top 2 by Game. Same-game combinations require an explicit research toggle; same-game, same-player/related-market and teammate dependencies are warned about. Duplicate or opposing versions of the same prop are blocked. Expired, unsupported or model-only legs cannot be priced.

**No genuine combined bookmaker quote has been supplied by the existing integration.** Even valid single-leg quotes do not establish an available parlay/SGP price. The optional mathematical product of leg decimals is explicitly **NOT an offered parlay quote**; mixed-book products are not placeable as one bookmaker bet. Correlation, bookmaker restrictions, SGP repricing and boosts remain unknown. Actual combined quoted odds, joint model probability and parlay EV stay **unavailable**, for every combination. Marginal model probabilities are never multiplied into a reliable joint probability. No stake or placement is produced. Selection identifiers include the line/price so a changed quote is not silently the original leg.

## Scientific / cost boundaries

No BET certificate, new probability method, safety threshold, confidence score, realised profit, CLV, historical odds, injury redistribution or numeric matchup uplift is invented. Stage 1A numerical forecasts, nine models and probability engine remain unchanged. Frozen research results and the 2026 week-11 onward final period remain protected. No model fitting or outcome settlement is activated.

**Incremental and new recurring paid dependencies: none.** Existing Community Cloud app, existing public GitHub/free standard CI, existing private quota repository, installed open-source libraries and built-in SQLite only. Active free Amateur/2,500 rolling objects and stricter original local cap/headroom checks remain. No new billable feature, licence, account, trial or paid compute resource is enabled. Existing account invoices are outside code visibility; the prior COST-AUDIT.md remains applicable with this cache-reuse enhancement. Repeated tests make no live odds requests.

## Existing-app verification on iPhone

1. Open the same research URL, unlock with the same password, confirm **r7**. If it still shows r6.1 or retains old imports, reboot **only the research app** via Manage app → menu → Reboot app. No branch/secret/runtime change is needed.
2. Top Picks should show fresh cached WATCH cards first, or clearly unpriced model-only candidates. Expand a card's Supporting evidence. Collection/technical controls should be below, collapsed.
3. Open Top 2 by Game. Fewer than two is valid; model-only cards are not bets.
4. Open the collapsed slate collection section. Review the bound, then click **Collect eligible slate — bounded free requests** once. Check Coverage/status for partial/missing fixtures; do not repeatedly click through RATE/BUDGET/HALTED failures.
5. Open Parlay Research. Select two legs and review correlations; same-game research requires the toggle. Confirm actual combined quote, joint probability and EV remain unavailable. No product of individual prices is represented as a bookmaker offer.
6. Production remains separate and unchanged. Hosted acceptance is owner-required if this workspace's proxy still blocks the research domain. Local browser tests do not establish authenticated hosted retrieval.

## Final local validation

- **321 full tests passed** on Python 3.14 / PyArrow 24.0.0. **138 focused tests passed**, including 21 new r7 cases. Tests cover bounded exposure, changed/tampered attempt limits, quota reservation before events, live cutoff rechecks, partial/rate/cache failures, no counter changes from cache reads, cache privacy/TTL, original timestamps, missing fixtures, expiry, model-only empty states, duplicate/rank handling, no forced second pick, parlay dependence and unavailable joint probability/EV, card ordering and the one-click UI path.
- Actual running Streamlit + Chromium synthetic acceptance: cached WATCH cards precede collection panels at **375/390/430/1280px** with matching document/viewport widths and no rendering exceptions. At 390px the full journey passed: open cached recommendations, expand evidence, show two distinct Top 2 players, click bounded slate collection (cache reuse, zero external requests), select parlay legs and display correlation/quote/probability limitations. Synthetic fixtures are not live coverage or profitability evidence.
- Actual `odds_value_research.py`, real approved baseline, configured synthetic credentials and empty cache: model-only cards appear immediately; all **eight workspaces** render at **390px** without horizontal overflow or exceptions. Existing password gate works. The local test harness disables Streamlit usage telemetry to avoid writing to the cloud workspace's read-only home; no production/cloud setting is changed.
- Ruff and whitespace checks passed. No live SportsGameOdds request, quota reset, credential change, new model fitting, benchmark modification or final-outcome access was used for development/testing. Final-head GitHub CI and hosted owner acceptance are separate gates and are reported on PR #8.


### Withdrawn / missing newer prices

A newer requested NFL window supersedes older captures **for the books it refreshed**, including a successful empty, unavailable or one-sided response. Older quotes from another request scope cannot silently reappear as current. Books not refreshed keep their independent fresh captures. This is an in-memory comparison subset: original cache bytes, source hashes, timestamps and quota state are never rewritten. Market Intelligence refreshes the session view before rendering legacy per-fixture data. Two regression cases verify withdrawal suppression and preservation of a different book. Final full suite: **321 passed**; focused suite: **138 passed**.
