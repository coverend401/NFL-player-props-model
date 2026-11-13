# Stage 1B.1 verification record

Research branch: `stage-1b1-validation-improvements`. Scientific source frozen at
`f27f20d3d3aad750f0f6d03d69b21dc720208b71`; immutable experiment
`experiments/stage1b1/improvements-20261113-v1`.

## Completed local checks (2026-11-13)

- Python 3.14.10: **115 tests passed** (98 existing + 17 new).
- Python 3.12 reference: **112 passed, 3 intentionally skipped**. The three archive
  integrity tests require the exact production Python 3.14 archive runtime; this
  is not a production Python-version change.
- New regressions cover future labels versus selection, disjoint phase timing,
  sealed-period exclusion, zero outcomes, count support and signed yards,
  monotone calibration/push partitions, finite Student tail mass, hand-calculated
  conformal ranks/interval scores, conservative point fallback, joint completion
  label validity, portable estimators, raw quote timestamps/hashes, refusal of
  post-kickoff/future quotes, failed/missing provider access, immutable captures,
  secret omission, public-rule URL restrictions, archive tampering and final-period
  rejection even after an attacker recomputes a payload hash.
- Full saved-model replay: **45 bundles, all 55,303 forecasts and all 331,818 paired
  probability probes reproduced**, with numerical tolerance 1e-12. No refitting or
  final-period data used during replay. Row IDs/outcomes and old comparator
  probabilities exactly match the frozen Stage 1B population.
- Frozen Stage 1B validator/semantic checks pass unchanged.
- Stage 1A candidate validation and full app smoke pass: all nine production models,
  **780 slate rows, 18 Top Picks**, every saved forecast replayed.
- Stage 1A fault-injection/rollback rehearsal passes in temporary copies. Missing
  model, future training, incorrect release ID and incorrect prediction are refused;
  rollback restores the verified release and retains a ledger marker. Production
  pointer/data were not switched by rehearsal.
- New-source Ruff F checks, formatting and compile checks pass; git whitespace check
  passes. Requirements and the 69-package production lock are unchanged.

CI runs the full suites on 3.12/3.14, the original release safeguards and Stage 1B
validation, plus full Stage 1B.1 replay on 3.14. Check the PR's final-head status;
local checks are not a substitute for green remote CI.

## Production and main isolation

PR #3 merge: `15a40282f347a76238ee29b8821c3fe8b3aa0223`.
Main's post-merge Actions run **43503248475 passed**. Main was rechecked against
this expected SHA before pushing the new research branch. The updater remains
`disabled_manually`; no conflicting jobs were active during that verification.

The active pointer is still `stage1a-20261113-py314-arrow24-r2`, selected manifest
SHA-256 `507f5cf07c7613ea9b4c1d0c4ff4c8397f399a150091bfebfb33d46ab3e3ddd2`.
The production app, probability/betting/accounting/ledger code, pipelines, release
loader, selected release data/models, requirements/lock, Streamlit settings and
updater workflow are byte-identical to the pre-Stage-1B production commit. There
is no Stage 1B/1B.1 import or UI activation in `app.py`. Stage 1B.1 also leaves the
frozen Stage 1B package, dashboard and baseline archive byte-identical to main.

No Supabase table/configuration, bankroll setting, authentication or production
secret was accessed or changed. No extra dashboard server was hosted. No Stage
1B.1 merge/deployment is authorised or performed. Repository/source and smoke
checks establish unchanged app behaviour; they are not a new authenticated visual
inspection of the password-protected production service.

## Approval boundary and limitations

The final period remains sealed. Previously inspected development/monitoring data
are not a new final test. Results are mixed; see `STAGE1B1_RESULTS.md`, including
season reversals, bias, count interval regressions and worse attempts/completions
ECE despite better proper scores. No profitable betting claim is supported.

The owner confirmed **no odds provider yet**. Capture code is prepared and tested,
but authentic collection is **not operational**. Provider/licence, private credential,
network approval, durable private storage, capture scheduling, identity mapping and
settlement-rule review remain outstanding. Genuine quotes/bets remain zero;
profit and ROI remain unavailable. No production environment changes or paid
requests are needed to review/merge this research-only PR.
