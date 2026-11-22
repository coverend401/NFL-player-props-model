"""Exact, separately certified serving runtime; immutable training runtime retained."""

import importlib.metadata
import platform
from datetime import UTC, datetime
from pathlib import Path

from release_utils import checked_path, read_json, sha256, validate_manifest

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = "week11-certifi-20261120-v1"
DIRECTORY = ROOT / "research_runtime_profiles" / PROFILE_ID
POINTER = ROOT / "research_cloud_active.json"


def pins(path):
    return dict(
        line.strip().split("==")
        for line in Path(path).read_text().splitlines()
        if "==" in line and not line.startswith("#")
    )


def binding_paths():
    from release_utils import SOURCE_FILES

    from .enhanced_engine import CERTIFIED, EXPERIMENT
    from .enhanced_engine import DIRECTORY as SELECTION
    from .inference_release import CODE

    files = {ROOT / p for p in SOURCE_FILES + CODE}
    files.update(
        ROOT / p for p in ["active_release.json", "research_active_inference.json"]
    )
    parent = checked_path(ROOT, read_json(ROOT / "active_release.json")["path"])
    for directory in [parent, CERTIFIED, EXPERIMENT, SELECTION]:
        manifest = read_json(directory / "manifest.json")
        files.add(directory / "manifest.json")
        files.update(directory / p for p in manifest["files"])
        if "source_sha256" in manifest:
            files.update(ROOT / p for p in manifest["source_sha256"])
    files.update(CERTIFIED / p for p in ["selection.json"])
    files.add(ROOT / "docs/season-intelligence-probability-uncertainty.csv")
    files.add(ROOT / "research_platform/enhanced_engine.py")
    files.update(
        ROOT / p
        for p in [
            "research_platform/cloud_runtime.py",
            "research_platform/cloud_inference.py",
            "research_platform/cloud_intelligence.py",
            "research_platform/cloud_selection.py",
            "research_platform/cloud_intelligence_ui.py",
            "scripts/generate_cloud_validators.py",
            "scripts/certify_cloud_runtime.py",
            "research_platform/cloud_dashboard.py",
            "research_platform/enhanced_ui.py",
            "research_platform/r8.py",
            "research_platform/startup_diagnostics.py",
            "research_access.py",
            "research_platform/selection_integrity.py",
        ]
    )
    files.update(
        DIRECTORY / p for p in ["requirements.lock", "baseline_validation.json"]
    )
    return {str(p.relative_to(ROOT)): p for p in files}


def runtime():
    expected = pins(DIRECTORY / "requirements.lock")
    actual = {}
    for name, value in expected.items():
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise ValueError(f"Serving runtime missing package: {name}") from error
        if value != installed:
            raise ValueError(
                f"Serving runtime package mismatch: {name}: expected {value}, found {installed}"
            )
        actual[name] = installed
    if platform.python_version_tuple()[:2] != ("3", "14"):
        raise ValueError("Serving release requires Python 3.14")
    original = pins(ROOT / "requirements-production.lock")
    if (
        set(original) != set(expected)
        or {k for k in original if original[k] != expected[k]} != {"certifi"}
        or original["certifi"] != "2026.10.23"
        or expected["certifi"] != "2026.11.20"
    ):
        raise ValueError("Unapproved serving-runtime substitution")
    return {
        "python_minor": "3.14",
        "python_build": platform.python_version(),
        "packages": actual,
    }


def verify_training_runtime(training, repo):
    if (
        Path(repo).resolve() != ROOT
        or training["python_minor"] != "3.14"
        or training["packages"] != pins(ROOT / "requirements-production.lock")
    ):
        raise ValueError("Original training runtime provenance changed")
    return runtime()


def validate_training_manifest(directory, repo):
    # Only the obsolete serving-runtime comparison is delegated. Every package
    # is checked by runtime(); original source/file/status/time checks still run.
    runtime()
    manifest = validate_manifest(directory, repo, check_runtime=False)
    verify_training_runtime(manifest["runtime"], repo)
    return manifest


