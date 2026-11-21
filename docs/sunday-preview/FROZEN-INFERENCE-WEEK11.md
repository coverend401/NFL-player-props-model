# Certified Week 11 frozen-model inference — local candidate

**Integration update:** the owner has approved this same certified snapshot as the research default. See [final integration and quota-review results](WEEK11-FINAL-INTEGRATION.md). Default-selection statements below describe the earlier certification checkpoint. Snapshot/model hashes are unchanged.

Release: **`research-week11-frozen-20261120-r2`**. Type: **`research_frozen_model_inference_v1`**. This passes the new explicit research inference contract, **not** the original coordinated-training release contract. No deployment or default-pointer activation.

## Contract and production isolation

The original `release_utils.py`, `scripts/validate_release.py`, model training/feature/slate scripts, production entrypoint, requirements, active pointer and Week 10 artifacts are unchanged. The parent is still `stage1a-20261113-py314-arrow24-r2`, with manifest SHA-256 `507f5cf07c7613ea9b4c1d0c4ff4c8397f399a150091bfebfb33d46ab3e3ddd2`.

The research validator requires:

- An explicit inference release type/schema and a successful exact-replay certificate.
- The immutable parent release manifest, all nine original model hashes and original model release identity. Each saved training timestamp/cutoff must equal the actual unmodified bundle metadata; training precedes prediction and the completed-history cutoff. The nine models retain their original coordinated training time.
- Identical validated Python minor and dependency pins, including Python 3.14 and PyArrow 24.0.0; original parent source verification remains enabled. New adapter, validator, preparation script and research entrypoint are separately fingerprinted.
- Complete hashed input/output artifacts: feature snapshot, schedule, roster evidence, versioned eligibility document, timestamped QB starters, source provenance, slate and Top Picks.
- Ordered build/prediction/creation times, source retrieval at/before prediction, strict historical availability, and the Week 11 outcome seal.
- Every candidate represented explicitly in the eligibility document. The document must exactly replay from the captured roster evidence and source timestamps. Unresolved/ineligible players cannot enter prediction. No omissions, silent promotion or post-generation row deletion.
- Exact deterministic replay of **every forecast row/value/column** and the original `compute_top_picks(..., side_filter="Over")` output. Required nine-market coverage, unique forecast identities, fixture/team matching and future T−60 eligibility are checked.

The adapter uses the unchanged production forecasting function in a private function namespace with a versioned upstream current-state adapter. It never patches shared module globals. Historical statistics/team records, numeric feature calculations and model weights are unchanged; current identity and eligibility are applied **before** player filtering/prediction. Exact replay uses the same adapter and inputs.

The training validator explicitly rejects this inference manifest, and no inference exception was added to production validation. Production source fingerprints were checked against the original approved parent manifest in the focused tests.

## Actual timestamps and source bounds

All times UTC (also UK time in November):

| Event | Timestamp |
| --- | --- |
| Original training cutoff | 13 Nov 2026 09:15:00 |
| Original training-as-of, all nine models | 13 Nov 2026 17:09:40.909923 |
| Completed-game feature-history cutoff | 19 Nov 2026 00:00:00 |
| Forecast build start | 20 Nov 2026 15:14:11.012000 |
| Prediction | 20 Nov 2026 15:14:13.310653 |
| Release creation | 20 Nov 2026 15:14:28.098348 |

`feature_data_cutoff` bounds completed-game history. Source-information availability is separately bounded by `prediction_at`: the existing filtered snapshots were captured on 20 November before prediction. This is not a claim that their later revisions were known on 19 November or during historical backtesting. Source URLs, raw-file hashes, modification/retrieval times and processed-file hashes are retained in the candidate. No new download was needed for this task.

Feature outcomes are restricted to 2026 Week 10 and earlier. Week 11 schedule rows contain fixture/context metadata, with score outcomes absent. Week 11 roster records are pregame eligibility metadata, not evaluation outcomes. No sealed result was inspected or used for method selection.

## Eligibility and identity

