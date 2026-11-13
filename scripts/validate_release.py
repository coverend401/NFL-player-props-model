"""Validate a complete release without fetching data or touching production."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import joblib
import numpy as np
import pandas as pd
from release_utils import validate_manifest, SOURCE_FILES, select_release
from scripts.build_slate import build_slate, compute_top_picks, MARKETS as SLATE_MARKETS
from scripts.train_all_markets import MARKETS, prepare_dataset


def validate_bundle(directory, repo=ROOT, allow_pending=False, app_smoke=False):
    directory = Path(directory).resolve()
    repo = Path(repo).resolve()
    manifest = validate_manifest(directory, repo, allow_pending=allow_pending)
    rid = manifest["release_id"]
    data = directory / "data"
    tables = {
        name: pd.read_parquet(data / f"{name}.parquet")
        for name in ["weekly_player_data", "player_features", "slate", "top_picks"]
    }
    for name, frame in tables.items():
        if (
            frame.empty
            or "release_id" not in frame
            or not frame.release_id.eq(rid).all()
        ):
            raise ValueError(f"Empty or mixed-release table: {name}")
    features = tables["player_features"]
    slate = tables["slate"]
    picks = tables["top_picks"]
    if features.duplicated(["player_id", "season", "week"]).any():
        raise ValueError("Duplicate engineered player-game rows")
    required = set(SLATE_MARKETS.values())
    if set(slate.market) != required or not required.issubset(
        set(slate[slate.projection_status.eq("complete")].market)
    ):
        raise ValueError("Every market must have complete, usable forecast rows")
    if (
        slate.duplicated(["player_id", "market", "game_id"]).any()
        or not np.isfinite(slate.projection).all()
    ):
        raise ValueError("Duplicate or nonfinite projections")
    if not picks.projection_status.eq("complete").all():
        raise ValueError("Unresolved scenarios cannot be Top Picks")
    prediction = pd.to_datetime(slate.prediction_at, utc=True)
    cutoff = pd.to_datetime(slate.completed_before, utc=True)
    if (
        prediction.nunique() != 1
        or cutoff.nunique() != 1
        or (cutoff > prediction).any()
    ):
        raise ValueError("Inconsistent forecast timestamps")
    started = pd.Timestamp(manifest["build_started_at"])
    finished = pd.Timestamp(manifest["built_at"])
    if not started <= prediction.iloc[0] <= finished:
        raise ValueError("Forecast not produced during this build")
    if (pd.to_datetime(slate.last_completed_game_at, utc=True) >= cutoff).any():
        raise ValueError("Forecast includes an unavailable game")
    summary = {}
    asofs = set()
    for market, config in MARKETS.items():
        name = config.get("model_name", market)
        b = joblib.load(data / f"model_{name}.joblib")
        trained = pd.Timestamp(b["training_as_of"])
        last = pd.Timestamp(b["training_cutoff"])
        if b.get("release_id") != rid or b.get("feature_timing_version") != "stage1a":
            raise ValueError(f"Mixed or legacy model: {name}")
        if b["features"] != config["features"] or b["positions"] != config["positions"]:
            raise ValueError(f"Model schema mismatch: {name}")
        if (
            not started <= trained <= prediction.iloc[0]
            or not last < trained
            or not last < cutoff.iloc[0]
        ):
            raise ValueError(f"Future/stale build provenance: {name}")
        if not np.isfinite(b["resid_std"]) or b["resid_std"] <= 0:
            raise ValueError(f"Invalid residual scale: {name}")
        eligible = prepare_dataset(
            features, config.get("target_col", market), config, as_of=trained
        )
        if (
            eligible.empty
            or pd.to_datetime(eligible.completed_at, utc=True).max() != last
        ):
            raise ValueError(f"Training data/cutoff mismatch: {name}")
        if not np.isfinite(b["model"].predict(eligible[b["features"]].tail(3))).all():
            raise ValueError(f"Invalid model predictions: {name}")
        asofs.add(trained.isoformat())
        summary[name] = {"rows": len(eligible), "training_cutoff": last.isoformat()}
    if len(asofs) != 1:
        raise ValueError("Models were not trained in one coordinated run")
    schedule = pd.read_parquet(directory / "inputs/schedule.parquet")
    qb = json.loads((directory / "inputs/qb_starters.json").read_text())
    replay = build_slate(
        features,
        schedule,
        prediction.iloc[0],
        current_qb_starters=qb["starters"],
        qb_starters_as_of=qb["as_of"],
        completed_before=cutoff.iloc[0],
        model_dir=data,
    )
    actual = slate.drop(columns="release_id")
    sort = ["market", "player_id", "game_id"]
    pd.testing.assert_frame_equal(
        replay.sort_values(sort).reset_index(drop=True),
        actual.sort_values(sort).reset_index(drop=True),
        check_dtype=False,
    )
    expected_picks = compute_top_picks(actual, side_filter="Over")
    pd.testing.assert_frame_equal(
        expected_picks.sort_values(sort).reset_index(drop=True),
        picks.drop(columns="release_id").sort_values(sort).reset_index(drop=True),
        check_dtype=False,
    )
    if set(manifest["game_kickoffs"]) != set(slate.game_id):
        raise ValueError("Incomplete fixture expiry metadata")
    earliest = min(pd.Timestamp(t) for t in manifest["game_kickoffs"].values())
    if (
        pd.Timestamp(manifest["activate_before"]) != earliest
        or earliest <= prediction.iloc[0]
    ):
        raise ValueError("Invalid activation deadline")
    if app_smoke:
        smoke_app(directory, repo)
    return {
        "release_id": rid,
        "models": summary,
        "slate_rows": len(slate),
        "statuses": slate.projection_status.value_counts().to_dict(),
        "top_picks": len(picks),
        "replayed_all_predictions": True,
        "app_smoke": bool(app_smoke),
    }


def smoke_app(directory, repo):
    """No production secrets, databases, pointer or working tree are touched."""
    from streamlit.testing.v1 import AppTest
    import streamlit as st
    from unittest.mock import patch

    from ledger import SQLiteBackend

    connections = []

    def temporary_backend(*args, **kwargs):
        backend = SQLiteBackend(*args, **kwargs)
        connections.append(backend.con)
        return backend

    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="nfl-release-smoke-") as tmp:
        root = Path(tmp)
        for name in SOURCE_FILES:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / name, root / name)
        # Legacy files are not needed by the active bundle; copy no ledger/secrets.
        target = root / "release_candidates" / directory.name
        shutil.copytree(directory, target)
        select_release(root, str(target.relative_to(root)), expected_current="legacy")
        try:
            os.chdir(root)
            with (
                patch.dict(os.environ, {"NFL_APP_ROOT": str(root)}),
                patch("ledger.SQLiteBackend", side_effect=temporary_backend),
            ):
                st.cache_resource.clear()
                st.cache_data.clear()
                at = AppTest.from_file(str(root / "app.py"), default_timeout=90)
                at.secrets.update(
                    {"APP_PASSWORD": "", "SUPABASE_URL": "", "SUPABASE_KEY": ""}
                )
                at.run()
                if at.exception:
                    raise ValueError([e.message for e in at.exception])
                slate = pd.read_parquet(target / "data/slate.parquet")
                for market in SLATE_MARKETS.values():
                    at.selectbox[0].select(market).run()
                    player = (
                        slate[
                            (slate.market == market)
                            & slate.projection_status.eq("complete")
                        ]
                        .iloc[0]
                        .player
                    )
                    at.selectbox[1].select(player).run()
                    next(
                        w for w in at.text_input if w.label.startswith("Odds (decimal")
                    ).input("1.91").run()
                    if at.exception:
                        raise ValueError([e.message for e in at.exception])
                scenarios = slate[slate.projection_status.eq("roof_scenarios_only")]
                if len(scenarios):
                    row = scenarios.iloc[0]
                    at.selectbox[0].select(row.market).run()
                    at.selectbox[1].select(row.player).run()
                    if at.exception or any(
                        m.label == "Model probability Over" for m in at.metric
                    ):
                        raise ValueError("Scenario pricing was not suppressed")
        finally:
            for connection in connections:
                connection.close()
            os.chdir(previous)
            st.cache_resource.clear()
            st.cache_data.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--all-candidates", action="store_true")
    parser.add_argument("--app-smoke", action="store_true")
    args = parser.parse_args()
    if not args.all_candidates and args.directory is None:
        parser.error("Provide a candidate directory or --all-candidates")
    paths = (
        sorted(
            p
            for p in (ROOT / "release_candidates").glob("*/manifest.json")
            if not p.parent.name.startswith(".")
        )
        if args.all_candidates
        else [args.directory / "manifest.json"]
    )
    if not paths:
        raise SystemExit("No release candidates found")
    for path in paths:
        print(
            json.dumps(validate_bundle(path.parent, app_smoke=args.app_smoke), indent=2)
        )
