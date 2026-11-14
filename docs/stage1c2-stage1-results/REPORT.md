# Stage 1C.2 Stage 1 — data quality and feasibility findings

**Recommendation: NO-GO for Stage 2 fitting intended to establish genuinely feasible historical pregame allocation.** Opportunity labels and missing-box histories are substantially auditable; the examined sources do not establish complete historically versioned teammate/inactive states at T−60. Stage 2 remains unauthorised. No research model has been fitted, probability method changed, forecast activated or production file modified.

## Discrepancies: 12 supported internal reconciliations; five unresolved

The new ledger restores two counted events incorrectly excluded by the generic no_play classification: HOU 2024 week 15, play 2274 (Dare Ogunbowale: one carry/35 rushing yards after a replay reversal); PIT 2025 week 2, play 3686 (Aaron Rodgers: an incomplete grounding pass, one attempt/zero passing yards). These are narrowly allowlisted with input flags, actor IDs and exact description fragments; other no-plays remain excluded.

Ten other team-games receive missing intermediate-lateral yard credits. No carry, target or reception is added for a lateral. Multiple Saubert segments are aggregated (+17), negative credits remain negative, and existing final-player/fumble adjustments are preserved. Every accepted change is supported by an explicit play-description credit and reconciles exactly to the original player and team counters. These are research event-ledger corrections, not rewritten official benchmark labels. Shared upstream descriptions/counters provide internal corroboration, not independent certification. Public ESPN API corroboration was blocked by the environment proxy at site.api.espn.com when attempted; no independent corroboration is claimed.

| game_id | team | decision |
| --- | --- | --- |
| 2020_16_CIN_HOU | HOU | unresolved_no_patch |
| 2021_01_CLE_KC | CLE | supported_internal_repair |
| 2021_09_HOU_MIA | HOU | supported_internal_repair |
| 2021_10_DET_PIT | DET | supported_internal_repair |
| 2022_03_PIT_CLE | PIT | supported_internal_repair |
| 2022_06_JAX_IND | JAX | unresolved_no_patch |
| 2022_18_NYJ_MIA | NYJ | supported_internal_repair |
| 2023_09_TB_HOU | TB | supported_internal_repair |
| 2023_16_BUF_LAC | LAC | unresolved_no_patch |
| 2024_03_SF_LA | SF | supported_internal_repair |
| 2024_04_JAX_HOU | JAX | unresolved_no_patch |
| 2024_05_DAL_PIT | PIT | unresolved_no_patch |
| 2024_09_LAC_CLE | LAC | supported_internal_repair |
| 2024_15_MIA_HOU | HOU | supported_internal_repair |
| 2025_02_SEA_PIT | PIT | supported_internal_repair |
| 2025_15_CLE_CHI | CHI | supported_internal_repair |
| 2025_18_IND_HOU | IND | supported_internal_repair |

Unresolved cases are retained without a residual allocation:

- **2020_16_CIN_HOU / HOU:** Description gives Coutee -9, Watson -4, Cooks +20 and Scharping +7; frozen player-box discrepancies instead identify Cooks +7 and Scharping +7. Team balance alone cannot certify individual ownership. No patch.
- **2022_06_JAX_IND / JAX:** Multiple laterals plus own-team fumble recovery: description includes Lawrence -4, Etienne +12 and subsequent Kirk -6, whereas box-credit mismatch isolates Jones -11. Need authoritative final credit ownership; no partial residual patch.
- **2023_16_BUF_LAC / LAC:** Multi-lateral and illegal-forward-pass enforcement. Description includes Stick -5 and Erickson +10; structured/box credits do not reproduce those individual amounts. Need final official credit/rule evidence; no patch.
- **2024_04_JAX_HOU / JAX:** Multi-lateral/fumble recovery: description includes Lawrence -4, while the last structured credit includes a fumble adjustment and the box mismatch isolates Davis -7. Cannot reconstruct full attribution from totals alone.
- **2024_05_DAL_PIT / PIT:** Description gives Frazier -5 and Fields +3; frozen box mismatch instead puts net -2 on Frazier. Cannot assign a net residual to a player without authoritative credit evidence.

The complete field-level before/after register and accepted source fragments are committed in the immutable audit bundle. Five unresolved games affect receiving-yard attribution, not an excuse to invent target counts or to alter frozen evaluation outcomes.

Positional category completeness (out of 4,016 team-games; includes production as well as opportunities):

| kind | original_complete | stage1c1_complete | stage1c2_stage1_complete |
| --- | --- | --- | --- |
| pass | 4,016.0000 | 4,016.0000 | 4,016.0000 |
| rec_RB | 2,756.0000 | 4,012.0000 | 4,015.0000 |
| rec_TE | 1,439.0000 | 4,008.0000 | 4,013.0000 |
| rec_WR | 2,008.0000 | 4,010.0000 | 4,014.0000 |
| rush_QB | 3,883.0000 | 4,016.0000 | 4,016.0000 |
| rush_RB | 2,756.0000 | 4,015.0000 | 4,016.0000 |

