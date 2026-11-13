"""Release integrity and one-pointer selection. This module never trains or deploys."""

import fcntl
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import tempfile

MODEL_NAMES = [
    "passing_yards",
    "passing_attempts",
    "completions",
    "rushing_yards",
    "rushing_attempts",
    "qb_rushing_yards",
    "qb_rushing_attempts",
    "receiving_yards",
    "receptions",
]
DATA_FILES = [
    "weekly_player_data.parquet",
    "player_features.parquet",
    "slate.parquet",
    "top_picks.parquet",
] + [f"model_{n}.joblib" for n in MODEL_NAMES]
INPUT_FILES = ["inputs/schedule.parquet", "inputs/qb_starters.json"]
SOURCE_FILES = [
    "app.py",
    "pricing.py",
    "betting_engine.py",
    "ledger.py",
    "odds_utils.py",
    "performance.py",
    "release_utils.py",
    "release_runtime.json",
    "requirements.txt",
    "requirements-production.lock",
    "scripts/update_data.py",
    "scripts/build_features.py",
    "scripts/forecast_features.py",
    "scripts/train_all_markets.py",
    "scripts/build_slate.py",
    "scripts/prepare_release.py",
    "scripts/validate_release.py",
    "scripts/activate_release.py",
]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def runtime_versions(repo):
    pins = {}
    for line in (Path(repo) / "requirements-production.lock").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, expected = line.split("==")
            installed = importlib.metadata.version(name)
            if installed != expected:
                raise ValueError(
                    f"Runtime package mismatch: {name}: expected {expected}, found {installed}"
                )
            pins[name] = installed
    expected_python = read_json(Path(repo) / "release_runtime.json")["python"]
    if platform.python_version_tuple()[:2] != tuple(expected_python.split(".")):
        raise ValueError(
            f"Release requires Python {expected_python}; found {platform.python_version()}"
        )
    return {
        "python_minor": expected_python,
        "python_build": platform.python_version(),
        "packages": pins,
    }


def checked_path(repo, relative):
    repo = Path(repo).resolve()
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("Release paths must be relative to the repository")
    path = (repo / relative).resolve()
    if path == repo or repo not in path.parents:
        raise ValueError("Release path escapes repository")
    return path


def validate_manifest(
    directory, repo, check_runtime=True, check_source=True, allow_pending=False
):
    """Fast startup check before any artifact is loaded. Raises on every mismatch."""
    repo = Path(repo).resolve()
    directory = Path(directory).resolve()
    manifest = read_json(directory / "manifest.json")
    if manifest.get("schema_version") != 1 or not manifest.get("release_id"):
        raise ValueError("Unsupported or incomplete release manifest")
    if not allow_pending and manifest.get("validation_status") != "passed":
        raise ValueError("Release has not passed validation")
    if datetime.fromisoformat(manifest["built_at"]) > datetime.now(timezone.utc):
        raise ValueError("Release build timestamp is in the future")
    expected = {f"data/{name}" for name in DATA_FILES} | set(INPUT_FILES)
    if set(manifest.get("files", {})) != expected:
        raise ValueError(
            "Release manifest must contain exactly the complete artifact set"
        )
    actual = {
        str(p.relative_to(directory))
        for p in (directory / "data").iterdir()
        if p.is_file()
    }
    if actual != {f"data/{name}" for name in DATA_FILES}:
        raise ValueError("Missing or unexpected release data files")
    for relative, entry in manifest["files"].items():
        raw_path = directory / relative
        if raw_path.is_symlink() or raw_path.parent.is_symlink():
            raise ValueError(f"Release must contain regular files: {relative}")
        path = checked_path(directory, relative)
        if (
            path.is_symlink()
            or path.stat().st_size != entry["bytes"]
            or sha256(path) != entry["sha256"]
        ):
            raise ValueError(f"Release integrity mismatch: {relative}")
    if check_source:
        if set(manifest.get("source_sha256", {})) != set(SOURCE_FILES):
            raise ValueError("Incomplete source provenance")
        for name in SOURCE_FILES:
            if sha256(repo / name) != manifest["source_sha256"][name]:
                raise ValueError(f"Release/code mismatch: {name}; rebuild the release")
    if check_runtime:
        current = runtime_versions(repo)
        if (
            current["python_minor"] != manifest["runtime"]["python_minor"]
            or current["packages"] != manifest["runtime"]["packages"]
        ):
            raise ValueError("Release/runtime mismatch")
    return manifest


