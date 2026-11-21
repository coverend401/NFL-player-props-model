# Week 11 — bounded eligibility reconciliation

**Local review checkpoint only. No partial publication, model changes, selection, deployment or SportsGameOdds calls.**

## The two conflicts: verified cause and current team

Both rows concern **Nikko Remigio**, receiving yards/receptions, incorrectly assigned to the upcoming ARI–KC fixture by the draft. His current team is **HOU**:

- Saved depth-chart evidence lists KC through **11 November**, then HOU from **14–20 November**.
- The additional nflverse roster snapshot, file-modified **20 November 07:04:12 UTC**, retrieved **09:59:13 UTC**, lists `HOU / ACT / Week 11` for the same GSIS ID.
- Refreshed historical observations already contain his **Week 10 HOU record with zero offensive snaps**. The history is not reassigned or erased.
- `scripts/forecast_features.py:243–246` removes zero-offensive-snap rows before choosing the latest state. Consequently, it also carries the **team identity** from his last positive-snap game, at KC (last completed 19 October), instead of the newer HOU identity. The fault is coupling current team identity to performance-history selection, not a KC/HOU abbreviation alias.

HOU's Week 11 fixture against IND kicked off **20 November 01:15 UTC**, before the draft prediction at **09:57:55 UTC**. Neither Remigio row belongs in the remaining upcoming Week 11 slate. This conclusion uses fixture timing, not the sealed game's outcome. The review decision obtains HOU from roster evidence, not a hardcoded player/team exception. It does not transplant the old KC/opponent projection to HOU.

The correct source fix needs dated current identity separate from performance history. The protected production feature/builder files were **not** modified: doing so would affect source-hash integrity and replay of the preserved release. A reviewed correction must be incorporated in an approved replay/publication path, not disguised by editing old game teams.

## The 42 missing confirmations

Inspected only the **14 affected players**. Reused existing depth/identity data; made **one** necessary free roster-file download (567,138 bytes). Only flagged IDs were materialised from that roster; no outcome data was requested.

| Current finding | Players | Forecast rows |
| --- | ---: | ---: |
| Week 11 practice-squad (`DEV`) record: currently not active-roster eligible | 10 | 30 |
| Current eligibility genuinely unresolved | 4 | 12 |
| Confirmed eligible and restored | 0 | 0 |

The 10 practice-squad players and row counts: Sterling Shepard 2; David Moore 2; Marquez Valdes-Scantling 2; Salvon Ahmed 4; Elijah Mitchell 4; Deven Thompkins 2; Zamir White 4; Israel Abanikanda 4; Kendre Miller 4; Charlie Jones 2. The roster also verifies Valdes-Scantling at PIT rather than LAC and Miller at DAL rather than NO. No new-opponent forecasts are fabricated for them.

These are **as-of-snapshot roster exclusions**, not claims of announced Sunday game-day inactivity. Players can be elevated before Sunday; new evidence would require a new decision timestamp.

The unresolved players:

| Player | Rows | Why not certified |
| --- | ---: | --- |
| Marquise Brown | 2 | Roster ACT row belongs to Week 9; saved player registry says CUT. No unambiguous current-week evidence. |
| Najee Harris | 4 | CUT/status evidence is attached to a Week 7 roster row; current-week eligibility timing is not established. |
| Dameon Pierce | 4 | CUT/IR-related evidence is attached to Week 9; current-week eligibility is not established. |
| Jimmy Horn Jr. | 2 | CLE practice-squad evidence is Week 10, while the draft says CAR; no current-week confirmation. |

Older records and file-wide modification times are not silently promoted into a current-week player status. Missing depth membership was never treated as proof of inactivity. No broader transaction/injury investigation followed the publication-contract stop condition.

## Publication contract and scope stop

The existing contract does **not** permit publishing an arbitrarily filtered clean subset:

- `scripts/validate_release.py:105–119` regenerates the slate with the original builder and requires exact frame equality. Dropping reconciled/unresolved rows without an approved input/replay rule violates this check.
- Lines 73–85 additionally require matching model/bundle release IDs and models trained during the coordinated build. The frozen nine-model reuse request cannot be implemented by relabelling models, backdating a build or pretending they were newly trained.
- The research entrypoint still resolves the existing integrity-checked production bundle; there is no already-approved independent research forecast loader/publication contract.

Therefore **no partial-publication policy, altered manifest, bypass or new architecture was introduced**. The local review-only helper records source-derived decisions but does not select or publish forecast rows. The forecast builder's source identity defect remains unintegrated pending the approved contract/source boundary correction.

## Counts, checks and next decision

- Flagged population: **44 rows / 15 players**, unchanged from the blocked run.
- Reconciled to defensible exclusion decisions: **32 rows** (30 current practice-squad + 2 already-started current-club fixture).
- Unresolved: **12 rows / 4 players**. No flagged rows restored as eligible.
- Otherwise unaffected draft: **692 rows across 12 upcoming Week 11 fixtures**. This is candidate coverage, **not certified/published coverage**.
- Accepted/published Week 11 slate: **none**. Top Picks generated: **0**. The research app cannot yet load an accepted Week 11 snapshot; dashboard integration was not bypassed or claimed successful.
- Necessary regeneration to recover the originally unpersisted flags reused the downloaded inputs and existing frozen models. No fitting or data refresh of those inputs occurred.
- Actual-data assertions passed for the 44-row population, absence of duplicate draft forecasts, ordered forecast timestamps, historical availability strictly before **19 November 00:00 UTC**, and no Week 11 outcome rows in features.
- **8 focused tests passed**, including frozen 44-row evidence replay, checksums, missing-versus-inactive handling, stale/future/ambiguous evidence rejection and active-roster-versus-game-day distinction. No full regression suite.

Roster evidence was obtained after the recovered draft's prediction timestamp. Decisions are explicitly dated **20 November 10:02:37 UTC**, after evidence retrieval, not retroactively applied as knowledge available at 09:57. Any accepted rerun must have a new timestamp and approved identity/eligibility replay rules.

Evidence and replayable decisions are under `research_inputs/week11_reconciliation/20261120/`; raw quarantine and the recovered draft remain in `/workspace/scratch/week11-refresh-20261120/reconciliation/`. Source hashes and all relevant timestamps are recorded. No private bookmaker data or credentials are included.

**Stop for review:** an approved frozen-model research publication/replay contract and source identity correction are required before publishing exclusions or generating Top Picks. This is outside the bounded reconciliation approval. Production, main, Week 10 artifacts, model bytes, rollback points, secrets and quota records are unchanged. SportsGameOdds usage: zero; its balance and Codex usage balance were not queried. No paid resources or new services.