## Missing boxes and genuine zero opportunities

| position | field | classification | n |
| --- | --- | --- | --- |
| QB | attempts | ledger_confirmed_zero | 106.0000 |
| QB | carries | ledger_confirmed_zero | 106.0000 |
| QB | targets | ledger_confirmed_zero | 106.0000 |
| RB | attempts | ledger_confirmed_zero | 475.0000 |
| RB | carries | ledger_confirmed_zero | 475.0000 |
| RB | targets | ledger_confirmed_zero | 475.0000 |
| TE | attempts | ledger_confirmed_zero | 3,028.0000 |
| TE | carries | ledger_confirmed_zero | 3,028.0000 |
| TE | targets | ledger_confirmed_zero | 3,028.0000 |
| WR | attempts | ledger_confirmed_zero | 2,092.0000 |
| WR | carries | ledger_confirmed_zero | 2,092.0000 |
| WR | targets | ledger_confirmed_zero | 2,092.0000 |

These represent 5,701 distinct offensive-participant missing-box player-games: 106 QB, 475 RB, 3,028 TE and 2,092 WR. The count ledgers support zero attempts, carries and targets for each of these records after the inclusion repairs. There are no recovered positive opportunities in this missing-box cohort. Three count-field overlay rows per player-game are not three independent observations. This is a source-backed count-history overlay only: no production zeros or new evaluation targets were manufactured, and zero opportunities do not rule out exceptional lateral production.

Full position/season classification and original observations remain separate. The source snapshot includes 185,912 player-games; the study preserves the existing 55,303 player-market evaluation rows and every frozen label. The overlay exposes a +36h retrospective availability proxy separately from a verified availability field, which remains missing. It cannot masquerade as an archived historical predecision source.

## Participation and identity coverage

| season | snap_player_games | unresolved_ids | conflicting_ids | mapped_absent_from_features |
| --- | --- | --- | --- | --- |
| 2,019.0000 | 22,884.0000 | 30.0000 | 0.0000 | 2.0000 |
| 2,020.0000 | 23,790.0000 | 21.0000 | 0.0000 | 0.0000 |
| 2,021.0000 | 25,271.0000 | 34.0000 | 0.0000 | 1.0000 |
| 2,022.0000 | 25,168.0000 | 8.0000 | 0.0000 | 0.0000 |
| 2,023.0000 | 25,329.0000 | 13.0000 | 0.0000 | 0.0000 |
| 2,024.0000 | 25,398.0000 | 39.0000 | 0.0000 | 0.0000 |
| 2,025.0000 | 25,396.0000 | 52.0000 | 0.0000 | 0.0000 |
| 2,026.0000 | 12,785.0000 | 28.0000 | 7.0000 | 0.0000 |

Across 186,021 snap player-games, 225 IDs remain unresolved, including 7 conflicting weekly-roster/static-crosswalk links. Same-week PFR links alone match only 125,874 rows; a permanent-ID-only crosswalk recovers most others. Its current team, position and status columns are deliberately not read. Later-discovered ID evidence is labelled retrospective; it does not establish historical roster membership.

| position | season | n |
| --- | --- | --- |
| RB | 2,025.0000 | 7.0000 |
| TE | 2,020.0000 | 8.0000 |
| TE | 2,023.0000 | 13.0000 |
| TE | 2,024.0000 | 14.0000 |
| WR | 2,019.0000 | 13.0000 |
| WR | 2,020.0000 | 1.0000 |
| WR | 2,021.0000 | 15.0000 |
| WR | 2,022.0000 | 1.0000 |
| WR | 2,024.0000 | 4.0000 |
| WR | 2,025.0000 | 10.0000 |
| WR | 2,026.0000 | 9.0000 |

No additional WR/TE/RB/QB game is confirmed as absent from the frozen features among unambiguously ID-matched snap records. Unmapped skill rows remain unknown, so this is not proof that coverage is complete. Three other-position rows are candidate identity discrepancies requiring review, not added zero histories; source position/identity inconsistencies prevent automatic acceptance. See additional_identity_review.csv. Special-teams-only games are audited but do not automatically determine sportsbook participation/void rules.

## Membership, statuses and publication timing