def resolve_release(repo):
    """Resolve once per app rerun, preserving a coherent bundle during pointer changes."""
    repo = Path(repo).resolve()
    pointer = repo / "active_release.json"
    if not pointer.exists():
        return (
            repo / "data",
            None,
        )  # Explicit, readable legacy fallback before first cutover.
    selected = read_json(pointer)
    directory = checked_path(repo, selected["path"])
    if sha256(directory / "manifest.json") != selected["manifest_sha256"]:
        raise ValueError("Release pointer/manifest mismatch")
    manifest = validate_manifest(directory, repo)
    if manifest["release_id"] != selected["release_id"]:
        raise ValueError("Release pointer ID mismatch")
    return directory / "data", manifest


def _select_release_locked(repo, relative, expected_current):
    """Operator-only pointer switch; caller must have approval. Never called by builds/CI."""
    repo = Path(repo).resolve()
    pointer = repo / "active_release.json"
    old = read_json(pointer) if pointer.exists() else None
    actual = old["release_id"] if old else "legacy"
    if actual != expected_current:
        raise ValueError(
            f"Active release changed: expected {expected_current}, found {actual}"
        )
    directory = checked_path(repo, relative)
    manifest = validate_manifest(directory, repo)
    if datetime.now(timezone.utc) >= datetime.fromisoformat(
        manifest["activate_before"]
    ):
        raise ValueError("Candidate is stale: regenerate before activation")
    selected = {
        "release_id": manifest["release_id"],
        "path": str(directory.relative_to(repo)),
        "manifest_sha256": sha256(directory / "manifest.json"),
        "previous": old,
        "legacy_data_sha256": manifest.get("legacy_data_sha256", {}),
    }
    fd, tmp = tempfile.mkstemp(prefix=".release-pointer-", dir=repo)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(selected, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Only this small file changes. Existing version directories are immutable.
        os.replace(tmp, pointer)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return selected


def resolve_data_directory(repo):
    return resolve_release(repo)[0]


def select_release(repo, relative, expected_current):
    """Guarded local switch. Builds and scheduled jobs never call this on production."""
    repo = Path(repo).resolve()
    with (repo / ".release-switch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _select_release_locked(repo, relative, expected_current)


def rollback_release(repo, expected_current):
    """Operator-only, guarded forecast rollback. Never changes code or bet storage."""
    repo = Path(repo).resolve()
    pointer = repo / "active_release.json"
    with (repo / ".release-switch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = read_json(pointer)
        if current["release_id"] != expected_current:
            raise ValueError("Active release changed; rollback refused")
        previous = current.get("previous")
        if previous:
            directory = checked_path(repo, previous["path"])
            if sha256(directory / "manifest.json") != previous["manifest_sha256"]:
                raise ValueError("Previous release manifest changed")
            validate_manifest(directory, repo)
            fd, tmp = tempfile.mkstemp(prefix=".release-pointer-", dir=repo)
            try:
                with os.fdopen(fd, "w") as stream:
                    json.dump(previous, stream, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(tmp, pointer)
            finally:
                Path(tmp).unlink(missing_ok=True)
        else:
            hashes = current.get("legacy_data_sha256", {})
            if set(hashes) != set(DATA_FILES):
                raise ValueError("No verified legacy fallback is recorded")
            for name, digest in hashes.items():
                if sha256(repo / "data" / name) != digest:
                    raise ValueError(
                        "Legacy fallback changed; restore a complete known-good Git release instead"
                    )
            pointer.unlink()
        return previous
