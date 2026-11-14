"""Data-only integrity and semantic checks; never unseal or fit a model."""

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from stage1b.artifacts import digest, runtime
from stage1c.contracts import assert_development
from stage1c1.artifacts import validate as validate_frozen
from stage1c2_stage1.contracts import check_count_ledger


def validate(directory, root):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    m = json.loads((directory / "manifest.json").read_text())
    expected_source = {
        str(x.relative_to(root)): digest(x)
        for x in sorted((root / "stage1c2_stage1").glob("*"))
        if x.suffix in [".py", ".json"]
    }
    if m["source_hashes"] != expected_source or m["runtime"] != runtime(root):
        raise ValueError("Audit source/runtime changed")
    if (
        m["status"] != "data_quality_only"
        or m["stage2_authorised"] is not False
        or m["models_fitted"] != 0
        or not m["final_period_sealed"]
    ):
        raise ValueError("Stage 2 is not authorised by this data audit")
    reference = root / "experiments/stage1c1/controlled-20261114-v1"
    validate_frozen(reference, root)
    if digest(reference / "manifest.json") != m["frozen_reference_manifest"]:
        raise ValueError("Frozen reference changed")
    old = root / "research_inputs/stage1c1/reconciled-20261114-v2"
    if digest(old / "manifest.json") != m["original_reconciliation_manifest"]:
        raise ValueError("Old reconciliation changed")
    base = root / "experiments/stage1b1/improvements-20261113-v1"
    bm = json.loads((base / "manifest.json").read_text())
    if digest(root / bm["input_path"]) != m["frozen_player_snapshot"]:
        raise ValueError("Frozen player labels/features changed")
    payload = {
        str(x.relative_to(directory))
        for x in directory.rglob("*")
        if x.is_file() and x.name != "manifest.json"
    }
    if payload != set(m["files"]) or any(
        p.endswith((".joblib", ".pkl", ".pickle")) for p in payload
    ):
        raise ValueError("Unexpected/missing audit payload or fitted model")
    for name, h in m["files"].items():
        raw = directory / name
        path = raw.resolve()
        if raw.is_symlink() or directory not in path.parents or digest(path) != h:
            raise ValueError("Audit payload mismatch")
        if path.suffix == ".parquet":
            d = pd.read_parquet(path)
            if "season" not in d and "game_id" in d:
                d["season"] = d.game_id.str[:4].astype(int)
                d["week"] = d.game_id.str[5:7].astype(int)
            if {"season", "week"}.issubset(d):
                assert_development(d)
    summary = json.loads((directory / "summary.json").read_text())
    if (
        summary["stage2_authorised"] is not False
        or summary["models_fitted"] != 0
        or not summary["final_period_sealed"]
        or summary["verified_feasible_games"] != 0
    ):
        raise ValueError("Unsupported fitting or availability claim")
    overlay = pd.read_parquet(directory / "history_count_overlay.parquet")
    check_count_ledger(overlay)
    if (
        not overlay.offense_pct.gt(0).all()
        or overlay.stats_observed.fillna(False).any()
        or not overlay.ledger_strict.all()
    ):
        raise ValueError("Missing box incorrectly promoted to a zero")
    expected = pd.read_parquet(old / "player_reconciliation.parquet")
    actual = pd.read_parquet(directory / "player_reconciliation.parquet")
    keys = ["game_id", "team", "player_id"]
    cols = keys + [x for x in expected if x.endswith("_official")]
    pd.testing.assert_frame_equal(
        expected[cols].sort_values(keys).reset_index(drop=True),
        actual[cols].sort_values(keys).reset_index(drop=True),
    )
    reg = pd.read_csv(directory / "discrepancy_register.csv")
    if len(reg) != 17 or reg.duplicated(["game_id", "team"]).any():
        raise ValueError("Discrepancy population changed")
    chosen = reg[reg.decision.eq("supported_internal_repair")]
    after = [x for x in chosen if x.endswith("_diff_after")]
    if not np.allclose(chosen[after], 0, atol=1e-8, rtol=0):
        raise ValueError("Repair does not reconcile")
    if len(chosen) != summary["internally_repaired_team_games"]:
        raise ValueError("Repair count mismatch")
    f = pd.read_parquet(directory / "evaluation_feasibility.parquet")
    original = pd.read_parquet(base / "forecasts.parquet")
    if (
        f.row_id.duplicated().any()
        or set(f.row_id) != set(original.row_id)
        or f.feasible_verified_share_state.any()
    ):
        raise ValueError("Evaluation population or predecision evidence claim changed")
    return dict(
        status="passed_data_audit_only",
        models_fitted=0,
        stage2_authorised=False,
        final_sealed=True,
        player_market_games=len(f),
        supported_internal_repairs=len(chosen),
        unresolved=17 - len(chosen),
    )