| season | team_games | nonempty_rosters | offense_participants | matched | non_ACT_transaction_codes | retrospective_INA | injury_publisher_date_before_cutoff | verified_universes | participant_match_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2,019.0000 | 512.0000 | 512.0000 | 9,283.0000 | 9,283.0000 | 0.0000 | 2,813.0000 | 5,197.0000 | 0.0000 | 100.0000 |
| 2,020.0000 | 512.0000 | 512.0000 | 9,592.0000 | 9,592.0000 | 3.0000 | 3,035.0000 | 5,401.0000 | 0.0000 | 100.0000 |
| 2,021.0000 | 544.0000 | 544.0000 | 10,073.0000 | 10,073.0000 | 0.0000 | 3,154.0000 | 5,345.0000 | 0.0000 | 100.0000 |
| 2,022.0000 | 542.0000 | 542.0000 | 9,984.0000 | 9,984.0000 | 0.0000 | 3,406.0000 | 5,433.0000 | 0.0000 | 100.0000 |
| 2,023.0000 | 544.0000 | 544.0000 | 10,066.0000 | 10,066.0000 | 0.0000 | 3,395.0000 | 5,451.0000 | 0.0000 | 100.0000 |
| 2,024.0000 | 544.0000 | 544.0000 | 10,022.0000 | 10,021.0000 | 0.0000 | 3,438.0000 | 5,953.0000 | 0.0000 | 99.9900 |
| 2,025.0000 | 544.0000 | 544.0000 | 10,066.0000 | 10,066.0000 | 0.0000 | 3,419.0000 | 0.0000 | 0.0000 | 100.0000 |
| 2,026.0000 | 274.0000 | 274.0000 | 5,037.0000 | 5,037.0000 | 0.0000 | 1,725.0000 | 0.0000 | 0.0000 | 100.0000 |

All 4,016 historical team-games have nonempty retrospective weekly rosters. They match 74,122 of 74,123 positive-offense participant rows (99.99865%). There are 97 roster rows with missing GSIS IDs and no duplicate valid roster keys. Three matched offensive-participant rows have non-ACT transaction codes (TRC/TRD); these are not proof of inactivity. ACT is not itself a timestamped active-list guarantee, and INA from a revised weekly snapshot cannot be backdated to T−60.

Weekly rosters have no row-level original-version publication/receipt history. Asset created_at/updated_at describes a whole mutable artifact, not when each membership/status became known. For example, the examined 2025 roster asset was created 2026-03-14, after that season. A week key proves an intended historical association, not availability before kickoff.

| season | injury_rows | publisher_date_present |
| --- | --- | --- |
| 2,019.0000 | 5,202.0000 | 5,202.0000 |
| 2,020.0000 | 5,414.0000 | 5,414.0000 |
| 2,021.0000 | 5,348.0000 | 5,348.0000 |
| 2,022.0000 | 5,450.0000 | 5,450.0000 |
| 2,023.0000 | 5,451.0000 | 5,451.0000 |
| 2,024.0000 | 5,954.0000 | 5,954.0000 |
| 2,025.0000 | 5,783.0000 | 0.0000 |
| 2,026.0000 | 3,166.0000 | 0.0000 |

Injury date_modified claims exist in 2019–24; the 2025–26 schemas omit that field entirely, which remains NaT. The 32,780 injury rows with publisher dates before the relevant cutoff, including 5,909 Out claims, are partial retrospective publisher metadata, not archived receipt evidence or complete inactive lists. An Out injury report cannot identify every inactive, transaction or coach decision. Do not turn these into retrospective pregame knowledge.

The nflreadr participation loader explicitly states that 2023-onward FTN participation is provided after all postseason games are completed. It is excluded from in-season share features. Historical membership reconstruction must use dated team/transaction/status versions, not the actual players who appeared or a current roster.

## Count labels versus genuinely feasible forecast states

| market | evaluation_tier | field | n | count_label_known | known_pct |
| --- | --- | --- | --- | --- | --- |
| completions | development_oos | attempts | 2,288.0000 | 2,288.0000 | 100.0000 |
| completions | monitoring | attempts | 289.0000 | 289.0000 | 100.0000 |
| passing_attempts | development_oos | attempts | 2,288.0000 | 2,288.0000 | 100.0000 |
| passing_attempts | monitoring | attempts | 289.0000 | 289.0000 | 100.0000 |
| passing_yards | development_oos | attempts | 2,288.0000 | 2,288.0000 | 100.0000 |
| passing_yards | monitoring | attempts | 289.0000 | 289.0000 | 100.0000 |
| qb_rushing_attempts | development_oos | carries | 2,288.0000 | 2,288.0000 | 100.0000 |
| qb_rushing_attempts | monitoring | carries | 289.0000 | 289.0000 | 100.0000 |
| qb_rushing_yards | development_oos | carries | 2,288.0000 | 2,288.0000 | 100.0000 |
| qb_rushing_yards | monitoring | carries | 289.0000 | 289.0000 | 100.0000 |
| receiving_yards | development_oos | targets | 14,112.0000 | 14,112.0000 | 100.0000 |
| receiving_yards | monitoring | targets | 1,834.0000 | 1,834.0000 | 100.0000 |
| receptions | development_oos | targets | 14,112.0000 | 14,112.0000 | 100.0000 |
| receptions | monitoring | targets | 1,834.0000 | 1,834.0000 | 100.0000 |
| rushing_attempts | development_oos | carries | 4,685.0000 | 4,685.0000 | 100.0000 |
| rushing_attempts | monitoring | carries | 578.0000 | 578.0000 | 100.0000 |
| rushing_yards | development_oos | carries | 4,685.0000 | 4,685.0000 | 100.0000 |
| rushing_yards | monitoring | carries | 578.0000 | 578.0000 | 100.0000 |

