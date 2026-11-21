# r6 validation and deployment record

15 November 2026. No final-period outcome inspection, new fitting, provider event retrieval, main merge or production change.

- **298 full regression tests passed** on the existing Python 3.14 / PyArrow 24.0.0 runtime. **115 focused tests passed** during integration (102 existing research/auth/odds safeguards + 13 new intelligence tests). Ruff and whitespace checks pass.
- New tests cover exact actual-price EV and paired no-vig arithmetic; zero BETs/stakes; supported half-lines versus unsupported pushes; negative-EV PASS; stale/future/post-cutoff/scenario/unmatched exclusions; coherent latest pairs; combining distinct fresh books without making a median quote; residual sensitivity bounds as a diagnostic only; session TTL/window cap; missing-context handling; frozen aggregate seal/hash requirements; all six workspaces rendering without network; genuine-schema synthetic quote-to-card flow; and HTML escaping.
- Frozen performance data loads only aggregate CSVs from SHA-256-pinned Stage 1B.1 and chained baseline manifests. It does not deserialize research models or read raw forecasts/outcomes. Nine market summaries, season diagnostics and probability-band counts are shown as inspected development evidence, not a fresh final test.
- Synthetic quote-layout Chromium tests at **375, 390, 430 and 1280px**: viewport equals document scroll width, zero Streamlit rendering exceptions. Layout fixtures are synthetic, not coverage or profitability evidence.
- Actual `odds_value_research.py` startup with the real approved release, a synthetic local test password and no API key: password gate unlocks and **all six workspaces** render at **390px** with no horizontal overflow or exceptions. Browser title `NFL Betting Intelligence · r6`. No live provider or quota call was required. Physical iPhone Safari remains an owner acceptance check.
- Source/configuration diff leaves `app.py`, production pricing, release loading, dependency locks, all release/model/data artifacts, workflows, Supabase/ledger/bankroll and frozen research files untouched. Production main at the prepublication check remains `ad6b545e2a0e132d336806aa56a99fbee0e9cd04`. Active baseline remains `stage1a-20261113-py314-arrow24-r2`.
- Working r5 preserved at tag `research-r5-working-20261115` (`938485d`). Implementation developed on `research-intelligence-20261115`; tested code is delivered by fast-forward to the existing `sportsgameodds-free-feasibility` branch / PR #8. No separate app or dashboard is created and no Streamlit settings/secrets are changed.

## Statistical result

**No new predictive-performance improvement or betting profit is claimed.** Stage 1A numerical forecasts and pricing are unchanged. The only historical numbers displayed are existing frozen chronological development experiments. They have repeated-development/selection limitations and no authentic historical bookmaker-price backtest. Authentic realised betting sample: **0**. ROI, CLV, validated win rate and BET safety thresholds remain unavailable. New engine outputs are EXPERIMENTAL WATCH/PASS with zero BETs.

## Hosted acceptance boundary

The owner reported successful genuine retrieval on the existing research app before this update. This implementation preserves its existing auth/adapter/quota path. Final-head GitHub CI, unauthenticated app availability and private owner acceptance are separate checks. A build/health/password screen alone cannot establish live odds retrieval, pricing content or physical Safari behavior. Final delivery reports actual checks and any remaining owner steps; it does not assert authenticated hosted verification without evidence.
