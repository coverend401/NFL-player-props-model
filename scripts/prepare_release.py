"""Build and validate an immutable candidate. Never selects, pushes or deploys it."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import joblib
import pandas as pd
from release_utils import (
    DATA_FILES,
    INPUT_FILES,
    SOURCE_FILES,
    sha256,
    runtime_versions,
)
from scripts.forecast_features import schedule_times
from scripts.validate_release import validate_bundle


def prepare(output, release_id):
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,80}", release_id):
        raise ValueError("Use a simple, unique release ID without slashes")
    output = Path(output).resolve()
    target = output / release_id
    if output == ROOT / "data" or ROOT / "data" in output.parents:
        raise ValueError("Candidate output must be separate from production data")
    if target.exists():
        raise ValueError("Release ID already exists; candidates are immutable")
    runtime = runtime_versions(ROOT)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "2"}
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    started = datetime.now(timezone.utc)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nfl-release-build-") as tmp:
        work = Path(tmp) / "work"
        work.mkdir()
        # No existing model/data, credentials, active pointer or ledger is copied.
        for name in SOURCE_FILES:
            (work / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, work / name)
        env.update(
            NFLREADPY_CACHE="filesystem",
            NFLREADPY_CACHE_DIR=str(Path(tmp) / "source-cache"),
            NFLREADPY_CACHE_DURATION="86400",
            NFL_RELEASE_INPUT_DIR=str(work / "inputs"),
        )
        for script in [
            "update_data.py",
            "build_features.py",
            "train_all_markets.py",
            "build_slate.py",
        ]:
            print("RUNNING", script, flush=True)
            subprocess.run(
                [sys.executable, "-u", "scripts/" + script],
                cwd=work,
                env=env,
                check=True,
            )
        bundle = Path(tmp) / release_id
        bundle.mkdir()
        (bundle / "data").mkdir()
        shutil.copytree(work / "inputs", bundle / "inputs")
        for name in DATA_FILES:
            path = work / "data" / name
            if not path.is_file():
                raise ValueError(f"Fresh build omitted required artifact: {name}")
            if name.endswith(".joblib"):
                value = joblib.load(path)
                value["release_id"] = release_id
                joblib.dump(value, bundle / "data" / name)
            else:
                frame = pd.read_parquet(path)
                frame["release_id"] = release_id
                frame.to_parquet(bundle / "data" / name, index=False)
        slate = pd.read_parquet(bundle / "data/slate.parquet")
        schedule = schedule_times(
            pd.read_parquet(bundle / "inputs/schedule.parquet")
        ).set_index("game_id")
        kickoffs = {
            gid: schedule.loc[gid, "kickoff_at"].isoformat()
            for gid in slate.game_id.unique()
        }
        manifest = {
            "schema_version": 1,
            "release_id": release_id,
            "feature_timing_version": "stage1a",
            "build_started_at": started.isoformat(),
            "built_at": datetime.now(timezone.utc).isoformat(),
            "activate_before": min(kickoffs.values()),
            "game_kickoffs": kickoffs,
            "runtime": runtime,
            "legacy_data_git_commit": subprocess.check_output(
                ["git", "log", "-1", "--format=%H", "--", "data"], cwd=ROOT, text=True
            ).strip(),
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "source_sha256": {name: sha256(work / name) for name in SOURCE_FILES},
            "files": {
                name: {
                    "sha256": sha256(bundle / name),
                    "bytes": (bundle / name).stat().st_size,
                }
                for name in [*[f"data/{n}" for n in DATA_FILES], *INPUT_FILES]
            },
            "legacy_data_sha256": {
                n: sha256(ROOT / "data" / n)
                for n in DATA_FILES
                if (ROOT / "data" / n).is_file()
            },
            "validation_status": "pending",
        }
        path = bundle / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        report = validate_bundle(bundle, allow_pending=True)
        manifest.update(validation_status="passed", checks=report)
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        report = validate_bundle(bundle, app_smoke=True)
        manifest.update(
            checks=report, validated_at=datetime.now(timezone.utc).isoformat()
        )
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        staging = output / ("." + release_id + ".tmp")
        if staging.exists():
            raise ValueError(
                "Abandoned staging folder exists; inspect before removing it"
            )
        shutil.copytree(bundle, staging)
        try:
            validate_bundle(staging)
            staging.rename(target)
        except Exception:
            shutil.rmtree(staging)
            raise
    print(
        json.dumps(
            {
                "candidate": str(target),
                "release_id": release_id,
                "active": False,
                "checks": report,
            },
            indent=2,
        )
    )
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "release_candidates")
    parser.add_argument(
        "--id", default=datetime.now(timezone.utc).strftime("stage1a-%Y%m%dt%H%M%Sz")
    )
    args = parser.parse_args()
    prepare(args.output_dir, args.id)