| market | evaluation_tier | n | verified_share_states |
| --- | --- | --- | --- |
| completions | development_oos | 2,288.0000 | 0.0000 |
| completions | monitoring | 289.0000 | 0.0000 |
| passing_attempts | development_oos | 2,288.0000 | 0.0000 |
| passing_attempts | monitoring | 289.0000 | 0.0000 |
| passing_yards | development_oos | 2,288.0000 | 0.0000 |
| passing_yards | monitoring | 289.0000 | 0.0000 |
| qb_rushing_attempts | development_oos | 2,288.0000 | 0.0000 |
| qb_rushing_attempts | monitoring | 289.0000 | 0.0000 |
| qb_rushing_yards | development_oos | 2,288.0000 | 0.0000 |
| qb_rushing_yards | monitoring | 289.0000 | 0.0000 |
| receiving_yards | development_oos | 14,112.0000 | 0.0000 |
| receiving_yards | monitoring | 1,834.0000 | 0.0000 |
| receptions | development_oos | 14,112.0000 | 0.0000 |
| receptions | monitoring | 1,834.0000 | 0.0000 |
| rushing_attempts | development_oos | 4,685.0000 | 0.0000 |
| rushing_attempts | monitoring | 578.0000 | 0.0000 |
| rushing_yards | development_oos | 4,685.0000 | 0.0000 |
| rushing_yards | monitoring | 578.0000 | 0.0000 |

Opportunity count labels are available for the frozen rows, but **0 / 55,303** have a complete publication/receipt-verified predecision teammate universe AND inactive state established by the examined snapshots. This is a finding about the audited sources and evidence standard, not proof that no usable historical archive exists anywhere. Roster coverage percentages cannot substitute for timing validity. Report development (2022–25) separately from the already-viewed 2026 weeks 1–10 monitoring tier. No 2026 week-11 onward or later-season outcomes were materialised.

## Stage 2 decision and next actions

The data support retaining the data-quality infrastructure and a retrospective corrected-count-history study, but do not currently support claiming a genuine pregame player-share allocation experiment. Do not fit any Stage 2 arm. Obtain authoritative resolution where possible for the five remaining lateral-credit cases; resolve identity ambiguities; and obtain archived dated membership/transaction/inactive versions with demonstrable availability by T−60. A new archive must be audited for actual version history, not accepted because it contains historical week labels.

If historical provenance cannot be recovered, a narrower retrospective diagnostic could be proposed for separate approval, clearly barred from live-readiness claims. Prospective predecision input snapshots may improve future evidence, but sealed-period outcomes must remain sealed and no new scoring window may be opened without separate approval. The present input captures cannot be backdated to create historical verification.

Retain the approved 2% target/carry accuracy thresholds, four/eight-week paired checks, season-consistency, coherence and all-nine-market/passing-yard safeguards for any future authorised fitting. Preserve the original frozen Stage 1B.1 probability recipes; the under-covering Stage 1C.1 wrapper is not adopted. No threshold or benchmark was retuned in this stage.

## Reproduction and safeguards

Run `python -m stage1c2_stage1.validate research_inputs/stage1c2/data-quality-20261114-v6 --replay` on the exact Python 3.14 / Arrow 24 runtime. Replay recomputes credit repairs, histories, roster availability and participation-ID decisions from committed bounded inputs without downloading mutable replacements or fitting a model. Original raw cache hashes and source URLs/times are recorded; the raw bytes remain preserved outside Git. `scripts/report_stage1c2_stage1.py` regenerates these report tables.

The final bundle declares models_fitted=0 and stage2_authorised=false. Hash/runtime/source/semantic validation and regression tests reject silent source changes, invented zero/verified states, altered frozen labels, final-period rows and attempts to relabel the audit as fitting approval. Stage 1A, Supabase, authentication, ledger/bankroll, dependency pins and all earlier benchmark code/archives remain unchanged. No merge, deployment, dashboard hosting or paid provider configuration is authorised or performed.
