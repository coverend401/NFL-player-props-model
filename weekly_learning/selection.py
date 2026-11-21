"""Independent operational research selection. Protected v1 entrypoint stays intact."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research_platform.inference_release import resolve_research_release

from .contract import TYPE, validate_operational
from .store import ROOT, encoded, sha

POINTER = "weekly_learning_state/selected_research.json"


def resolve_current(repo=ROOT):
    repo = Path(repo).resolve()
    fallback = resolve_research_release(repo)
    path = repo / POINTER
    if not path.exists():
        return fallback
    p = json.loads(path.read_text())
    directory = (repo / p["path"]).resolve()
    directory.relative_to(repo / "research_inference_releases")
    if sha(directory / "manifest.json") != p["manifest_sha256"]:
        raise ValueError("Operational selection integrity mismatch")
    checks = validate_operational(directory, repo)
    m = json.loads((directory / "manifest.json").read_text())
    if m["release_id"] != p["release_id"] or m["release_type"] != TYPE:
        raise ValueError("Operational selection identity mismatch")
    return directory, {
        **m,
        "built_at": m["created_at"],
        "feature_timing_version": "stage1a",
        "operational_checks": checks,
    }


def for_app(slate, release):
    # Explicit archive tests/views are independent of the live operational overlay.
    if (
        os.environ.get("NFL_RESEARCH_INFERENCE_POINTER")
        or not (ROOT / POINTER).exists()
        or release.get("release_type") != "research_frozen_model_inference_v1"
    ):
        return slate, release
    try:
        directory, current = resolve_current()
        if current["release_id"] == release["release_id"]:
            return slate, release
        return pd.read_parquet(directory / "slate.parquet"), current
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        return slate, {
            **release,
            "weekly_selection_warning": "Operational selection failed checks. Last certified baseline retained; expired forecasts are not current opportunities.",
        }


def select(store, path, *, now=None):
    now = pd.Timestamp(now or datetime.now(UTC))
    path = Path(path).resolve()
    path.relative_to(ROOT / "research_inference_releases")
    checks = validate_operational(path, ROOT, replay=True)
    m = json.loads((path / "manifest.json").read_text())
    if not all(
        now < pd.Timestamp(v) - pd.Timedelta(minutes=60)
        for v in m["game_kickoffs"].values()
    ):
        raise ValueError("Candidate activation deadline passed")
    selection = {
        "path": str(path.relative_to(ROOT)),
        "release_id": m["release_id"],
        "manifest_sha256": sha(path / "manifest.json"),
        "selected_at": now.isoformat(),
        "checks": checks,
    }
    pointer = ROOT / POINTER
    previous = (
        json.loads(pointer.read_text())
        if pointer.exists()
        else {"fallback": "research_active_inference.json"}
    )
    with store.transaction():
        store.publish(
            "operational_selections",
            m["release_id"],
            documents={"previous.json": previous, "selection.json": selection},
        )
        store.audit(
            "operational_candidate_selected",
            {
                "release_id": m["release_id"],
                "manifest_sha256": selection["manifest_sha256"],
            },
        )
        temp = pointer.with_name(".selected_research.next.json")
        with temp.open("x") as f:
            f.write(encoded(selection))
        os.replace(temp, pointer)
    return selection


def capture_current(store, *, prepared=None):
    directory, release = prepared or resolve_current()
    from .engine import capture

    if release.get("release_type") != TYPE:
        return capture(store)
    target = store.root / "captures" / release["release_id"]
    if target.exists():
        store.validate(target)
        return target
    now = pd.Timestamp.now(tz="UTC")
    frame = pd.read_parquet(directory / "slate.parquet")
    if not pd.to_datetime(frame.prediction_at, utc=True).le(now).all() or not all(
        now < pd.Timestamp(t) - pd.Timedelta(minutes=60)
        for t in release["game_kickoffs"].values()
    ):
        raise ValueError("Cannot backdate an operational forecast capture")
    meta = {
        "release_id": release["release_id"],
        "frozen_at": now.isoformat(),
        "capture_tier": "genuine_predecision_capture",
        "source_manifest_sha256": sha(directory / "manifest.json"),
        "models": release["models"],
        "game_kickoffs": release["game_kickoffs"],
        "complete_rows": int(frame.projection_status.eq("complete").sum()),
        "source_path": str(directory.relative_to(ROOT)),
    }
    research = json.loads((directory / "game_script.json").read_text())
    lookup = {(g["game_id"], g["team"]): g for g in research["fixtures"]}
    rows = []
    for row in frame[frame.projection_status.eq("complete")].to_dict("records"):
        g = lookup.get((row["game_id"], row["team"]), {})
        rows.append(
            {
                "game_id": row["game_id"],
                "player_id": row["player_id"],
                "market": row["market"],
                "expected_attempts": g.get("pass_attempts_last3"),
                "expected_carries": g.get("carries_last3"),
            }
        )
    with store.transaction():
        return store.publish(
            "captures",
            release["release_id"],
            frames={"experimental_context.parquet": pd.DataFrame(rows)},
            copies={
                "forecasts.parquet": directory / "slate.parquet",
                "top_picks.parquet": directory / "top_picks.parquet",
                "release_manifest.json": directory / "manifest.json",
                "game_script.json": directory / "game_script.json",
            },
            documents={"capture.json": meta},
        )