def replay(directory, root):
    """Recompute data-only decisions from committed bounded inputs, no downloads."""
    from stage1b.data import read_development_snapshot
    from stage1c1.reconcile import reconcile
    from stage1c2_stage1.credits import repair
    from stage1c2_stage1.audit import histories, roster_audit, snap_audit
    from stage1c2_stage1.build import replace_keys
    from stage1c.contracts import team, development_filters

    directory, root = Path(directory), Path(root)
    result = validate(directory, root)
    old = root / "research_inputs/stage1c1/reconciled-20261114-v2"
    legacy = root / "research_inputs/stage1c/public-20261113-v3"
    base = root / "experiments/stage1b1/improvements-20261113-v1"
    bm = json.loads((base / "manifest.json").read_text())
    source = read_development_snapshot(
        root / bm["input_path"],
        json.loads((root / "stage1b1/protocol.json").read_text()),
    )
    source["team"] = source.team.map(team)
    plays = pd.read_parquet(directory / "case_plays.parquet")
    case_keys = pd.MultiIndex.from_frame(plays[["game_id", "team"]].drop_duplicates())
    select = lambda d: pd.MultiIndex.from_frame(d[["game_id", "team"]]).isin(case_keys)
    rates = pd.read_parquet(legacy / "position_totals.parquet")
    games = pd.read_parquet(legacy / "team_games.parquet")
    credits, _ = repair(plays, source[select(source)])
    rate, ta, pl, _ = reconcile(
        credits, source[select(source)], rates[select(rates)], games[select(games)]
    )

    def compare(actual, name, keys):
        expected = (
            pd.read_parquet(directory / name)
            if name.endswith(".parquet")
            else pd.read_csv(directory / name)
        )
        if "prediction_at" in actual and "prediction_at" in expected:
            expected["prediction_at"] = pd.to_datetime(expected.prediction_at, utc=True)
        pd.testing.assert_frame_equal(
            actual[expected.columns].sort_values(keys).reset_index(drop=True),
            expected.sort_values(keys).reset_index(drop=True),
            check_dtype=False,
            rtol=1e-12,
            atol=1e-12,
        )

    team_audit = replace_keys(
        pd.read_parquet(old / "team_reconciliation.parquet"), ta, ["game_id", "team"]
    )
    player_audit = replace_keys(
        pd.read_parquet(old / "player_reconciliation.parquet"),
        pl,
        ["game_id", "team", "player_id"],
    )
    compare(team_audit, "team_reconciliation.parquet", ["game_id", "team"])
    compare(
        player_audit, "player_reconciliation.parquet", ["game_id", "team", "player_id"]
    )
    compare(
        replace_keys(
            pd.read_parquet(old / "position_totals.parquet"),
            rate,
            ["game_id", "team", "kind"],
        ),
        "position_totals.parquet",
        ["game_id", "team", "kind"],
    )
    h, overlay = histories(player_audit, source)
    compare(
        h,
        "history_count_classification.parquet",
        ["game_id", "team", "player_id", "field"],
    )
    compare(
        overlay,
        "history_count_overlay.parquet",
        ["game_id", "team", "player_id", "field"],
    )
    roster = pd.read_parquet(directory / "roster_snapshot.parquet")
    injury = pd.read_parquet(directory / "injury_snapshot.parquet")
    scored = pd.read_parquet(base / "forecasts.parquet")
    _, matches, coverage, feasible = roster_audit(roster, injury, source, games, scored)
    compare(matches, "participant_roster_audit.parquet", ["game_id", "team", "gsis_id"])
    compare(coverage, "fixture_universe_coverage.csv", ["game_id", "team"])
    compare(feasible, "evaluation_feasibility.parquet", ["row_id"])
    box = pd.read_parquet(
        root
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
    box["team"] = box.team.map(team)
    snap, _ = snap_audit(
        pd.read_parquet(directory / "snap_snapshot.parquet"),
        roster,
        source,
        box,
        team_audit,
        pd.read_parquet(directory / "identity_snapshot.parquet"),
    )
    compare(snap, "snap_participation_audit.parquet", ["game_id", "team", "pfr_id"])
    return {**result, "all_data_decisions_replayed": True}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("directory", type=Path)
    p.add_argument("--replay", action="store_true")
    a = p.parse_args()
    print(
        json.dumps(
            (replay if a.replay else validate)(
                a.directory, Path(__file__).resolve().parents[1]
            )
        )
    )
