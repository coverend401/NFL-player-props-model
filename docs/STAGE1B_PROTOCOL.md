# Stage 1B experiment protocol and review runbook

## Production isolation

Branch `stage-1b-validation-calibration`. Keep `app.py`, the active release pointer,
root production `data/`, trained production models, Supabase, authentication and
bankroll settings unchanged. No scheduled production task is enabled. The lab
uses the existing exact Python 3.14 / pyarrow 24.0.0 dependency lock.

`stage1b_dashboard.py` is a **standalone proposed dashboard**, not imported by the
production app or automatically deployed. It reads public experimental artifacts,
not Streamlit secrets or the private ledger. Future integration needs approval.

## Frozen time protocol

Protocol file: `stage1b/protocol.json`; seed 41017. No random train/test split.
For each evaluation season Y (2022–2026):

1. Fit point candidates on earlier labels available before season Y−2 starts.
2. Select the point recipe on season Y−2; refit on all labels available before Y−1.
3. Fit distribution parameters on season Y−1 weeks 1–9.
4. Fit calibration on Y−1 weeks 10–14.
5. Select probability method/calibrator by log loss on Y−1 weeks 15–18.
6. Freeze models, distribution and calibration; evaluate season Y. Annual rolling
   origin is intentional. Within-season history updates use only previous games;
   model weights are not silently refitted weekly under an old calibrator.

Every phase additionally requires outcome availability strictly before the next
phase's earliest decision time. Predictions are defined one hour before kickoff.
Feature provenance must be strictly earlier; missing/unverified completion blocks
history. The inherited kickoff+8h availability field is a proxy, not an observed
publication timestamp. Point features are recomputed from observations, not copied
from a historically closing-context row.

Only historical player outcome/opportunity averages/trends, prior participation
share and prior game count enter the benchmark. All eligible panel candidates are
counted; scoring requires positive verified offensive participation and an observed
outcome. A genuine zero is retained; unknown outcome/participation is never filled.
The panel cannot reconstruct players absent from all historical source records or
prove historical sportsbook eligibility. It is not an offered-market population.

## Untouched final period

2025 was already inspected in Stage 1A; it is NOT a new untouched test. 2022–2025
are development OOS; 2026 weeks 1–10 are monitoring and reported separately.
The genuinely prospective final period is **2026 week 11 onward**, conservatively
sealed from **19 November 2026 00:00 GMT**. The first listed week-11 kickoff in the
source schedule is 20 November 01:15 GMT. Future seasons are sealed too.

The runner has no unseal flag. Parquet filters exclude sealed rows before their
outcomes are materialised; preparation and artifact semantic guards repeat the
restriction. There are no final-period performance numbers in this release.
Changing the protocol after seeing final results invalidates the final claim.

`stage1b.prospective.capture` provides an offline capture path using the frozen
2026 fold. It requires reviewed pregame feature vectors and original raw snapshots
whose hashes match, stamps the real clock (no backdating option), only accepts the
registered one-hour pregame window, and stores predictions without outcomes.
No collector is scheduled or deployed. The owner must arrange prospective source,
roster, rule and quote archiving before that period; the retrospective snapshot
alone cannot establish full point-in-time validity. Final scoring/unsealing requires
separate approval and an unchanged model/protocol, after outcomes are available.

## Reproducible execution

