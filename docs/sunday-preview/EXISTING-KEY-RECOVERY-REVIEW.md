# Existing-key recovery review — 20 November 2026

## Decision: retain the halt

The original guard was an exact full-key byte search, not a heuristic. However,
the same exception covered either that match or an HTTP body over 8 MiB. Neither
the rejected body, byte count nor branch-specific flags were retained. The saved
incident evidence therefore proves an unsafe-response rejection, not which
condition occurred. Missing evidence does not prove absence of a credential echo.

The original fixed HTTPS provider destination, header-only credential,
`allow_redirects=False`, generic exception and rejection before JSON parsing or
cache writes substantially limit application-side disclosure. A credential echoed
back over an approved channel would not itself prove third-party compromise.
Those facts nevertheless do not establish the actual rejected content or exclude
upstream logging/intermediary exposure if a secret was present. No original
branch-specific hosted diagnostic or response evidence is available. No separate
provider requests were used to test the same possibly affected key.

Under the owner's existing requirement not to treat an unknown echo as harmless,
there is insufficient evidence to certify same-key recovery. Rotation confirmation
remains mandatory in `recover_halt_once`; this review neither removes that check
nor substitutes a false confirmation. The owner cannot self-rotate and declines
provider assistance: no approved credential-remediation route is currently
available. The integration remains blocked on that specific external dependency,
not on a continuing open-ended investigation. A provider-issued replacement or
reliable original incident evidence establishing a size-only rejection is needed
before a new recovery review. No credential is requested in chat.

## Independent completed engineering

- Existing response guards retain separate size/echo booleans and response-byte
  count only, with distinct codes. Both guards and the 8 MiB threshold remain.
- `EventClient.discover(..., limit=1)` now supports a genuine one-object discovery;
  the ordinary collector default remains 16. Invalid limits fail before HTTP.
- New operator-only `DiagnosticClient` is not connected to automatic UI actions
  or halt recovery. It permits one metadata discovery and one price operation,
  no pagination/retries, at most three actual transport calls and two object
  requests. It never clears or refunds quota.
- Price diagnostics require the event ID and player ID actually returned in the
  permitted discovery, matching home/away teams and kickoff. Missing player
  metadata stops rather than guessing IDs or issuing another discovery.
- Filters use the existing official v2 OpenAPI fields `eventIDs`, `playerID`,
  `oddID`, `bookmakerID`, `limit` and date/status restrictions. Only seven canonical
  full-game over/under definitions are requested for one player, with opposing
  odds enabled and alternate/open/close lines disabled. Long filter URLs fail
  closed rather than silently dropping the player filter. Provider interpretation
  and live coverage remain unverified; unit responses are synthetic.
- One account observation may be reused in this same foreground diagnostic for
  no more than 30 seconds, with an unchanged credential. Halt/proof checks still
  apply. Freshness is checked again immediately before transport, including after
  reservation or pacing delays. Expiry stops without a replacement account call;
  any already-made reservation is retained. Each event keeps the original
  atomic reservation, cap, headroom and account-entitlement validation.
- The existing recovery method still requires the complete expected state and
  SHA, exactly 81 objects / 11 records, verified conditional updates and rotation
  confirmation. It makes one conditional PUT, never rebases/retries on conflict,
  and verifies the complete readback. No real recovery was executed.

## Verification and remaining scope

23 focused tests passed: budgets/filter restrictions, historical reservation
preservation, halt checks, account expiry, slow-reservation expiry, no retry or
pagination, fixture validation, strict recovery conflicts/readback and separate
credential-echo/size guards. Real private-ledger GET-only verification found the
entire preserved baseline unchanged: 81 reserved objects, 11 records, halt active.
Actual provider usage/remaining allowance remains unknown; local reservations are
not a provider balance. No full regression run or live provider request.

No paid resource, new service, credential change, production/main modification,
model retraining, certified Week 11 artifact change or quota write. No full-slate
collection is authorised or attempted. These changes prepare a safe bounded
sequence; they do not claim a working authenticated bookmaker diagnostic.
