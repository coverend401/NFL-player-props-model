# Free account and secure testing

1. Open https://sportsgameodds.com/pricing and choose **Amateur — Free / $0**. Use the official Get API Key/account flow. Verify the account says Amateur, 2,500 objects, 10 requests/minute. Do not choose a paid trial or attach a paid upgrade. If the flow requires a paid plan, stop.
2. In this existing Codex task's cloud environment settings, add an **environment secret** named `SPORTSGAMEODDS_API_KEY`, with the key as its secret value. Save/apply the environment settings. Do not paste it into chat, a terminal command, source code, PR, `.env` committed file or GitHub. Tell Codex only that the secret has been configured.
3. First run the account-only probe with Python 3.14:

   ```sh
   python scripts/probe_sgo_free_account.py --account-only --output /tmp/sgo-private-account.json
   ```

   This makes one header-authenticated account request, discards identifying/billing fields and saves a mode-0600 private report outside the repository. It establishes no prop coverage. Reports should not be committed or posted publicly.
4. For an explicitly approved **manual development trial**, use an already available persistent private volume outside the repository, owned by the development account. Configure `SGO_RESEARCH_STORE` to its SQLite file; `SGO_PERSISTENT_VOLUME_APPROVED=1` asserts it survives process/host restarts and is shared by all collectors for this key. Do not use temporary storage or Streamlit ephemeral storage for this assertion. Set `SGO_PRIVATE_CACHE_TERMS_ACK=1` only after accepting the limited private caching/data-use constraints. Optionally lower `SGO_OBJECT_CAP` (integer 1–2,000); values above 2,000 fail closed. These nonsecret flags are deliberately not enabled by this PR. If a suitable free volume is unavailable, keep collection disabled.
5. Choose a future NFL fixture window, at most eight days wide. Execute manually:

   ```sh
   python scripts/sgo_research_capture.py --starts-after FUTURE_ISO_UTC --starts-before FUTURE_ISO_UTC --books williamhill,unibet
   ```

   Replace the placeholders with future timezone-aware timestamps. No past/live games, auto-pagination, retries or scheduled jobs. One batch reserves 16 objects before requesting events. The console prints sanitised coverage counts, not quotes/identifiers or credentials; limited pregame quote metadata stays privately cached. Account schema without an unambiguous Amateur tier/monthly reset fails closed. Contact provider support yourself if entitlement metadata is missing; do not infer it from signup text.
6. Review which of the seven markets actually return both sides at the same line. Independently verify the precise sportsbook jurisdiction, UK account accessibility, provider timestamps, available prices and settlement rules against the bookmaker's authorised UK site. Brand names alone are insufficient. There is no authenticated response evidence yet.
7. Local interface preview only:

   ```sh
   streamlit run odds_value_research.py
   ```

   This uses the existing integrity-validated Stage 1A slate. The production `app.py` is deliberately unchanged; do not switch the production Streamlit entry point. Missing credentials/configuration give a safe message. HTTP occurs only on the manual Retrieve button, never automatically on reruns. Stacked cards suit narrow screens; physical iPhone verification is outstanding. The preview is not hosted and must not be exposed without separate authentication/hosting approval.

## Limitations and stop conditions

401/403/429, conflicting account schemas, non-Amateur tier, exhausted budget and unsafe payloads stop collection. A persisted authentication/quota halt requires manual investigation; do not delete counters/retry to evade it. Provider changes, stale/missing timestamps, ambiguous identities and unmatched forecasts remain excluded. Existing approved projections are never regenerated here.

UK variant/rule evidence defaults to absent, so no selection becomes eligible merely because a quote looks attractive. `comparisons` accepts explicitly reviewed `book_evidence` and player-ID mappings for subsequent controlled tests; this PR's UI supplies neither and makes no UK verification claim. Both opposite sides, same line, mainline, fresh timestamps, approved forecast provenance and pre-T−60 timing are required. Integer/quarter lines have no EV, pending validated push treatment. Displayed half-line EV is a diagnostic under the unchanged Stage 1A normal-CDF method, not a profitability claim.

There is no Supabase integration, bankroll posting, settlement, paid fallback, scheduler or database migration. Paper decision payloads are in-memory preparation only. Archive writes and settlement raise explicit errors. Before any archival/closing-price/outcome pipeline: approve licensing/retention, seal policy, free durable storage, UK rules and collection scope separately. On account expiry/termination remove private quote caches per terms; do not commit raw provider data.
