"""Explicit research-only frozen-model contract. Production validation is untouched."""

import os
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from release_utils import (
    MODEL_NAMES,
    checked_path,
    read_json,
    resolve_release,
    runtime_versions,
    sha256,
    validate_manifest,
)
from scripts.build_slate import MARKETS, compute_top_picks, get_upcoming_week
from scripts.forecast_features import utc_timestamp
from scripts.train_all_markets import MARKETS as MODEL_CONFIG

from .inference_builder import (
    build_inference,
    candidate_state,
    derive_eligibility,
    eligibility_map,
)

TYPE = "research_frozen_model_inference_v1"
CODE = [
    "research_platform/inference_builder.py",
    "research_platform/inference_release.py",
    "scripts/prepare_research_inference.py",
    "odds_value_research.py",
]
FILES = {
    "features.parquet",
    "schedule.parquet",
    "roster_evidence.csv",
    "eligibility.json",
    "qb_starters.json",
    "sources.json",
    "slate.parquet",
    "top_picks.parquet",
}


def validate_inference(directory, repo, *, replay=False, allow_pending=False):
    if Path(directory).is_symlink():
        raise ValueError("Inference release directory must not be a symlink")
    repo, directory = Path(repo).resolve(), Path(directory).resolve()
    m = read_json(directory / "manifest.json")
    if m.get("release_type") != TYPE or m.get("schema") != 1:
        raise ValueError("Not a frozen-model research inference release")
    certificate = m.get("certification", {})
    if not allow_pending and (
        certificate.get("status") != "passed"
        or certificate.get("contract") != TYPE
        or certificate.get("checks", {}).get("exact_replay") is not True
        or certificate.get("checks", {}).get("models_verified") != len(MODEL_NAMES)
    ):
        raise ValueError("Inference release not exact-replay certified")
    start, prediction, cutoff, created = map(
        utc_timestamp,
        [
            m["forecast_build_started_at"],
            m["prediction_at"],
            m["feature_data_cutoff"],
            m["created_at"],
        ],
    )
    if not cutoff <= prediction or not start <= prediction <= created <= utc_timestamp(
        datetime.now(UTC)
    ):
        raise ValueError("Invalid inference build/cutoff timestamps")
    if m["runtime"] != {**runtime_versions(repo)}:
        # Python patch builds are diagnostic; the validated minor/packages are mandatory.
        current = runtime_versions(repo)
        if (
            m["runtime"]["python_minor"] != current["python_minor"]
            or m["runtime"]["packages"] != current["packages"]
        ):
            raise ValueError("Inference runtime mismatch")
    if set(m["source_sha256"]) != set(CODE) or any(
        sha256(repo / p) != digest for p, digest in m["source_sha256"].items()
    ):
        raise ValueError("Inference source/code mismatch")
    if set(m["files"]) != FILES or {p.name for p in directory.iterdir()} != FILES | {
        "manifest.json",
        "selection.json",
    }:
        raise ValueError("Incomplete or unexpected inference artifact set")
    for name, entry in m["files"].items():
        p = checked_path(directory, name)
        if (
            (directory / name).is_symlink()
            or p.stat().st_size != entry["bytes"]
            or sha256(p) != entry["sha256"]
        ):
            raise ValueError(f"Inference integrity mismatch: {name}")
    parent = checked_path(repo, m["model_parent"]["path"])
    if sha256(parent / "manifest.json") != m["model_parent"]["manifest_sha256"]:
        raise ValueError("Parent model release integrity mismatch")
    pm = validate_manifest(parent, repo)
    if pm["release_id"] != m["model_parent"]["release_id"] or set(m["models"]) != set(
        MODEL_NAMES
    ):
        raise ValueError("Incorrect model parent/market set")
    training_times = set()
    for market in MODEL_NAMES:
        entry = m["models"][market]
        path = parent / "data" / f"model_{market}.joblib"
        digest = sha256(path)
        if (
            digest != entry["sha256"]
            or digest != pm["files"][f"data/model_{market}.joblib"]["sha256"]
        ):
            raise ValueError("Frozen model artifact changed")
        bundle = joblib.load(path)
        trained, trained_cutoff = map(
            utc_timestamp, [bundle["training_as_of"], bundle["training_cutoff"]]
        )
        cfg = {c.get("model_name", key): c for key, c in MODEL_CONFIG.items()}[market]
        if (
            bundle["release_id"] != pm["release_id"]
            or entry["training_as_of"] != bundle["training_as_of"]
            or entry["training_cutoff"] != bundle["training_cutoff"]
        ):
            raise ValueError("Frozen model identity/training provenance mismatch")
        if not trained_cutoff < trained <= prediction or not trained_cutoff < cutoff:
            raise ValueError("Frozen model contains unavailable training information")
        if (
            bundle["feature_timing_version"] != "stage1a"
            or bundle["features"] != cfg["features"]
            or bundle["positions"] != cfg["positions"]
            or not np.isfinite(bundle["resid_std"])
            or bundle["resid_std"] <= 0
        ):
            raise ValueError("Frozen model schema incompatible")
        training_times.add(trained.isoformat())
    if len(training_times) != 1:
        raise ValueError("Parent models were not one coordinated training run")
    sources = read_json(directory / "sources.json")
    if not sources or any(
        utc_timestamp(s["retrieved_at"]) > prediction
        or len(s["sha256"]) != 64
        or not s["url"].startswith("https://")
        for s in sources
    ):
        raise ValueError("Invalid/future source provenance")
    f, s, slate, picks = [
        pd.read_parquet(directory / p)
        for p in [
            "features.parquet",
            "schedule.parquet",
            "slate.parquet",
            "top_picks.parquet",
        ]
    ]
    if (
        f.duplicated(["player_id", "season", "week"]).any()
        or ((f.season >= 2026) & ((f.season > 2026) | (f.week >= 11))).any()
    ):
        raise ValueError("Duplicate history or sealed Week 11 outcomes")
    if (
        f.completed_at.isna().any()
        or not pd.to_datetime(f.completed_at, utc=True).lt(cutoff).all()
    ):
        raise ValueError("History includes unavailable observations")
    # Future fixture rows carry metadata only; scores/results cannot cross the seal.
    future = s[s.season.eq(2026) & s.week.ge(11)]
    if future[["home_score", "away_score"]].notna().any().any():
        raise ValueError("Sealed fixture outcomes in inference input")
    eligibility = read_json(directory / "eligibility.json")
    records = eligibility_map(eligibility, prediction)
    qb = read_json(directory / "qb_starters.json")
    if utc_timestamp(qb["as_of"]) > prediction:
        raise ValueError("Future starter evidence")
    state = candidate_state(f, s, prediction, cutoff, qb["starters"])
    roster = pd.read_csv(directory / "roster_evidence.csv")
    roster_source = next(
        (item for item in sources if item.get("source_id") == "roster"), None
    )
    if roster_source is None:
        raise ValueError("Missing original roster provenance")
    expected_eligibility = derive_eligibility(
        state, roster, s, prediction, roster_source
    )
    if expected_eligibility != eligibility:
        raise ValueError("Eligibility decisions differ from versioned source replay")
    required = set(state.player_id)
    if required != set(records):
        raise ValueError("Incomplete eligibility population")
    if (
        slate.empty
        or picks.empty
        or not slate.release_id.eq(m["release_id"]).all()
        or not picks.release_id.eq(m["release_id"]).all()
    ):
        raise ValueError("Empty or mixed inference forecasts")
    if (
        slate.duplicated(["player_id", "market", "game_id"]).any()
        or not np.isfinite(slate.projection).all()
        or set(slate.market) != set(MARKETS.values())
    ):
        raise ValueError("Invalid forecast population/markets")
    if (
        not set(MARKETS.values())
        <= set(slate[slate.projection_status.eq("complete")].market)
        or not picks.projection_status.eq("complete").all()
    ):
        raise ValueError("Missing complete markets or scenario-only Top Picks")
    if (
        not pd.to_datetime(slate.prediction_at, utc=True).eq(prediction).all()
        or not pd.to_datetime(slate.completed_before, utc=True).eq(cutoff).all()
        or not pd.to_datetime(slate.last_completed_game_at, utc=True).lt(cutoff).all()
    ):
        raise ValueError("Inconsistent forecast/history timestamps")
    week, games = get_upcoming_week(s, prediction)
    games = games[games.kickoff_at.gt(prediction + pd.Timedelta(minutes=60))]
    fixture_identity = {
        "season": int(games.season.iloc[0]),
        "week": int(week),
        "game_ids": sorted(games.game_id.tolist()),
    }
    if (
        m["fixture_slate"] != fixture_identity
        or fixture_identity["season"] != 2026
        or week != 11
    ):
        raise ValueError("Incorrect Week 11 fixture slate identity")
    times = games.set_index("game_id").kickoff_at
    if set(m["game_kickoffs"]) != set(slate.game_id) or not set(slate.game_id) <= set(
        times.index
    ):
        raise ValueError("Incorrect inference fixture coverage")
    for row in slate.itertuples():
        e = records.get(row.player_id)
        game = games[games.game_id.eq(row.game_id)].iloc[0]
        if (
            e is None
            or e["status"] != "eligible"
            or e["team"] != row.team
            or {row.team, row.opponent} != {game.home_team, game.away_team}
        ):
            raise ValueError("Unresolved or conflicting forecast eligibility")
        if utc_timestamp(m["game_kickoffs"][row.game_id]) != utc_timestamp(
            times[row.game_id]
        ):
            raise ValueError("Incorrect fixture kickoff")
    if replay:
        expected = build_inference(
            f,
            s,
            prediction,
            cutoff,
            qb["starters"],
            qb["as_of"],
            eligibility,
            parent / "data",
        )
        expected["release_id"] = m["release_id"]
        keys = ["market", "player_id", "game_id"]
        pd.testing.assert_frame_equal(
            expected.sort_values(keys).reset_index(drop=True),
            slate.sort_values(keys).reset_index(drop=True),
            check_dtype=False,
            check_exact=True,
        )
        expected_picks = compute_top_picks(expected, side_filter="Over")
        pd.testing.assert_frame_equal(
            expected_picks.sort_values(keys).reset_index(drop=True),
            picks.sort_values(keys).reset_index(drop=True),
            check_dtype=False,
            check_exact=True,
        )
    return {
        "forecast_rows": len(slate),
        "complete_rows": int(slate.projection_status.eq("complete").sum()),
        "fixtures": int(slate.game_id.nunique()),
        "top_picks": len(picks),
        "models_verified": len(MODEL_NAMES),
        "exact_replay": replay,
        "eligibility_counts": pd.Series([e["status"] for e in records.values()])
        .value_counts()
        .to_dict(),
    }


def resolve_research_release(repo, pointer=None):
    repo = Path(repo).resolve()
    default = resolve_release(
        repo
    )  # Original training-release validation stays mandatory.
    name = (
        pointer
        or os.environ.get("NFL_RESEARCH_INFERENCE_POINTER")
        or "research_active_inference.json"
    )
    path = checked_path(repo, name)
    if not path.exists():
        if pointer or os.environ.get("NFL_RESEARCH_INFERENCE_POINTER"):
            raise ValueError("Requested research inference pointer missing")
        return default
    p = read_json(path)
    directory = checked_path(repo, p["path"])
    if sha256(directory / "manifest.json") != p["manifest_sha256"]:
        raise ValueError("Inference pointer/manifest mismatch")
    validate_inference(directory, repo)
    m = read_json(directory / "manifest.json")
    if m["release_id"] != p["release_id"]:
        raise ValueError("Inference pointer identity mismatch")
    return directory, {
        **m,
        "built_at": m["created_at"],
        "feature_timing_version": "stage1a",
    }
