# Week 11 refresh — stopped at current-team eligibility gate

Status: **blocked, local investigation only; no valid forecast snapshot selected or published**.

## Minimum safe generation method identified

Reuse the nine immutable models in `stage1a-20261113-py314-arrow24-r2`. Each has Stage 1A feature timing, training cutoff `2026-11-13T09:15:00Z` and training-as-of `2026-11-13T17:09:40.909923Z`; nothing in the model timing check requires retraining for this refresh. No model was fitted, rewritten or copied with fabricated training provenance.

Use the existing `build_player_features`, `build_slate` and `compute_top_picks` functions in an isolated working directory. Preserve pre-2026 raw history from the validated bundle; refresh only current-season player/team statistics, snaps, expected opportunities, passing NGS, player identity and depth charts. Recompute inclusive forecast inputs using the original feature functions and supply freshly observed fixture context and QB1 timestamps. `prepare_release.py` was deliberately **not** run: it would execute a full test suite and retrain all nine models, and its single-build provenance contract cannot be repurposed by pretending old models were newly trained.

A research-only snapshot tied to the unchanged base-model hashes would be needed for dashboard consumption without changing the production pointer. No loader/pointer change was implemented after the eligibility gate failed.

## Source evidence and cutoffs

Eight bounded, single-attempt downloads succeeded from the same public GitHub release URLs used by the installed nflreadpy loaders. No SportsGameOdds request, account probe or quota-store operation occurred.

| Source | Last-Modified UTC | Retrieval UTC on 20 November |
| --- | --- | --- |
| 2026 player statistics | 20 Nov 05:35:11 | 08:52:10 |
| Schedule | 20 Nov 07:36:22 | 08:53:31 |
| 2026 team statistics | 20 Nov 05:35:14 | 08:53:32 |
| 2026 snaps | 17 Nov 12:01:31 | 08:53:32 |
| Player ID mapping | 18 Nov 17:12:35 | 08:53:33 |
| 2026 expected opportunities | 17 Nov 14:54:44 | 08:53:34 |
| Passing NGS | 20 Nov 07:17:43 | 08:53:35 |
| 2026 depth charts | 20 Nov 07:02:02 | 08:53:35 |

Last-Modified is file provenance, not proof of the original publication time of every observation. Outcome tables were read with Parquet predicate pushdown for **2026 weeks 1–10 only**. Week 11 schedule reads selected fixture/context columns, excluding score/outcome columns. Week 11-and-later outcomes remain sealed; downloaded originals stayed quarantined outside the repository.

The player-stat availability gate read season/week metadata only: Week 10 has 982 player rows. Corresponding metadata checks found 28 team rows, 1,311 snap rows, 299 expected-opportunity rows and 29 passing-NGS rows for Week 10. These are source rows, not confirmed eligible-player totals.

The draft used an explicit completed-game cutoff of **19 November 2026, 00:00 UTC**, before Week 11 began, and a live generation timestamp on 20 November after all source retrievals. This includes available Week 10 history while preventing use of the sealed Thursday Week 11 outcome. The rejected draft's exact prediction timestamp was not persisted; no approved prediction timestamp or current-week provenance is claimed.

## Failed gate — stop condition

The original pipeline produced **736 draft player/market rows**, all labelled Week 11: 680 `complete` and 56 `roof_scenarios_only`. “Complete” here is only the existing numeric-feature/roof status, **not** successful current-team or active-player verification.

Comparing draft player teams with unique team membership in the latest at-or-before-generation depth snapshot found:

- **2 draft rows with conflicting current-team identifiers.** This has not been resolved into a trade, alias difference or stale membership record. Publishing without resolving it could associate a player with the wrong fixture/opponent.
- **42 draft rows without confirmed team membership in that snapshot.** Missing depth evidence does not mean inactive, and was not converted into an inactive flag or zero forecast.
- Source processing also reported 20 unmapped offensive-snap records and dropped 10 source rows without a player ID. Neither was fabricated or silently repaired.

Generation raised `ValueError: Current depth team mismatch; trustworthy current eligibility unresolved` and stopped before saving slate/Top Picks or creating a research manifest. Per the owner's hard-stop instruction, no fallback filtering, reassignment, model retraining, broader roster investigation or further source request was attempted.

**Accepted/published forecasts: 0. Accepted fixture coverage: not established. Top Picks generated: 0.** The 736 rows are rejected in-memory draft output, not a deliverable slate. Their fixture count was not persisted before the stop. The research dashboard continues to use the preserved Week 10 bundle and stale-slate warning; it cannot yet load a validated Week 11 snapshot.

## Checks performed and next review

- Read all nine model metadata records and verified their cutoffs precede the proposed current cutoff; models loaded successfully in Python 3.14.
- Checked availability and Week 10 metadata coverage before generation.
- Exercised the actual existing feature and forecast functions against bounded current sources, with historical cutoff and context-time guards enabled; frozen-model prediction ran without fitting. Accepted coverage per market was not certified after the failed gate.
- **Current-team eligibility validation failed.** No successful current-week integration or forecast release test is claimed.
- No unit/full-regression reruns or dashboard deployment followed the stop condition.

Local reproduction scripts, source URL/hash/timestamp reports and the failure log are saved at `/workspace/scratch/week11-refresh-20261120/`. The raw source quarantine remains `/tmp/nfl-week11-refresh/`; it is not an approved input archive and must not be loaded without the same week/column bounds.

Required next decision: review and authorise a bounded current-team/roster reconciliation before rerunning generation. Any accepted correction must preserve historical team/opponent identities, distinguish missing roster evidence from inactivity and avoid assigning a new team's opponent to an old-team forecast. There is no evidence here that retraining is needed.

Production, main, models, active release pointer, rollback tags, authentication, Supabase, bookmaker code, credentials and historical quota records are unchanged. No deployment, push, SportsGameOdds usage or paid resource. Codex/account usage balances were not queried or verified.
