# Operational readiness — 24 November 2026

## Week 11 settlement is complete with explicit missingness

The authorised Tuesday-noon settlement floor passed. ESPN access was enabled by the owner. Both nflverse finality and ESPN season/week-specific final scores were checked before player outcomes were admitted. Original pregame captures are untouched.

- Certified complete forecasts: **568**, of which **484 scored**, 14 missing box records despite confirmed participation, 26 missing player observations, 44 with no offensive snaps (not proof of inactivity or sportsbook void).
- Enhanced forecasts: **522**, of which **440 scored**, 14 missing-box/confirmed-participation, 26 missing-player-observation, 42 no-offensive-snaps/unscored.
- The original 12 enhanced Top Picks and 20 Top 2 rows are identified in the immutable joined audit. Market-level errors are recorded. No artificial zero outcomes, mixed-unit aggregate MAE, betting hit rate or ROI is reported.
- Evidence: `weekly_learning_state/cycles/week11-operational-20261124-queryfix`, admitted source receipt under `weekly_learning_state/sources/week11-operational-20261124-queryfix`, and `weekly_learning_state/enhanced_settlements/week11-20261124`.
- Fresh nflverse and ESPN schedules agree that PIT–PHI kicked off at 18:00 UK and JAX–NYG at 21:25, unlike the earlier frozen kickoff metadata. The audit explicitly checks original forecast and capture timestamps against these admitted actual kickoffs: both remained before T−60. Historical frozen records were not rewritten.
- These authorised operational Week 11 results are **not inputs** to the threshold-model sprint or frozen research benchmarks. Operational settlement does not unseal the research final period for method selection.

Two narrow source-handling defects were corrected: ESPN's unsupported date-range query was replaced with its season/type/week filter; the source prefilter now handles Arrow large-string season/week fields before materialising player outcomes. It excludes Week 12 outcomes. Strict finality, score, team, timestamp and admission checks remain enforced.

## Week 12 candidate is certified, frozen and unselected

Release: `research_inference_releases/weekly-week12-schemafix-20261124`.

- **846 total rows: 651 complete + 195 explicitly labelled roof scenarios.**
- **16 fixtures**, including **12 with complete forecasts** and four roof-only fixtures: BAL–HOU, NYG–IND, PHI–DAL, WAS–ARI.
- **24 model-only Top Picks and 24 Top 2 rows**, from complete forecasts only. No invented bookmaker value or forced roof selections.
- Eligibility evidence: 461 eligible, 65 unresolved, 52 ineligible source records. Unresolved and ineligible players do not enter accepted forecasts.
- All nine original frozen model hashes verified; no retraining. Original training timestamps preserved. Exact forecast and Top Picks replay passed under `prospective_frozen_model_inference_v2`.
- Immutable predecision captures recorded for the existing weekly learning, selection-performance and game-script workflows.
- Independent ESPN Week 12 metadata matched all 16 fixture/team/kickoff entries. Earliest kickoff is **Thursday 26 November, 01:00 UK**; its T−60 is midnight. This is verified source metadata, not assumed from a conventional weekly schedule. Last kickoff is 1 December 01:15 UK.
- Manifest SHA-256: `4377a209105f79fd038c23e5390fb2cd720281779acf27bffc61e26fe2dc8af5`.
- Readiness, fixture proof and hashes: `weekly_learning_state/readiness/week12-release-readiness-20261124`, `week12-independent-fixtures-20261124`, and the cycle-keyed `week11-operational-20261124-queryfix` readiness record consumed by the existing Weekly Learning workspace.

## Remaining activation requirements

This is **not selected or hosted**. Current research Cloud serving admission remains explicitly bound to the Week 11 release and certifi 2026.11.20; this candidate was certified in the original Python 3.14 / PyArrow 24 / certifi 2026.10.23 generation environment. A separately validated coordinated serving profile/integration and owner approval are required before replacing the current research slate. Preserve runtime checks; do not edit expected package versions by hand. Four roofs and any later material availability changes need timestamped evidence and a new certified candidate before their scenarios can become recommendations.

Production, main, existing certified artifacts, original models, bookmaker credentials and quota records were unchanged. No bookmaker requests, scheduled activation, new services, or paid resources. The forecast data was refreshed once after finality, reused for preparation, and no contender was promoted.
