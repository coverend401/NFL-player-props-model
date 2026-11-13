# Prospective bookmaker evidence: prepared, not activated

The owner confirmed that no odds provider is selected. No licensed research odds
credential or purchased archive is configured in this workspace. No genuine quote has been collected. No collection scheduler, paid
request, database integration, production change or public quote archive has been
deployed. Provider choice/licence, approved network domain and a private durable
archive are operational prerequisites, not assumed completed work.

`python -m stage1b1.odds_capture --help` provides a manual research collector for
The Odds API's event odds endpoint and public settlement-rule pages. The official
[event sample](https://github.com/the-odds-api/samples-python/blob/master/event_odds.py)
was retrieved: event-specific markets, regions, ISO timestamps and decimal prices
are supported. The full vendor guide is network-blocked here; market entitlement,
coverage, account quota and commercial terms need owner/provider confirmation.
A raw collector can be tested without asserting those commercial facts.

## Activation requirements (separate from merging this research PR)

1. Select a licensed provider and confirm NFL player-market/region/book coverage,
   permissible retention, account quota, clock freshness and price availability.
2. Configure its key privately as `RESEARCH_ODDS_API_KEY` in a research environment;
   do not paste credentials into chat, commit them, print query URLs or enable HTTP
   debug logging. Approve `api.the-odds-api.com` in network policy if using this
   provider. No production Streamlit/Supabase secrets are required or altered.
3. Choose private durable append-only storage outside the public repository. Use
   unique capture IDs. Set a capture schedule only after approval and cost review;
   none is supplied/enabled as a GitHub workflow in this PR. First obtain the vendor
   NFL event IDs from its authenticated event listing; do not infer IDs from names.
4. For each pregame event, invoke the manual command, for example:

   ```sh
   python -m stage1b1.odds_capture --event-id VENDOR_EVENT_ID \
     --regions us,uk --output /PRIVATE_ARCHIVE/UNIQUE_CAPTURE_ID
   ```

   The seven vendor market keys cover the nine research markets, but QB/RB routing,
   event/player identity and crosswalk provenance still require review. The collector
   saves exact response bytes plus actual UTC observed/request times, event kickoff,
   requested markets/region, source URL without credential/query, SHA-256 and safe
   HTTP Date/ETag. Provider market last-update times remain in the original bytes.
   Network/HTTP errors, redirects, missing quotes, future quote times, post-kickoff
   events and invalid prices fail closed. No historical observation time can be set.
   Quoted price visibility does not prove an executable stake/limit.
5. Archive bookmaker-specific action/void/push/overtime rules prospectively:

   ```sh
   python -m stage1b1.odds_capture --rules-url https://APPROVED_BOOK/rules \
     --approved-rule-host APPROVED_BOOK --output /PRIVATE_ARCHIVE/UNIQUE_RULE_ID
   ```

   Review source/legal access, rule identity, jurisdiction, effective date and
   unsupported settlement clauses. Capture time is **not** inferred effective time.
   No redirects, login bypass or credential-bearing URLs are allowed.
6. Review licence, raw payload extraction, event/player IDs, rule scope and
   settlement evidence. The archive is explicitly `backtest_ready=false`. Convert
   to the existing `stage1b.backtest` provenance schema only after review; do not
   infer void from missing snaps, assume current rules applied historically, or
   manufacture unavailable quote sides/outcomes. Unsupported rules remain blocked.
7. Record the contemporaneous frozen model version/information cutoff and evaluate
   exact offered lines at a predeclared decision time. Prefer fixed-unit paper
   accounting first; log quote staleness, missing coverage and rejected decisions.
   Do not choose retrospectively optimal prices or apply today's models to the past.
   Existing replay protections for margin, pushes, voids, concurrent stakes and
   settlement availability remain unchanged. No realised results are reported until
   all evidence is authentic, complete and reviewed.

Synthetic response fixtures in automated tests verify mechanics only. They are
never placed in scientific outputs or counted as genuine bookmaker observations.
