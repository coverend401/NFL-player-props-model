# NFL Research Betting Intelligence — r6

This upgrades the **existing** https://nfl-props-research.streamlit.app, entrypoint `odds_value_research.py`, through PR #8's deployment branch `sportsgameodds-free-feasibility`. No new app, main merge, production change, secret change, account, subscription, provider or dependency. Development was isolated on `research-intelligence-20261115`; tested changes are fast-forwarded to the existing deployment branch. Known working checkpoint: tag `research-r5-working-20261115`, commit `938485d`.

## What runs

- **Top Picks:** ranked cards for genuine fresh exact-line quotes, independent Stage 1A projection, actual decimal/fractional price, legacy probability, estimated EV per £1, paired no-vig probability, book count/median, timestamp/expiry, player-specific evidence, risks and WATCH/PASS. The screen deduplicates a player/market/side to its highest current legacy estimated EV quote; it does not invent a median price or treat quotes as independent bets.
- **Player Intelligence:** all nine forecast-market types, including the 214 scenario-only rows (explicitly excluded from recommendations), legacy distribution reference, observed player usage, missing-role information, genuine quote comparisons and uncertainty caveats. No odds are needed to browse forecasts.
- **Game Intelligence:** all 12 frozen Sunday fixture assessments, individualized QB/receiver evidence, blitz/pressure and NGS proxies, measured pace/volume, unweighted leading/trailing scenarios and missing information. No quantified causal adjustment.
- **Market Intelligence:** preserves the working retrieval/diagnostics/benchmark view and adds actual-line probability and price cards. All exact quotes can be inspected; consensus does not become a fictitious offered line or a confidence score.
- **Model Performance:** SHA-256-pinned frozen development aggregate metrics for all nine markets/seasons: MAE, RMSE, bias, naive benchmark, interval coverage/width/score, Brier, log loss, uncertainty and calibration-band samples. Archived Stage 1A-normal-rule methodology comparison is clearly separate from today's exact deployed release. No experiment fitting, model activation or raw outcome loading.
- **Data & Safety:** free-tier controls, retention, disclosure of unavailable evidence, costs, cutoffs, recovery and baseline release identity.

## Recommendation policy

Policy `stage1a-research-watch-only-v1` is deterministic research triage, not a selected profitable betting rule.

1. Existing fixture, unique player/team identity, forecast timestamp/release, complete-forecast, primary-line, paired-price, real authenticated quote and freshness guards run first. Only supported seven canonical categories / nine existing forecast markets are considered.
2. One coherent latest captured Over/Under pair per bookmaker/player/market is used. Distinct fresh books each contribute once to a median. Several private session capture windows can contribute, but their original timestamps and quoted lines remain separate.
3. For supported half-lines, the **unchanged Stage 1A normal-tail method** prices the actual bookmaker line. EV per £1 is `p * decimal_odds - 1`. Quarter/integer-line push cases have no actionable probability/EV and are PASS.
4. Same-book/same-line proportional no-vig probability is `(1 / selected_decimal) / (1 / over_decimal + 1 / under_decimal)`. This removes quoted margin algebraically; it does not establish a true event probability. Underround prices are PASS pending availability review.
5. Positive legacy estimated EV yields **EXPERIMENTAL WATCH**, never BET. Non-positive or unsupported cases yield PASS. There is no tuned minimum-edge/safety threshold because authentic historical-price evidence is absent. Positivity is a watchlist description, not a validated selection threshold.
6. **BET is disabled**: no sufficient independent calibration certificate, genuine odds backtest, confirmed bettor availability or preregistered margin-of-safety policy exists. The UI can and currently does show zero BETs. No arbitrary confidence percentage, stake, Kelly recommendation or accumulator is produced.
7. Ranking uses quality gates then legacy estimated EV. Book count, correlated matchup evidence and probability differences are not added into an invented score. Context does not alter forecasts/probabilities or claim to explain a market gap causally.
8. A projection ±1 residual-scale pricing stress range illustrates assumption sensitivity. It is not a confidence interval, calibrated distribution or uncertainty bound on actual EV. Normal distributions can be inappropriate for discrete/skewed/zero-heavy markets; that limitation is visible.

## Retention, timing and provenance

