"""Reproduce the Stage 1C.2 DATA-ONLY report; never fit or price a model."""

import argparse
import json
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stage1c2_stage1.validate import validate  # noqa: E402


def table(d):
    z = d.copy()
    for c in z.select_dtypes(include="number"):
        z[c] = z[c].map(lambda x: f"{x:,.4f}" if pd.notna(x) else "unknown")
    return "\n".join(
        [
            "| " + " | ".join(z.columns) + " |",
            "| " + " | ".join(["---"] * len(z.columns)) + " |",
        ]
        + [
            "| " + " | ".join(map(str, r)) + " |"
            for r in z.itertuples(index=False, name=None)
        ]
    )


def report(directory, output):
    directory, output = Path(directory), Path(output)
    result = validate(directory, ROOT)
    output.mkdir(parents=True, exist_ok=True)
    reg = pd.read_csv(directory / "discrepancy_register.csv")
    hist = pd.read_parquet(directory / "history_count_classification.parquet")
    missing = hist[
        ~hist.stats_observed.fillna(False)
        & hist.participation_established
        & hist.position.isin(["QB", "RB", "WR", "TE"])
    ]
    zero = (
        missing.groupby(["position", "field", "classification"])
        .size()
        .rename("n")
        .reset_index()
    )
    zero.to_csv(output / "missing_box_summary.csv", index=False)
    missing.groupby(["position", "season", "field", "classification"]).size().rename(
        "n"
    ).reset_index().to_csv(output / "missing_box_by_season.csv", index=False)
    roster = pd.read_csv(directory / "fixture_universe_coverage.csv")
    ro = roster.groupby("season", as_index=False).agg(
        team_games=("game_id", "size"),
        nonempty_rosters=("roster_rows", lambda x: int(x.gt(0).sum())),
        offense_participants=("offensive_participants", "sum"),
        matched=("participants_matched", "sum"),
        non_ACT_transaction_codes=("participants_not_ACT", "sum"),
        retrospective_INA=("retrospective_INA", "sum"),
        injury_publisher_date_before_cutoff=(
            "injury_publisher_claim_before_cutoff",
            "sum",
        ),
        verified_universes=("verified_complete_pregame_universe", "sum"),
    )
    ro["participant_match_pct"] = 100 * ro.matched / ro.offense_participants
    ro.to_csv(output / "membership_by_season.csv", index=False)
    f = pd.read_parquet(directory / "evaluation_feasibility.parquet")
    feasibility = f.groupby(["market", "evaluation_tier"], as_index=False).agg(
        n=("row_id", "size"),
        verified_share_states=("feasible_verified_share_state", "sum"),
    )
    feasibility.to_csv(output / "feasible_by_market.csv", index=False)
    counts = (
        pd.read_csv(directory / "count_label_coverage.csv")
        .groupby(["market", "evaluation_tier", "field"], as_index=False)[
            ["n", "count_label_known"]
        ]
        .sum()
    )
    counts["known_pct"] = 100 * counts.count_label_known / counts.n
    counts.to_csv(output / "count_labels_by_market.csv", index=False)
    snap = pd.read_parquet(directory / "snap_participation_audit.parquet")
    sn = snap.groupby("season", as_index=False).agg(
        snap_player_games=("game_id", "size"),
        unresolved_ids=("identity_unresolved", "sum"),
        conflicting_ids=("identity_conflict", "sum"),
        mapped_absent_from_features=("absent_from_frozen_features", "sum"),
    )
    sn.to_csv(output / "snap_identity_by_season.csv", index=False)
    skill_unknown = (
        snap[snap.identity_unresolved & snap.position.isin(["QB", "RB", "WR", "TE"])]
        .groupby(["position", "season"])
        .size()
        .rename("n")
        .reset_index()
    )
    skill_unknown.to_csv(output / "unresolved_skill_snap_ids.csv", index=False)
    rare = snap[snap.absent_from_frozen_features]
    rare[
        [
            "game_id",
            "team",
            "pfr_id",
            "player_id",
            "position",
            "identity_method",
            "identity_review_required_for_new_history",
        ]
    ].to_csv(output / "additional_identity_review.csv", index=False)
    sources = pd.DataFrame(json.loads((directory / "source_index.json").read_text()))
    sources[
        [
            "kind",
            "name",
            "created_at",
            "updated_at",
            "retrieved_at",
            "sha256",
            "browser_download_url",
        ]
    ].to_csv(output / "source_inventory.csv", index=False)
    tiers = []
    for season, g in pd.read_parquet(directory / "injury_snapshot.parquet").groupby(
        "season"
    ):
        tiers.append(
            dict(
                season=season,
                injury_rows=len(g),
                publisher_date_present=int(g.date_modified.notna().sum()),
            )
        )
    injury = pd.DataFrame(tiers)
    injury.to_csv(output / "injury_timestamp_coverage.csv", index=False)
    text = [
        "# Stage 1C.2 Stage 1 — data quality and feasibility findings",
        "**Recommendation: NO-GO for Stage 2 fitting intended to establish genuinely feasible historical pregame allocation.** Opportunity labels and missing-box histories are substantially auditable; the examined sources do not establish complete historically versioned teammate/inactive states at T−60. Stage 2 remains unauthorised. No research model has been fitted, probability method changed, forecast activated or production file modified.",
        "## Discrepancies: 12 supported internal reconciliations; five unresolved",
        "The new ledger restores two counted events incorrectly excluded by the generic no_play classification: HOU 2024 week 15, play 2274 (Dare Ogunbowale: one carry/35 rushing yards after a replay reversal); PIT 2025 week 2, play 3686 (Aaron Rodgers: an incomplete grounding pass, one attempt/zero passing yards). These are narrowly allowlisted with input flags, actor IDs and exact description fragments; other no-plays remain excluded.",
        "Ten other team-games receive missing intermediate-lateral yard credits. No carry, target or reception is added for a lateral. Multiple Saubert segments are aggregated (+17), negative credits remain negative, and existing final-player/fumble adjustments are preserved. Every accepted change is supported by an explicit play-description credit and reconciles exactly to the original player and team counters. These are research event-ledger corrections, not rewritten official benchmark labels. Shared upstream descriptions/counters provide internal corroboration, not independent certification. Public ESPN API corroboration was blocked by the environment proxy at site.api.espn.com when attempted; no independent corroboration is claimed.",
        table(reg[["game_id", "team", "decision"]]),
        "Unresolved cases are retained without a residual allocation:\n\n"
        + "\n".join(
            f"- **{r.game_id} / {r.team}:** {r.reason}"
            for r in reg[reg.decision.eq("unresolved_no_patch")].itertuples()
        ),
        "The complete field-level before/after register and accepted source fragments are committed in the immutable audit bundle. Five unresolved games affect receiving-yard attribution, not an excuse to invent target counts or to alter frozen evaluation outcomes.",
        "## Missing boxes and genuine zero opportunities",
        table(zero),
        "These represent 5,701 distinct offensive-participant missing-box player-games: 106 QB, 475 RB, 3,028 TE and 2,092 WR. The count ledgers support zero attempts, carries and targets for each of these records after the inclusion repairs. There are no recovered positive opportunities in this missing-box cohort. Three count-field overlay rows per player-game are not three independent observations. This is a source-backed count-history overlay only: no production zeros or new evaluation targets were manufactured, and zero opportunities do not rule out exceptional lateral production.",
        "Full position/season classification and original observations remain separate. The source snapshot includes 185,912 player-games; the study preserves the existing 55,303 player-market evaluation rows and every frozen label. The overlay exposes a +36h retrospective availability proxy separately from a verified availability field, which remains missing. It cannot masquerade as an archived historical predecision source.",
        "## Participation and identity coverage",
        table(sn),
        f"Across {len(snap):,} snap player-games, {int(snap.identity_unresolved.sum()):,} IDs remain unresolved, including {int(snap.identity_conflict.sum()):,} conflicting weekly-roster/static-crosswalk links. Same-week PFR links alone match only 125,874 rows; a permanent-ID-only crosswalk recovers most others. Its current team, position and status columns are deliberately not read. Later-discovered ID evidence is labelled retrospective; it does not establish historical roster membership.",
        table(skill_unknown),
        "No additional WR/TE/RB/QB game is confirmed as absent from the frozen features among unambiguously ID-matched snap records. Unmapped skill rows remain unknown, so this is not proof that coverage is complete. Three other-position rows are candidate identity discrepancies requiring review, not added zero histories; source position/identity inconsistencies prevent automatic acceptance. See additional_identity_review.csv. Special-teams-only games are audited but do not automatically determine sportsbook participation/void rules.",
        "## Membership, statuses and publication timing",
        table(ro),
        "All 4,016 historical team-games have nonempty retrospective weekly rosters. They match 74,122 of 74,123 positive-offense participant rows (99.99865%). There are 97 roster rows with missing GSIS IDs and no duplicate valid roster keys. Three matched offensive-participant rows have non-ACT transaction codes (TRC/TRD); these are not proof of inactivity. ACT is not itself a timestamped active-list guarantee, and INA from a revised weekly snapshot cannot be backdated to T−60.",
        "Weekly rosters have no row-level original-version publication/receipt history. Asset created_at/updated_at describes a whole mutable artifact, not when each membership/status became known. For example, the examined 2025 roster asset was created 2026-03-14, after that season. A week key proves an intended historical association, not availability before kickoff.",
        table(injury),
        "Injury date_modified claims exist in 2019–24; the 2025–26 schemas omit that field entirely, which remains NaT. The 32,780 injury rows with publisher dates before the relevant cutoff, including 5,909 Out claims, are partial retrospective publisher metadata, not archived receipt evidence or complete inactive lists. An Out injury report cannot identify every inactive, transaction or coach decision. Do not turn these into retrospective pregame knowledge.",
        "The nflreadr participation loader explicitly states that 2023-onward FTN participation is provided after all postseason games are completed. It is excluded from in-season share features. Historical membership reconstruction must use dated team/transaction/status versions, not the actual players who appeared or a current roster.",
        "## Count labels versus genuinely feasible forecast states",
        table(counts),
        table(feasibility),
        "Opportunity count labels are available for the frozen rows, but **0 / 55,303** have a complete publication/receipt-verified predecision teammate universe AND inactive state established by the examined snapshots. This is a finding about the audited sources and evidence standard, not proof that no usable historical archive exists anywhere. Roster coverage percentages cannot substitute for timing validity. Report development (2022–25) separately from the already-viewed 2026 weeks 1–10 monitoring tier. No 2026 week-11 onward or later-season outcomes were materialised.",
        "## Stage 2 decision and next actions",
        "The data support retaining the data-quality infrastructure and a retrospective corrected-count-history study, but do not currently support claiming a genuine pregame player-share allocation experiment. Do not fit any Stage 2 arm. Obtain authoritative resolution where possible for the five remaining lateral-credit cases; resolve identity ambiguities; and obtain archived dated membership/transaction/inactive versions with demonstrable availability by T−60. A new archive must be audited for actual version history, not accepted because it contains historical week labels.",
        "If historical provenance cannot be recovered, a narrower retrospective diagnostic could be proposed for separate approval, clearly barred from live-readiness claims. Prospective predecision input snapshots may improve future evidence, but sealed-period outcomes must remain sealed and no new scoring window may be opened without separate approval. The present input captures cannot be backdated to create historical verification.",
        "Retain the approved 2% target/carry accuracy thresholds, four/eight-week paired checks, season-consistency, coherence and all-nine-market/passing-yard safeguards for any future authorised fitting. Preserve the original frozen Stage 1B.1 probability recipes; the under-covering Stage 1C.1 wrapper is not adopted. No threshold or benchmark was retuned in this stage.",
        "## Reproduction and safeguards",
        "Run `python -m stage1c2_stage1.validate research_inputs/stage1c2/data-quality-20261114-v5 --replay` on the exact Python 3.14 / Arrow 24 runtime. Replay recomputes credit repairs, histories, roster availability and participation-ID decisions from committed bounded inputs without downloading mutable replacements or fitting a model. Original raw cache hashes and source URLs/times are recorded; the raw bytes remain preserved outside Git. `scripts/report_stage1c2_stage1.py` regenerates these report tables.",
        "The final bundle declares models_fitted=0 and stage2_authorised=false. Hash/runtime/source/semantic validation and regression tests reject silent source changes, invented zero/verified states, altered frozen labels, final-period rows and attempts to relabel the audit as fitting approval. Stage 1A, Supabase, authentication, ledger/bankroll, dependency pins and all earlier benchmark code/archives remain unchanged. No merge, deployment, dashboard hosting or paid provider configuration is authorised or performed.",
    ]
    (output / "REPORT.md").write_text("\n\n".join(text) + "\n")
    print(json.dumps(result))
    print(output / "REPORT.md")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("directory", type=Path)
    p.add_argument("--output", type=Path, default=ROOT / "docs/stage1c2-stage1-results")
    a = p.parse_args()
    report(a.directory, a.output)
