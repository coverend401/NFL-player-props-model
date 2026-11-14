"""Build an immutable DATA-ONLY audit; there is no fitting entrypoint."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import subprocess

import pandas as pd
from stage1b.artifacts import digest, runtime
from stage1b.data import read_development_snapshot
from stage1c.contracts import development_filters, team
from stage1c1.reconcile import COLS, reconcile
from stage1c2_stage1.contracts import (
    ROSTER_COLUMNS,
    SNAP_COLUMNS,
    INJURY_COLUMNS,
    bounded_read,
    check_count_ledger,
)
from stage1c2_stage1.credits import repair, DECISIONS
from stage1c2_stage1.audit import histories, roster_audit, snap_audit

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "research_inputs/stage1c1/reconciled-20261114-v2"
LEGACY = ROOT / "research_inputs/stage1c/public-20261113-v3"
REFERENCE = ROOT / "experiments/stage1c1/controlled-20261114-v1"


def replace_keys(old, new, keys):
    old_index = pd.MultiIndex.from_frame(old[keys])
    new_index = pd.MultiIndex.from_frame(new[keys])
    if new_index.duplicated().any():
        raise ValueError("Ambiguous replacement keys")
    return pd.concat([old[~old_index.isin(new_index)], new], ignore_index=True)


def acquire_from_cache(cache, work):
    """Copy only bounded, minimal columns; preserve original artifact metadata."""
    frames = {}
    records = []
    for kind, filename, columns in [
        ("roster", "roster_weekly", ROSTER_COLUMNS),
        ("snap", "snap_counts", SNAP_COLUMNS),
        ("injury", "injuries", INJURY_COLUMNS),
    ]:
        metas = json.loads((cache / f"{kind}_sources.json").read_text())
        chunks = []
        for meta in metas:
            file = cache / meta["name"]
            if file.stat().st_size != meta["size"] or not meta[
                "browser_download_url"
            ].startswith(
                "https://github.com/nflverse/nflverse-data/releases/download/"
            ):
                raise ValueError("Unexpected source artifact")
            chunks.append(bounded_read(file, columns))
            records.append(
                dict(
                    meta,
                    kind=kind,
                    sha256=digest(file),
                    row_publication_history_verified=False,
                )
            )
        d = pd.concat(chunks, ignore_index=True)
        d.to_parquet(work / f"{kind}_snapshot.parquet", index=False)
        frames[kind] = d
    # Permanent ID links only. Current team, position and status are deliberately
    # not read, and this later-discovered crosswalk supplies no pregame membership.
    identity_meta = json.loads((cache / "identity_sources.json").read_text())[0]
    identity_path = cache / identity_meta["name"]
    if identity_path.stat().st_size != identity_meta["size"]:
        raise ValueError("Identity source changed")
    frames["identity"] = pd.read_parquet(identity_path, columns=["gsis_id", "pfr_id"])
    frames["identity"].to_parquet(work / "identity_snapshot.parquet", index=False)
    records.append(
        dict(
            identity_meta,
            kind="identity",
            sha256=digest(identity_path),
            row_publication_history_verified=False,
        )
    )
    (work / "source_index.json").write_text(json.dumps(records, indent=2) + "\n")
    return frames


def build(output, cache, pbp_cache):
    output, cache, pbp_cache = Path(output).resolve(), Path(cache), Path(pbp_cache)
    if output.exists():
        raise ValueError("Immutable audit output exists")
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--", "stage1c2_stage1"], cwd=ROOT, text=True
    ).strip():
        raise ValueError(
            "Commit the data-audit implementation before building an immutable bundle"
        )
    base = ROOT / "experiments/stage1b1/improvements-20261113-v1"
    bm = json.loads((base / "manifest.json").read_text())
    protocol = json.loads((ROOT / "stage1b1/protocol.json").read_text())
    source = read_development_snapshot(ROOT / bm["input_path"], protocol)
    source["team"] = source.team.map(team)
    before = pd.read_parquet(OLD / "team_reconciliation.parquet")
    deltas = [x for x in before if x.endswith("_diff")]
    cases = before[before[deltas].abs().gt(1e-8).any(axis=1)]
    if len(cases) != 17:
        raise ValueError("Frozen discrepancy register changed")
    case_keys = pd.MultiIndex.from_frame(cases[["game_id", "team"]])
    subset = source[
        pd.MultiIndex.from_frame(source[["game_id", "team"]]).isin(case_keys)
    ]
    legacy = pd.read_parquet(LEGACY / "position_totals.parquet")
    games = pd.read_parquet(LEGACY / "team_games.parquet")
    im = json.loads((LEGACY / "manifest.json").read_text())
    raw, raw_sources = [], []
    for year in sorted(cases.game_id.str[:4].astype(int).unique()):
        path = pbp_cache / f"{year}.parquet"
        meta = next(
            x for x in im["source_records"] if x["url"].endswith(f"_{year}.parquet")
        )
        if digest(path) != meta["sha256"]:
            raise ValueError("Original PBP cache changed")
        d = pd.read_parquet(
            path, columns=COLS + ["desc"], filters=development_filters()
        )
        d = d[d.game_id.isin(cases.game_id)]
        d = d[d.posteam.notna()].copy()
        d["team"] = d.posteam.map(team)
        raw.append(d[pd.MultiIndex.from_frame(d[["game_id", "team"]]).isin(case_keys)])
        raw_sources.append(meta)
    pbp = pd.concat(raw, ignore_index=True)
    credits, evidence = repair(pbp, subset)
    mask = lambda d: pd.MultiIndex.from_frame(d[["game_id", "team"]]).isin(case_keys)
    rate_patch, audit_patch, player_patch, unresolved = reconcile(
        credits, subset, legacy[mask(legacy)], games[mask(games)]
    )
    spec = json.loads(DECISIONS.read_text())
    accepted = set((evidence.game_id + "|" + evidence.team))
    for r in audit_patch.itertuples():
        if r.game_id + "|" + r.team in accepted:
            if not r.pass_strict or not r.rush_strict or not r.rec_strict:
                raise ValueError(
                    f"Proposed repair fails per-player/team reconciliation: {r.game_id} {r.team}"
                )
    audit = replace_keys(before, audit_patch, ["game_id", "team"])
    players = replace_keys(
        pd.read_parquet(OLD / "player_reconciliation.parquet"),
        player_patch,
        ["game_id", "team", "player_id"],
    )
    rates = replace_keys(
        pd.read_parquet(OLD / "position_totals.parquet"),
        rate_patch,
        ["game_id", "team", "kind"],
    )
    with tempfile.TemporaryDirectory(prefix="nfl-c2-data-") as tmp:
        work = Path(tmp)
        frames = acquire_from_cache(cache, work)
        pbp["season"] = pbp.game_id.str[:4].astype(int)
        pbp["week"] = pbp.game_id.str[5:7].astype(int)
        pbp.to_parquet(work / "case_plays.parquet", index=False)
        evidence["season"] = evidence.game_id.str[:4].astype(int)
        evidence["week"] = evidence.game_id.str[5:7].astype(int)
        evidence.to_parquet(work / "accepted_credit_evidence.parquet", index=False)
        register = cases.merge(
            audit_patch[["game_id", "team"] + deltas],
            on=["game_id", "team"],
            suffixes=("_before", "_after"),
            validate="one_to_one",
        )
        register["decision"] = [
            "supported_internal_repair"
            if g + "|" + t in accepted
            else "unresolved_no_patch"
            for g, t in zip(register.game_id, register.team)
        ]
        register["reason"] = [
            "Unambiguous event/actor credit plus exact original box/team reconciliation; no independent corroboration claimed"
            if g + "|" + t in accepted
            else spec["unresolved"][g + "|" + t]
            for g, t in zip(register.game_id, register.team)
        ]
        register["season"] = register.game_id.str[:4].astype(int)
        register["week"] = register.game_id.str[5:7].astype(int)
        register.to_csv(work / "discrepancy_register.csv", index=False)
        audit.to_parquet(work / "team_reconciliation.parquet", index=False)
        players.to_parquet(work / "player_reconciliation.parquet", index=False)
        rates.to_parquet(work / "position_totals.parquet", index=False)
        hist, overlay = histories(players, source)
        check_count_ledger(overlay)
        hist.to_parquet(work / "history_count_classification.parquet", index=False)
        overlay.to_parquet(work / "history_count_overlay.parquet", index=False)
        scored = pd.read_parquet(base / "forecasts.parquet")
        rr, matches, coverage, eval_coverage = roster_audit(
            frames["roster"], frames["injury"], source, games, scored
        )
        matches[
            [
                "game_id",
                "team",
                "gsis_id",
                "season",
                "week",
                "position",
                "status",
                "present_in_retrospective_roster",
                "retrospective_active",
                "verified_predecision_membership",
                "verified_predecision_inactive",
            ]
        ].to_parquet(work / "participant_roster_audit.parquet", index=False)
        coverage.to_csv(work / "fixture_universe_coverage.csv", index=False)
        eval_coverage[
            [
                "row_id",
                "market",
                "season",
                "week",
                "game_id",
                "team",
                "position",
                "evaluation_tier",
                "feasible_verified_share_state",
            ]
        ].to_parquet(work / "evaluation_feasibility.parquet", index=False)
        raw_box = pd.read_parquet(
            ROOT
            / "release_candidates/stage1a-20261113-py314-arrow24-r2/data/weekly_player_data.parquet",
            columns=[
                "game_id",
                "team",
                "player_id",
                "season",
                "week",
                "attempts",
                "carries",
                "targets",
            ],
            filters=development_filters(),
        )
        raw_box["team"] = raw_box.team.map(team)
        snaps, ambiguous = snap_audit(
            frames["snap"], frames["roster"], source, raw_box, audit, frames["identity"]
        )
        snaps.to_parquet(work / "snap_participation_audit.parquet", index=False)
        hist.groupby(
            ["position", "field", "classification"], dropna=False
        ).size().rename("n").reset_index().to_csv(
            work / "history_counts.csv", index=False
        )
        hist[
            ~hist.stats_observed.fillna(False) & hist.participation_established
        ].groupby(["position", "season", "field", "classification"]).size().rename(
            "n"
        ).reset_index().to_csv(work / "missing_box_counts.csv", index=False)
        feasibility = eval_coverage.groupby(
            ["market", "evaluation_tier", "season"], as_index=False
        ).agg(n=("row_id", "size"), verified=("feasible_verified_share_state", "sum"))
        feasibility.to_csv(work / "feasibility_by_market_season.csv", index=False)
        coverage_rows = []
        for (market, tier, season), group in eval_coverage.groupby(
            ["market", "evaluation_tier", "season"]
        ):
            field = (
                "attempts"
                if market in ["passing_yards", "passing_attempts", "completions"]
                else "carries"
                if "rushing" in market
                else "targets"
            )
            count = group.merge(
                players[
                    [
                        "game_id",
                        "team",
                        "player_id",
                        field + "_official",
                        field + "_event_validated",
                    ]
                ],
                on=["game_id", "team", "player_id"],
                validate="many_to_one",
            )
            known = (
                count[field + "_official"].notna()
                | count[field + "_event_validated"].notna()
            )
            coverage_rows.append(
                dict(
                    market=market,
                    evaluation_tier=tier,
                    season=int(season),
                    field=field,
                    n=len(group),
                    count_label_known=int(known.sum()),
                )
            )
        pd.DataFrame(coverage_rows).to_csv(
            work / "count_label_coverage.csv", index=False
        )
        summary = dict(
            scope="Stage1C.2 Stage1 DATA QUALITY ONLY",
            models_fitted=0,
            stage2_authorised=False,
            final_period_sealed=True,
            decision="NO_GO_FOR_GENUINELY_FEASIBLE_PREGAME_ALLOCATION_FITTING",
            baseline_player_market_games=len(scored),
            verified_feasible_games=int(
                eval_coverage.feasible_verified_share_state.sum()
            ),
            reviewed_team_games=17,
            internally_repaired_team_games=len(accepted),
            unresolved_team_games=17 - len(accepted),
            ambiguous_roster_identity_rows=int(rr.ambiguous.sum()),
            roster_missing_gsis_rows=int(rr.gsis_id.isna().sum()),
            roster_duplicate_key_rows=int(
                rr[rr.gsis_id.notna()]
                .duplicated(["season", "week", "team", "gsis_id"], keep=False)
                .sum()
            ),
            snap_unresolved_identity_rows=int(snaps.identity_unresolved.sum()),
            snap_conflicting_identity_rows=int(snaps.identity_conflict.sum()),
            ambiguous_snap_crosswalk_rows=ambiguous,
            no_independent_credit_corroboration_claim=True,
            evidence_limit="Revised weekly status/membership snapshots lack historical original-version publication/receipt evidence; injury date_modified is publisher metadata, not a complete inactive list or an archived receipt",
        )
        (work / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        provenance = dict(
            schema=1,
            status="data_quality_only",
            created_at=datetime.now(timezone.utc).isoformat(),
            source_commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            source_hashes={
                str(x.relative_to(ROOT)): digest(x)
                for x in sorted((ROOT / "stage1c2_stage1").glob("*"))
                if x.suffix in [".py", ".json"]
            },
            runtime=runtime(ROOT),
            frozen_reference_manifest=digest(REFERENCE / "manifest.json"),
            frozen_player_snapshot=digest(ROOT / bm["input_path"]),
            original_reconciliation_manifest=digest(OLD / "manifest.json"),
            pbp_sources=raw_sources,
            files={
                str(x.relative_to(work)): digest(x)
                for x in sorted(work.iterdir())
                if x.is_file()
            },
            stage2_authorised=False,
            models_fitted=0,
            final_period_sealed=True,
        )
        (work / "manifest.json").write_text(json.dumps(provenance, indent=2) + "\n")
        from stage1c2_stage1.validate import validate

        validate(work, ROOT)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, output)
    print(json.dumps(summary))
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cache", type=Path, default=Path("/tmp/stage1c2-evidence"))
    p.add_argument("--pbp-cache", type=Path, default=Path("/tmp/stage1c-pbp"))
    a = p.parse_args()
    build(a.output, a.cache, a.pbp_cache)
