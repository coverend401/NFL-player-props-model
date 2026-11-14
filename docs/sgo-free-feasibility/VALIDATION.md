# Validation and readiness

14 November 2026. Synthetic API fixtures are not live coverage evidence.

- Python 3.14 initial full suite: **223 tests passed**, no skips. After adding schema, concurrency, fresh-paper-decision and preview controls, the final focused suite: **46 tests passed** (39 adapter/research tests plus seven existing account-probe tests). Final-head GitHub checks are the authoritative full-suite and frozen-archive replay record.
- Python 3.12 reference checks retain intentional runtime-pinned skips, including the real-bundle preview which requires Python 3.14. The production target remains Python 3.14 / PyArrow 24.0.0; dependencies/locks unchanged.
- Synthetic tests cover seven canonical markets plus QB rushing routing; actual per-book lines instead of consensus; manual normal-CDF/EV arithmetic; both sides; integer/quarter push exclusions; stale/missing/future timestamps; forecast provenance; name/team/game ambiguity; explicit identity maps; T−60; deterministic paper records; disabled archival/settlement.
- Client/store tests cover missing credentials/no HTTP, header-only credentials, no redirects/retries, paid-tier rejection, current/legacy usage schemas, malformed structures, secret echo rejection, errors/no refunds, response-size/object bounds, persisted quota halt, concurrent reservations, restart accounting, early-reset rejection, rate limits, cache expiry/pruning and private mode-0600 storage outside the repository. No genuine odds were collected.
- Streamlit AppTest covers missing credentials and synthetic stacked cards/filter reruns with **no HTTP**. Physical iPhone/viewport testing remains outstanding; no claim of a verified mobile-device session.
- Full committed-candidate integrity/replay and production-app smoke passed on Python 3.14: **nine models, 780 slate rows, 18 Top Picks**, active release `stage1a-20261113-py314-arrow24-r2`. Archived incompatible candidates remain correctly non-selectable; their provenance was not edited.
- Production `app.py`, probabilities, release pointer/bundle, dependencies, authentication, ledger/Supabase, settings and bankroll code are unchanged. No forecast rebuild, new fitting, sealed results access, frozen benchmark alteration, scheduler, paid resource, merge or deployment.
- Legacy updater remains disabled. `main` remains `ad6b545e2a0e132d336806aa56a99fbee0e9cd04` at review.

## Readiness

Ready for code review and preparation of a **manual, private authenticated coverage trial** once the owner supplies the free key, an approved durable free quota store and private-cache acknowledgement. Not approved for deployment/automation. The first trial must verify actual account entitlements/reset fields, NFL/book/seven-market responses, per-book freshness and UK jurisdiction/rules. No UK variant or genuine quote is yet verified. Long-term paper archival, closing-price capture and settlement remain disabled pending separate retention/seal approval. No production UI hook was added because it would invalidate the existing source-hashed release.
