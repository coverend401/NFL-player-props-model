# Phase 1 validation — not free-tier coverage evidence

- Python 3.14: **190 tests passed**, no skips.
- Python 3.12 reference: **190 tests run**, 11 intentional runtime-pinned archive skips; remaining tests passed.
- Seven new synthetic probe tests passed: missing key/no request, header-only auth, paid/trial rejection, unknown limits, redirect/API/network errors, malformed/echoed-secret responses, and private/non-overwriting report paths.
- Missing-key CLI check exited safely before any request. The prepared probe was **not run with a real key** and retrieved no NFL odds.
- Stage 1A production bundle validation, all-prediction replay and local Streamlit app smoke passed: nine models, 780 slate rows, 18 Top Picks.
- Ruff checks, formatting and Git whitespace checks passed. No new dependencies or runtime changes.
- The active release, production app/pricing/auth/settings, Supabase/ledger, all frozen source/benchmark paths and sealed-period protections are unchanged against `ad6b545`. The legacy updater remains disabled.
- Official pricing/docs/API host connections were blocked by the proxy. These are not actual provider responses. First-party GitHub schema/example evidence and its limits are recorded separately.

The only new executable is the Phase 1 **account-only preflight**, not an odds adapter. No tests of new matching, EV, mobile presentation, genuine NFL coverage or real object consumption can pass because those features are not built and authenticated evidence is unavailable. No subscription, paid/free database resource, collector schedule, deployment or merge was created.

The Phase 1 gate remains unpassed. A future successful account report alone cannot change that status: current free entitlement, UK bookmaker/market evidence, object charging/reset/refresh rules and data-use rights still require verification before feature work.
