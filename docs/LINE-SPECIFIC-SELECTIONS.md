# Line-specific research engines v1

## Operational status

Implementation on research PR #8 only. No model promotion, production change,
SportsGameOdds use, ledger access, or recurring schedule activation. Hosted
completion is **not certified** until authenticated verification succeeds.

The existing November 22 forecast bundle remains unchanged. On November 23 its
pregame admission window has expired. It cannot supply new current selections.
A separately certified upcoming slate and current player/fixture review are
required for prospective use; this change does not manufacture or refresh them.

## Existing app

Top Picks and Top 2 by Game now start with **Quoted propositions**, separate from
**Frozen forecast-only research**. The existing manual comparison and parlay
workspace remain available. Manual and CSV entry use the same matching,
probability and settlement functions. CSV columns:

`game_id,player_id,market,side,line,decimal_odds,bookmaker,quoted_at,settlement_rule,source`

Use UTC-aware ISO timestamps. Quote age is at most 30 minutes, with T−60 as a
harder deadline. v1 admits positive half/noninteger lines, not integer pushes.
`settlement_rule` must equal `offensive_participation_full_refund_push`; the owner
must confirm the actual bookmaker uses this rule and permits private record
retention. No provider odds/payloads are imported or archived automatically.

**Compare** computes using the actual line. **Freeze** rechecks current forecast
integrity, availability exclusions, original probabilities, quote expiry and
T−60, writes a private immutable decision snapshot, then verifies persistence.
A comparison is not a recorded selection until this succeeds. Failures/conflicts
require explicit reload; no silent retries or backdating.

## Ranking and evidence limitations

No new probability method is fitted. Existing supported empirical research laws
supply probabilities; original normal-only and unsupported point upgrades do not
qualify for ranking. The existing probability-support flag, calibration gap at
most 5 percentage points, diagnostic sample at least 100 and observed workload
history are admission checks. Ranking also requires 2025 chronological empirical
probability evidence in the same market, position and 10-point probability band:
at least 100 distinct player-games across eight weeks and band error at most
five percentage points. Repeated illustrative lines are averaged within each
player-game, not counted as independent samples. Extreme probabilities outside
10–90% are excluded from primary rankings pending targeted validation. No 2026
final-period results are opened for these checks. These are conservative **research policy gates**,
not newly proven line-specific confidence intervals or profitability evidence.
The diagnostic sample is a point-forecast sample, not a count of independent
betting decisions. Probability evidence remains retrospective chronological
research, including previously inspected development data. No independent final
holdout or new ranking-performance improvement is claimed.

Primary selections require hit probability at least 50%; weaker propositions are not forced into slots. Hit probability orders eligible propositions; relative prediction width and
workload variability break ties. Prices and EV do not alter that order. A high
hit probability may still have negative EV at the actual price. Each player can
occupy only one primary slot per fixture. Top Picks returns at most 12; Top 2
returns at most two per fixture; alternatives remain in the frozen records.
All selections are WATCH research, never automatic BET recommendations or
injury-cleared assertions. Matchup explanations remain the original traceable
forecast evidence; no narrative bonus changes rankings.

## Durable storage prerequisite — owner action

The existing private quota repository is explicitly forbidden for selections.
The public model repository is also forbidden: private quotes cannot be committed
there. Streamlit temporary files are not durable.

An **owner-approved separate private GitHub repository**, containing no Actions
workflow, is required. No such repository is created automatically. On GitHub's
free plan this uses bounded ordinary repository storage, no hosted compute or
billable infrastructure. A 900 KiB journal cap fails closed without pruning;
archive/retention changes require owner review.

Configure these new secrets in the **research app only**, and the same secrets
for the existing research weekly workflow:

- `NFL_SELECTION_GITHUB_REPOSITORY`: `owner/private-selection-repository`
- `NFL_SELECTION_GITHUB_TOKEN`: fine-grained PAT scoped only to that repository,
  Contents read/write (never paste into chat).

No production or quota token is reused. The client requires the repository to be
private, uses explicit Bearer authentication, refuses redirects and bounds
responses. Writes use Contents API SHA compare-and-swap; conflicts fail without
retry. An initially empty approved repository is bootstrapped on the first
explicit freeze. Each event binds its predecessor by SHA-256; original decision
snapshots are not overwritten. GitHub repository history provides an additional
recovery record, not a claim of tamper-proof hardware storage.

## Automatic weekly reconciliation

The existing research weekly workflow's `auto` mode now has a selection step
following successful operational processing. No new schedule or default-branch
registration is activated. With both private-store secrets configured, it
consumes the latest already-admitted prospective cycle. It does not fetch any
results itself. Manual equivalent:

`python -m selection_learning.cli --cycle weekly_learning_state/cycles/<id>`

The existing settlement floor (Week 11: November 24, 12:00 UK), pregame capture,
finality receipt, source hashes and immutable reconciled-cycle manifest must all
pass before outcomes are opened. Observed zero stats are scored; missing,
zero-snap/uncertain participation and unfinished results remain pending, not zero
or presumed void. Settlement records link the frozen quote and results receipt.
Repeated runs are idempotent. Source amendments never rewrite frozen decisions.

Weekly reports separately score Top Picks, Top 2 and all entered comparisons, with per-slate breakdowns. Private performance metrics are never printed to public Actions logs:
sample/pending counts, hit rate, Brier/log loss, reliability bands and hypothetical
fixed-unit paper returns. Actual ROI remains unavailable. No retrospective
selection reconstruction, past price invention, ranking promotion or claim that
repeated holdout inspection supplies fresh evidence is permitted.

## Parlay safeguards

Existing Parlay Research stays intact. The quoted-ticket expander accepts frozen
current legs and a separately supplied actual combined price. It reports pairwise
same-player/team/game dependencies and Frechet probability bounds conditional on
the supplied marginal probabilities. With no validated joint model, joint point
probability, fair odds and EV remain withheld; multiplying marginal probabilities
is not substituted. The pure scenario helper labels any seasonal independence
calculation as a user-assumption scenario, never a prediction or guarantee.

## Hosted verification (mandatory, still outstanding)

The task proxy currently rejects the research domain with HTTP 403 and no shared
authenticated browser tool is exposed. Local AppTest/browser evidence is not
hosted verification. Do not call this release complete on that evidence.

Once the branch commit has deployed to the existing research app, authenticate
normally; do not share the password. Confirm the deployed branch/head in Manage
app, then check both selection screens and every fixture. With a certified future
slate, enter a genuine quote and freeze it; reload the private journal in a fresh
session and verify the exact line, price, timestamps and original probability.
Run the admitted operational cycle only after its seal opens; verify the private
weekly report and missing-result statuses. Without durable storage/current
forecasts, the correct state is blocked or empty, not fabricated recommendations.
