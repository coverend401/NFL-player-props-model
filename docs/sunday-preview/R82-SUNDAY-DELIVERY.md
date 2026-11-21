# r8.2: certified Week 11 research and recovery controls

## Preserved release

The default remains `research-week11-frozen-20261120-r2`: 618 forecast rows,
568 complete rows, 50 TEN–DAL roof scenarios, 12 fixtures and 22 certified
model-only Top Picks. The roof scenarios remain excluded from pricing and
recommendations. No model, prediction, probability calculation, threshold,
eligibility input, release manifest, production file or quota record is changed.

## Football evidence

Recommendation cards now use the certified feature and schedule inputs, filtered
again by the manifest's prediction time and completed-game cutoff. Inclusive
player-state calculations include the latest permitted completed appearance.
They show last-three production and workload, last-five production, historical
opponent team totals and last-three team attempts/carries. Team volume uses the
existing authoritative repeated team totals once per team-game, not sums across
possibly incomplete player box scores. Each individual quote retains its exact
line/probability/EV computation; context changes no ranking or pricing.

Opponent figures are unadjusted expanding historical team averages, not current
season positional weakness ratings. All-position rushing totals are never called
QB allowances. Game-script sentences are conditional football interpretations,
not known future scorelines or quantified forecast adjustments. QB scrambling is
distinguished from designed carries. Routes, injuries and positional coverage
are not invented. The detailed panel records the cutoff and averaging limits.

## Credential and recovery gate

The legacy incident cannot distinguish an oversized response from credential
echo. Therefore live recovery requires owner-confirmed rotation of the provider
key in both Codex and the research app's Streamlit Secrets. Never paste a key
into chat. No key is read out, rotated by tooling or added to the repository.

`GitHubQuotaStore.recover_halt_once` is an explicit operator method, not a button
or automatic startup action. It requires rotation confirmation, the complete
expected ledger and expected SHA, the existing private-repository validation,
verified conditional updates, the manual-review halt and exactly 81 reserved
objects / 11 historical records. It deep-copies state, changes only `halt`, uses
one SHA-conditioned PUT and verifies the full readback. Conflicts, changed state
or unexpected readback stop without a retry/rebase. An uncertain write outcome
requires read-only reconciliation; never blindly repeat it. Close other research
collection sessions during the diagnostic window.

Both guard outcomes now have distinct safe exception codes and retain only
response byte count and boolean size/echo metadata. If both conditions occur,
credential echo takes diagnostic priority. The original 8 MiB threshold, echo
check, authentication, account, free-tier cap, reservations and rate protections
remain enforced. No rejected payload is saved.

After rotation confirmation and successful recovery, the authorised sequence is
at most one metadata discovery and one event-specific diagnostic, no retries or
pagination, maximum three provider HTTP calls and two new reserved objects
including account preflight. Check the existing client call/reservation plan
before each operation; stop rather than exceed the combined bound. No full-slate
collection is authorised by this release. Current provider consumption is unknown
until an authorised account check; local reservations are not a provider balance.

## Cost and deployment

No new dependency, account, service, hosting plan, paid API or scheduled collector.
Incremental infrastructure cost: £0. Existing Amateur allowance remains 2,500
objects per rolling 30 days; the application's conservative lifetime cap and
headroom protections remain unchanged. No claim is made about Codex account
usage balance, which is unavailable here.

Pushing the existing PR #8 research branch updates only its existing research
Streamlit deployment. Main and the Stage 1A production app remain untouched.
Rollback source is commit `66f5533`; its certified release bundle is unchanged.
Hosted authentication still requires the owner; local browser verification is
not evidence of hosted verification.

## Validation on 20 November 2026

- Full Python 3.14 regression: **394 tests passed** (342.700 seconds), including
  all nine model identities/hashes and exact forecast/Top Picks replay.
- Final affected-path checks: **28 tests passed**, including the real authenticated
  entrypoint, all eight workspaces, both response guards and strict recovery.
- Actual complete slate: recorded numerical player evidence on **568/568** rows.
- Real Chromium at **390px**: 11 model-only landing cards, 22 Top 2 cards,
  eight readable navigation options, four multiselect options, minimum measured
  contrast **8.15:1**, no horizontal overflow or stale Week 10 warning.
- Read-only private GitHub check: complete ledger matches preserved baseline;
  81 reserved objects, 11 records, halt active. No live recovery/provider calls.
- Ruff lint/format and whitespace checks passed. Main remains `ad6b545`.
- Hosted authenticated verification remains owner-only; no hosted success claimed.