`pregame_eligibility_v1` records player ID, historical/current team, source/hash, evidence/availability/effective timestamps, status, reason and original roster status. Effective time is explicitly **snapshot observation time, not an invented NFL transaction date**. Only unambiguous current-week active-roster evidence with a future fixture is marked eligible. Game-day active status remains unconfirmed.

All **572 candidate player states** were covered: 336 eligible, 70 ineligible and 166 unresolved. These are player states, not projection counts; existing starter, minimum-history and feature requirements still apply afterward.

Nikko Remigio is mapped to **HOU** from the captured roster, while his old KC historical games remain unchanged. HOU's fixture had already kicked off, so his old ARI–KC projections never reach prediction. The four previously unresolved players remain explicitly unresolved and absent from the accepted slate. Current practice-squad exclusions are not permanent: a later documented ACT snapshot can supersede DEV in a new timestamped release; the elevation transition and future-evidence rejection are tested.

Compared with the earlier 736-row draft, **118 old rows were not regenerated**: 32 ineligible (30 practice-squad, 2 past current-club fixture), and 86 unresolved (the previous 12 plus 74 additional rows whose current-week status does not establish active-roster eligibility). No new output keys were added. Thus the former 692 unaffected rows were not assumed publishable. Exclusions occur upstream; no generated rows were manually deleted.

## Certified coverage

- **618 forecast rows / 216 players / all nine markets / 12 fixtures**.
- **568 complete forecasts across 11 fixtures**.
- **50 explicitly labelled roof-scenario rows for TEN–DAL**. These do not enter Top Picks or pricing; an unknown roof was not assumed to be outdoors.
- **22 model-only Top Picks**, generated by the original process. They are not bookmaker-backed selections or validated betting value; its legacy reference is recent form, not an invented bookmaker line.
- The research Top 2 by Game view loads **22 model-only cards** across the 11 complete fixtures. No recommendations are forced for the roof-only fixture.

## Tests and dashboard loading

**15 focused tests passed** in the final focused run (74.006 seconds). Coverage includes actual forecast/Top Picks exact replay; immutable model hash and training-time tampering; missing/altered eligibility; explicit unresolved handling; practice-squad elevation; future/stale evidence; feature cutoff and seal violations; integrity and missing-replay certificate rejection; original-contract isolation; and real authenticated research-entrypoint loading. Synthetic negative fixtures are isolated temporary copies, never selectable candidate releases. No full regression suite or unrelated tests ran.

The actual research entrypoint loaded the certified candidate using its explicit local pointer, displayed current Week 11 research, removed the stale Week 10 warning and rendered Top Picks / Top 2 without a provider call. The test blocked all HTTP requests. No hosted verification or deployment is claimed.

The accepted snapshot includes `selection.json`. Local review can opt in using:

```sh
NFL_RESEARCH_INFERENCE_POINTER=research_inference_releases/research-week11-frozen-20261120-r2/selection.json python -m streamlit run odds_value_research.py
```

Without explicit selection, the research app continues to resolve the preserved Week 10 release. `research_active_inference.json` was **not** created. An invalid requested pointer fails closed rather than silently falling back. Production always uses its original resolver and ignores the research setting.

## Remaining limits and review boundary

Certification of this research candidate succeeded; the prior provenance/replay blocker is resolved under the newly authorised contract. Default selection, full release regression, hosted deployment/verification and bookmaker collection remain pending separate review. TEN–DAL is scenario-only; unresolved eligibility is excluded, and later roster changes/elevations need a new evidence version. No injury/inactive confirmation or Week 11-specific descriptive matchup snapshot was created; incompatible old matchup evidence stays unavailable rather than being attached to new fixtures. Live probability calibration and betting profitability are not certified.

No models were retrained, rewritten or relabelled. No production/main changes, new service/dependency, credentials, SportsGameOdds calls or quota operations. £0 additional infrastructure/operating cost introduced. Codex/provider usage balances were not queried. An early unselected prototype is retained outside the repository under the local scratch checkpoint; only the accepted r2 candidate is included here.