def resolve_training_release(repo):
    selected = read_json(Path(repo) / "active_release.json")
    directory = checked_path(repo, selected["path"])
    if sha256(directory / "manifest.json") != selected["manifest_sha256"]:
        raise ValueError("Original parent pointer changed")
    manifest = validate_training_manifest(directory, repo)
    if manifest["release_id"] != selected["release_id"]:
        raise ValueError("Original parent identity changed")
    return directory / "data", manifest


def admit():
    pointer = read_json(POINTER)
    path = checked_path(ROOT, pointer["path"])
    if (
        path != DIRECTORY / "certificate.json"
        or pointer["profile_id"] != PROFILE_ID
        or sha256(path) != pointer["sha256"]
    ):
        raise ValueError("Serving certificate pointer mismatch")
    certificate = read_json(path)
    if (
        certificate["schema"] != 1
        or certificate["status"] != "passed"
        or certificate["profile_id"] != PROFILE_ID
        or certificate["forecast_release"] != "research-week11-frozen-20261120-r2"
    ):
        raise ValueError("Serving runtime is not certified")
    if datetime.fromisoformat(certificate["validated_at"]) > datetime.now(UTC):
        raise ValueError("Future serving certification")
    baseline = read_json(DIRECTORY / "baseline_validation.json")
    from .enhanced_engine import CERTIFIED

    original_manifest = read_json(CERTIFIED / "manifest.json")
    if (
        baseline["schema"] != 1
        or certificate["checks"] != baseline["checks"]
        or certificate["checks"]["inference"]["exact_replay"] is not True
        or certificate["checks"]["intelligence"]["replay"] is not True
        or certificate["checks"]["intelligence"]["promoted"] is not False
        or certificate["permitted_package_change"]
        != {"certifi": {"from": "2026.10.23", "to": "2026.11.20"}}
        or certificate["training_runtime"]
        != read_json(CERTIFIED / "manifest.json")["runtime"]
        or certificate["model_parent"] != original_manifest["model_parent"]
        or certificate["model_lineage"] != original_manifest["models"]
        or certificate["baseline_validation_runtime"] != baseline["runtime"]
        or not datetime.fromisoformat(baseline["validated_at"])
        <= datetime.fromisoformat(certificate["validated_at"])
        or (
            certificate["checks"]["forecasts"],
            certificate["checks"]["top_picks"],
            certificate["checks"]["top2"],
            certificate["checks"]["inference"]["models_verified"],
        )
        != (522, 12, 20, 9)
    ):
        raise ValueError("Serving replay certificate/provenance changed")
    if set(certificate["files"]) != set(binding_paths()):
        raise ValueError("Incomplete serving certificate bindings")
    for name, digest in certificate["files"].items():
        file = checked_path(ROOT, name)
        if (ROOT / name).is_symlink() or sha256(file) != digest:
            raise ValueError("Serving certificate artifact/source mismatch")
    actual = runtime()
    if (
        certificate["serving_runtime"]["python_minor"] != actual["python_minor"]
        or certificate["serving_runtime"]["packages"] != actual["packages"]
    ):
        raise ValueError("Serving certificate runtime mismatch")
    from .cloud_inference import resolve_research_release

    directory, manifest = resolve_research_release(ROOT)
    if manifest["release_id"] != certificate["forecast_release"]:
        raise ValueError("Serving forecast selection changed")
    return directory, {
        **manifest,
        "serving_runtime_profile": PROFILE_ID,
        "serving_runtime": actual,
    }


def preflight():
    try:
        directory, manifest = admit()
        import pandas as pd

        return {
            "status": "PASS",
            "release": manifest["release_id"],
            "serving_runtime_profile": PROFILE_ID,
            "certifi": manifest["serving_runtime"]["packages"]["certifi"],
            "base_forecast_rows": len(pd.read_parquet(directory / "slate.parquet")),
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        from .startup_diagnostics import package_mismatches, safe_failure

        return {
            "status": "FAIL",
            **safe_failure(error),
            "package_mismatches": package_mismatches(DIRECTORY / "requirements.lock"),
        }