Existing provider cache reuse is ten minutes, with 24-hour cleanup on access. New UI capture history is private session-only, at most six windows, pruned after 15 minutes. Latest coherent pairs retain their original provider/retrieval timestamps and exact definition. No raw quote exports, permanent odds archives or settlement. Opening a screen makes no provider calls. Only existing manual buttons collect; no polling or scheduled job is introduced.

Provider-updated and retrieved times must be nonfuture and at most 15 minutes old; T−60 is preserved. Each card has explicit expiry and view-generation time. A sleeping/disconnected phone does not refresh itself: rerun/reopen before acting; no idle screen is claimed as a current price source. The backend rejects expired quotes on rerender. Munich's decision cutoff is **13:30 UK on 15 November 2026**; 18:00 fixtures close **17:00 UK**. No late data is represented as pre-cutoff evidence.

The game-script snapshot's observed public-source retrieval times are documented; original historical publication times are not fully established. Routes, confirmed inactive/injury redistribution, actual coverage shells, isolated protection grades, coaching changes and timestamped weather are unavailable here. Missing data is never zero-filled. Season-long/per-game usage plots are not fabricated from last-four-game aggregates.

## Validation status

**Engineering verified:** release integrity, original forecast/model bytes, authentication and private CAS safeguards, parsing/matching, exact-line arithmetic, no-vig, unsupported-push rejection, stale/cutoff rejection and mobile rendering. This does not validate profitability.

**Experimental:** legacy production probability estimates, EV watchlist, normal reference distribution, sensitivity range, descriptive matchup interpretation, archived development method comparisons. The frozen passing-yards development MAE change 73.07→68.14 is previously inspected research evidence, not a new platform improvement or live-model change.

**Unavailable/deferred:** statistically validated BET selections, independent fresh final-test evidence, passing/anytime touchdown probabilities, authentic historical odds returns/CLV, settlement, current injury/route/snap/news/weather feeds and numeric matchup adjustments. Authentic historical betting sample remains **0**; ROI, hit rate and CLV are unavailable. No synthetic price is counted as a realised wager.

The 2026 week-11 onward final period remains sealed. Stage 1B/1B.1 and C0–C2/C1.1/C1.2 Stage 1 research are immutable. Aggregate metrics are only `development_oos`; an unexpected evaluation tier or failed digest stops display. No experimental probabilities are activated. There is no new predictive-performance gain claim: Stage 1A files and numerical pricing are unchanged.

## Existing app update and iPhone acceptance

1. Keep the existing URL, branch, entrypoint, Python 3.14, PyArrow 24.0.0 and Secrets. Do not create another app or merge main. After tested branch publication, Cloud normally updates automatically. Confirm **NFL Betting Intelligence · r6** / **Research intelligence r6**. If it stays on the prior version, **Manage app → menu → Reboot app** on the research app only.
2. Unlock with the existing research password. Top Picks is the landing screen. Open **Load / refresh genuine bookmaker prices**, choose the future fixture/week and existing free bookmakers, then Retrieve once. Missing/unavailable prices result in an honest empty state; Player Intelligence still works.
3. Check actual book/line/price, model probability, EV formula, WATCH/PASS reason, expiry and principal risk. US odds are benchmarks, not verified Northern Ireland bets. No green BET is expected.
4. Expand a candidate's evidence to see player-specific facts separately from hypotheses. Use Workspace to open Player, Game, Market and Model Performance. Confirm all 12 Game assessments and nine performance markets are accessible. Check calibration counts, development disclaimers and sealed-period notice.
5. Confirm existing retrieval and read-only GitHub diagnostics still work. No credential change should be necessary. If a safeguard fails, stop and report only its safe code. Never reset the quota or disable verification.
6. Reopen/rerun after leaving Safari idle. After a T−60 cutoff no current recommendation should remain for that game. Missing/stale data is not substituted.
7. Verify production separately still shows `stage1a-20261113-py314-arrow24-r2` and its original behavior. No changes have been made there by this release.

Owner-authenticated hosted odds/iPhone verification remains separate from local browser tests. An HTTP health response or visible password gate does not prove private data, API retrieval or recommendations work.

## Recovery

The retained tag points to the working r5 app. If r6 fails, report the error; restore only the research code through a reviewed revert of the platform commit on the existing research branch. Do not touch main, repoint production, reset private quota, rotate credentials or alter database tables. Restoring code does not refund reservations or resurrect stale odds. The older app can be inspected from tag `research-r5-working-20261115` without changing deployment.
