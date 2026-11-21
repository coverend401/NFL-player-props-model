"""Operational frozen-model candidate builder from admitted, cutoff-filtered inputs.

No downloader, fitting, production pointer, odds provider or deployment path.
"""

import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import joblib
import pandas as pd

from release_utils import MODEL_NAMES, resolve_release, runtime_versions, sha256
from research_platform.inference_builder import (
    build_inference,
    candidate_state,
    derive_eligibility,
)
from research_platform.slate import model_candidates, top_two
from scripts.build_slate import compute_top_picks, get_upcoming_week
from weekly_learning.contract import CODE, FILES, TYPE
from weekly_learning.contract import validate_operational as validate_inference
from weekly_learning.game_script import build_game_research


def build_prepared(saved, output, admission_path):
    saved, output = Path(saved).resolve(), Path(output).resolve()
    if (
        not output.is_relative_to(ROOT / "research_inference_releases")
        or output.exists()
    ):
        raise ValueError("Use a unique immutable research-only output directory")
    started = datetime.now(UTC).isoformat()
    data, parent = resolve_release(ROOT)
    parent_dir = data.parent
    generation = json.loads((saved / "generation.json").read_text())
    cutoff = generation["completed_before"]
    features = pd.read_parquet(saved / "features.filtered.parquet").drop(
        columns="release_id", errors="ignore"
    )
    schedule = pd.read_parquet(saved / "schedule.filtered.parquet")
    sources = [json.loads((saved.parent / "source-gate.json").read_text())]
    sources[0]["source_id"] = "player_stats"
    for item in json.loads((saved.parent / "required-source-report.json").read_text()):
        sources.append({**item, "source_id": item["name"]})
    roster_source = {
        **json.loads((saved / "roster_source.json").read_text()),
        "source_id": "roster",
    }
    sources.append(roster_source)
    prediction = datetime.now(UTC).isoformat()
    state = candidate_state(
        features, schedule, prediction, cutoff, generation["qb_starters"]
    )
    # Materialise identities/status only for candidate IDs, never any outcome.
    roster = pd.read_parquet(
        saved / "roster_2026.quarantined.parquet",
        columns=["gsis_id", "team", "status", "season", "week"],
        filters=[("gsis_id", "in", state.player_id.tolist())],
    )
    eligibility = derive_eligibility(state, roster, schedule, prediction, roster_source)
    rid = output.name
    slate = build_inference(
        features,
        schedule,
        prediction,
        cutoff,
        generation["qb_starters"],
        generation["prediction_at"],
        eligibility,
        data,
    )
    slate["release_id"] = rid
    picks = compute_top_picks(slate, side_filter="Over")
    with tempfile.TemporaryDirectory(prefix="frozen-research-build-") as tmp:
        directory = Path(tmp)
        shutil.copyfile(admission_path, directory / "admission.json")
        for name, frame in [
            ("features.parquet", features),
            ("schedule.parquet", schedule),
            ("slate.parquet", slate),
            ("top_picks.parquet", picks),
        ]:
            frame.to_parquet(directory / name, index=False)
        roster.to_csv(directory / "roster_evidence.csv", index=False)
        for name, value in [
            ("eligibility.json", eligibility),
            ("sources.json", sources),
            (
                "qb_starters.json",
                {
                    "as_of": generation["prediction_at"],
                    "starters": generation["qb_starters"],
                },
            ),
        ]:
            (directory / name).write_text(json.dumps(value, indent=2) + "\n")
        week, games = get_upcoming_week(schedule, prediction)
        games = games[
            games.kickoff_at.gt(pd.Timestamp(prediction) + pd.Timedelta(minutes=60))
        ]
        model_meta = {}
        for market in MODEL_NAMES:
            path = data / f"model_{market}.joblib"
            b = joblib.load(path)
            model_meta[market] = {
                "sha256": sha256(path),
                "training_as_of": b["training_as_of"],
                "training_cutoff": b["training_cutoff"],
            }
        identity = {
            "season": int(games.season.iloc[0]),
            "week": int(week),
            "game_ids": sorted(games.game_id.tolist()),
        }
        info = {
            "release_id": rid,
            "prediction_at": prediction,
            "feature_data_cutoff": cutoff,
            "fixture_slate": identity,
            "game_kickoffs": {
                gid: games.set_index("game_id").loc[gid, "kickoff_at"].isoformat()
                for gid in slate.game_id.unique()
            },
        }
        groups = top_two(
            [],
            model_candidates(slate, info, pd.Timestamp(prediction).to_pydatetime()),
            info,
        )
        pd.DataFrame([row for rows in groups.values() for row in rows]).to_parquet(
            directory / "top_two.parquet", index=False
        )
        (directory / "game_script.json").write_text(
            json.dumps(
                build_game_research(features, schedule, info), indent=2, allow_nan=False
            )
            + "\n"
        )
        m = {
            "schema": 1,
            "release_type": TYPE,
            "release_id": rid,
            "model_parent": {
                "path": str(parent_dir.relative_to(ROOT)),
                "release_id": parent["release_id"],
                "manifest_sha256": sha256(parent_dir / "manifest.json"),
            },
            "models": model_meta,
            "forecast_build_started_at": started,
            "prediction_at": prediction,
            "feature_data_cutoff": cutoff,
            "created_at": datetime.now(UTC).isoformat(),
            "runtime": runtime_versions(ROOT),
            "source_sha256": {p: sha256(ROOT / p) for p in CODE},
            "files": {
                p: {
                    "sha256": sha256(directory / p),
                    "bytes": (directory / p).stat().st_size,
                }
                for p in sorted(FILES)
            },
            "fixture_slate": {
                "season": int(games.season.iloc[0]),
                "week": int(week),
                "game_ids": sorted(games.game_id.tolist()),
            },
            "game_kickoffs": {
                gid: games.set_index("game_id").loc[gid, "kickoff_at"].isoformat()
                for gid in sorted(slate.game_id.unique())
            },
            "certification": {"status": "pending", "contract": TYPE},
        }
        (directory / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
        (directory / "selection.json").write_text("{}\n")
        report = validate_inference(directory, ROOT, replay=True, allow_pending=True)
        m["certification"] = {
            "status": "passed",
            "contract": TYPE,
            "checks": report,
            "certified_at": datetime.now(UTC).isoformat(),
        }
        (directory / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
        (directory / "selection.json").write_text(
            json.dumps(
                {
                    "release_id": rid,
                    "path": str(output.relative_to(ROOT)),
                    "manifest_sha256": sha256(directory / "manifest.json"),
                },
                indent=2,
            )
            + "\n"
        )
        output.parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="." + output.name + "-", dir=output.parent
        ) as stage:
            staged = Path(stage) / "candidate"
            shutil.copytree(directory, staged)
            validate_inference(staged, ROOT)
            staged.rename(output)
    print(
        json.dumps(
            {
                "candidate": str(output),
                "selection_pointer": str((output / "selection.json").relative_to(ROOT)),
                **report,
            },
            indent=2,
        )
    )
    return report