In the pinned Python 3.14 environment, from repository root:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m unittest discover -s tests -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m stage1b.runner --id baseline-20261113-v5
python -m stage1b.cli experiments/stage1b/baseline-20261113-v5
streamlit run stage1b_dashboard.py
```

IDs are immutable; choose a new ID for a new experiment, never overwrite results.
The runner starts in temporary research storage, reads the selected release via
its existing guard, verifies runtime pins, freezes source/config/input hashes,
saves all 45 market-season models, and validates output hashes and timing.
No production training script, model file or data pointer is mutated.

Artifacts include row-level forecasts, explicitly hypothetical probability probes,
coverage, point metrics/cohorts, probability scores by season, probability-band
reliability, paired uncertainty intervals, earlier-phase candidate selection and
all-candidate outer diagnostics. Diagnostic outer scores do not choose a winner;
the frozen selection code never reads evaluation labels. Historical timestamps are registered replay decisions, not claims that these
models were deployed then. The archive records the actual experiment build time
and the latest information used; it never fabricates a historical fit time.
Saved models permit
exact-line pricing later if genuine historical quotes are acquired.

A candidate family may regress out of sample despite winning earlier selection.
Do not tune on the final period or silently exclude losing markets/cohorts.

## Genuine historical odds, if obtained later

No authentic quote data is bundled. The initial betting status explicitly has
zero quotes/bets and null realised profit. Synthetic tests are not trading results.

Reviewed quote CSV fields: `quote_id,bookmaker,game_id,player_id,market,side,line,odds,odds_format,
quoted_at,available_at,decision_at,kickoff_at,rule_id,evidence_id`.
`odds_format` must be `decimal`; American prices are not silently interpreted.
Times must be UTC-aware. Lines/prices must exist before the exact forecast decision;
only one-hour decision features are available in this protocol. The default maximum
price age is five minutes; do not assume an earlier price was still executable.

Evidence manifest maps each ID to `classification=authentic_provider_archive`,
`reviewed_by`, `licence_confirmed`, `provider_host`, credential-free `source_url`,
`original_path`, `original_sha256`, reviewed extraction `path`, and `sha256`.
The extraction JSON has `quotes` entries binding economic/identity/timestamp fields
to the original provider response. Each entry also requires a `settlement_rule` archive with `rule_id`, `path`,
`sha256`, timezone-aware `available_at` before the decision, and credential-free
`source_url`. Independent manual verification is required;
a caller-created hash cannot authenticate a historical price.

```bash
python -m stage1b.cli experiments/stage1b/baseline-20261113-v5 \
  --quotes /path/to/reviewed-quotes.csv \
  --evidence-manifest /path/to/evidence.json --evidence-root /path/to/archive \
  --output /path/to/new-research-backtest
```

Unsupported settlement rules or missing action evidence stop scoring. Quarter
lines/exchange commissions/parlays are unsupported. No-snap cases remain unresolved
unless a verified official void is supplied; absence of snaps is never inferred
as a void. Fixed stake = one generic unit, minimum EV 3%, one bet per player-market-
game at earliest eligible decision. This is preregistered research policy, not a
claim of profitability or a change to live bankroll settings.

Push-aware economics: `EV = p_win*(odds-1)-p_loss`; fair decimal odds
`(1-p_push)/p_win`; Kelly uses only the resolved win/loss fraction. Research risk
utility compares model disagreement and zero-default staking; fractional Kelly
(1/8 with 0.5% cap) is illustrative and requires independently validated inputs.
Its disagreement interval is not an individual confidence interval. Fixed stake
is the primary historical comparator. Calibration sample size and subgroup
reliability must be considered; no heuristic 0–100 score is called confidence.

## Stage 1C benchmark

Keep this protocol, input snapshot, model files, forecast row IDs and selected
method decisions unchanged. Compare new opponent/personnel/game-script features
on identical eligible games, quote decisions, settlement rules and proper scores.
Require paired uncertainty estimates and coverage changes, not headline win rates.
Use timestamped pregame snapshots for new features; historical closing data or
retrospective injury labels are inadmissible. The untouched final period remains
sealed until an explicit, documented final evaluation decision.

## Approval and limitations

No Stage 1B merge or deployment is authorised. Review the PR, results and dashboard
in isolation first. Historical forecast scores remain conditional on observable
participation and retrospective stat snapshots; absent publication/roster archives,
this is not a fully authenticated historical deployment simulation. Authentic
bookmaker ROI and final-period results are unavailable, not estimated substitutes.
