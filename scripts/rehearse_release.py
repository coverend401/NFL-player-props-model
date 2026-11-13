"""Fault-injection and rollback rehearsal in temporary copies. Never deploys."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import joblib
import pandas as pd
from release_utils import (
    DATA_FILES,
    SOURCE_FILES,
    sha256,
    read_json,
    validate_manifest,
    select_release,
    resolve_release,
    rollback_release,
)
from scripts.validate_release import validate_bundle


def rewrite_hash(directory, relative):
    path = directory / relative
    m = read_json(directory / "manifest.json")
    m["files"][relative] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    (directory / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")


def rehearse(directory):
    directory = Path(directory).resolve()
    manifest = validate_manifest(directory, ROOT)
    validate_bundle(directory)
    results = {}
    with tempfile.TemporaryDirectory(prefix="nfl-release-rehearsal-") as tmp:
        tmp = Path(tmp)
        for case in [
            "missing_model",
            "future_training",
            "wrong_release_id",
            "incorrect_projection",
        ]:
            copy = tmp / case
            shutil.copytree(directory, copy)
            model_path = copy / "data/model_passing_yards.joblib"
            if case == "missing_model":
                model_path.unlink()
            elif case in ["future_training", "wrong_release_id"]:
                b = joblib.load(model_path)
                if case == "future_training":
                    b["training_cutoff"] = (
                        pd.Timestamp(manifest["built_at"]) + pd.Timedelta(days=1)
                    ).isoformat()
                else:
                    b["release_id"] = "wrong-cohort"
                joblib.dump(b, model_path)
                rewrite_hash(copy, "data/model_passing_yards.joblib")
            else:
                path = copy / "data/slate.parquet"
                s = pd.read_parquet(path)
                s.loc[0, "projection"] += 100
                s.to_parquet(path, index=False)
                rewrite_hash(copy, "data/slate.parquet")
            try:
                validate_bundle(copy)
            except (ValueError, AssertionError) as error:
                expected = {
                    "missing_model": "Missing or unexpected",
                    "future_training": "Future/stale",
                    "wrong_release_id": "Mixed or legacy",
                    "incorrect_projection": "DataFrame.iloc",
                }[case]
                if expected not in str(error):
                    raise AssertionError(
                        f"{case}: rejected for the wrong reason: {error}"
                    ) from error
                results[case] = {"rejected": True, "reason": str(error).splitlines()[0]}
            else:
                raise AssertionError(f"Unsafe candidate accepted: {case}")
        root = tmp / "rollback"
        root.mkdir()
        for name in SOURCE_FILES:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, root / name)
        (root / "data").mkdir()
        for name in DATA_FILES:
            shutil.copy2(ROOT / "data" / name, root / "data" / name)
        # This is a synthetic marker, never a copy of live betting history.
        ledger = root / "ledger_local.db"
        ledger.write_bytes(b"rollback rehearsal bet marker")
        before = sha256(ledger)
        target = root / "release_candidates" / directory.name
        shutil.copytree(directory, target)
        if datetime.now(timezone.utc) >= datetime.fromisoformat(
            manifest["activate_before"]
        ):
            try:
                select_release(root, str(target.relative_to(root)), "legacy")
            except ValueError as error:
                if "stale" not in str(error):
                    raise
                results["expired_activation"] = {"rejected": True}
            else:
                raise AssertionError("Expired candidate activated")
        else:
            select_release(root, str(target.relative_to(root)), "legacy")
            if resolve_release(root)[1]["release_id"] != manifest["release_id"]:
                raise AssertionError("Wrong selection")
            rollback_release(root, manifest["release_id"])
            if resolve_release(root) != (root / "data", None):
                raise AssertionError("Rollback failed")
            if sha256(ledger) != before:
                raise AssertionError("Rollback changed bet storage")
            results["rollback"] = {
                "restored_verified_legacy": True,
                "bet_marker_unchanged": True,
            }
    return {
        "release_id": manifest["release_id"],
        "manifest_sha256": sha256(directory / "manifest.json"),
        "checks": results,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", nargs="?", type=Path)
    p.add_argument("--all-current-candidates", action="store_true")
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    directories = [args.directory] if args.directory else []
    if args.all_current_candidates:
        directories = []
        for manifest_path in sorted(
            (ROOT / "release_candidates").glob("*/manifest.json")
        ):
            if manifest_path.parent.name.startswith("."):
                continue
            m = validate_manifest(
                manifest_path.parent, ROOT, check_source=False, check_runtime=False
            )
            if all(
                sha256(ROOT / name) == digest
                for name, digest in m["source_sha256"].items()
            ):
                directories.append(manifest_path.parent)
    if not directories:
        p.error("No matching current-source candidate supplied")
    results = [rehearse(d) for d in directories]
    text = json.dumps(results, indent=2) + "\n"
    if args.report:
        args.report.write_text(text)
    print(text)
