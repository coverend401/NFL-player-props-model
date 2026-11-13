"""Immutable experiment provenance, separate from all production releases."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources(root):
    return sorted(
        [
            *Path(root).glob("stage1b/*.py"),
            Path(root) / "stage1b/protocol.json",
            Path(root) / "stage1b_dashboard.py",
            Path(root) / "scripts/forecast_features.py",
            Path(root) / "requirements-production.lock",
        ]
    )


def runtime(root):
    pins = {}
    for line in (Path(root) / "requirements-production.lock").read_text().splitlines():
        if line and not line.startswith("#"):
            name, version = line.split("==")
            installed = importlib.metadata.version(name)
            if installed != version:
                raise ValueError("Experiment runtime mismatch: " + name)
            pins[name] = version
    if platform.python_version_tuple()[:2] != ("3", "14"):
        raise ValueError("Experiments require the production Python 3.14 runtime")
    return {"python": platform.python_version(), "packages": pins}


def validate(directory, root, check_runtime=True):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("status") != "passed" or not manifest.get("final_period_sealed"):
        raise ValueError("Unvalidated or unsealed experiment")
    actual = {
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if actual != set(manifest["files"]):
        raise ValueError("Missing or unexpected experiment artifacts")
    if set(manifest["source_hashes"]) != {
        str(p.relative_to(root)) for p in sources(root)
    }:
        raise ValueError("Incomplete experiment source provenance")
    source = (root / manifest["input_relative_path"]).resolve()
    if root not in source.parents or digest(source) != manifest["input_sha256"]:
        raise ValueError("Experiment input snapshot changed")
    for name, expected in manifest["files"].items():
        p = (directory / name).resolve()
        if directory not in p.parents or p.is_symlink() or digest(p) != expected:
            raise ValueError("Experiment payload mismatch: " + name)
    for name, expected in manifest["source_hashes"].items():
        if digest(root / name) != expected:
            raise ValueError("Experiment source mismatch: " + name)
    if check_runtime and runtime(root) != manifest["runtime"]:
        raise ValueError("Experiment environment changed")
    return manifest


def validate_results(directory):
    """Semantic audit in addition to byte hashes; does not refit/select methods."""
    import pandas as pd
    import numpy as np

    directory = Path(directory)
    protocol = json.loads((directory / "protocol.json").read_text())
    f = pd.read_parquet(directory / "forecasts.parquet")
    p = pd.read_parquet(directory / "probes.parquet")
    if f.row_id.duplicated().any() or f.empty:
        raise ValueError("Duplicate or empty forecast population")
    if (f.prediction_at >= pd.Timestamp(protocol["final_start"])).any():
        raise ValueError("Sealed final outcomes appeared in experiment")
    if f[["history_available_at", "prediction_at", "completed_at"]].isna().any().any():
        raise ValueError("Missing forecast time provenance")
    if not (
        (f.history_available_at < f.prediction_at) & (f.prediction_at < f.completed_at)
    ).all():
        raise ValueError("Invalid historical feature/outcome timing")
    if not np.isfinite(f[["projection", "y", "lower90", "upper90"]]).all().all():
        raise ValueError("Invalid numerical forecast")
    if (
        not np.isfinite(p[["probability", "brier", "log_loss"]]).all().all()
        or not p.probability.between(0, 1).all()
    ):
        raise ValueError("Invalid proper scores")
    if (
        set(p.row_id) != set(f.row_id)
        or not p.line_kind.eq("hypothetical_pregame_halfline_NOT_BOOKMAKER").all()
    ):
        raise ValueError("Probe population/line provenance mismatch")
    if not p.groupby("row_id").size().eq(6).all():
        raise ValueError("Incomplete paired baseline/probe population")
    import joblib

    for (market, year), g in f.groupby(["market", "season"]):
        bundle = joblib.load(directory / "models" / f"{market}-{year}.joblib")
        if not (
            pd.Timestamp(bundle["model_information_cutoff"])
            < pd.Timestamp(bundle["model_fit_available_at"])
            < g.prediction_at.min()
        ):
            raise ValueError("Late model or probability selection")
    betting = json.loads((directory / "betting_status.json").read_text())
    if betting["authentic_quotes"] != 0 or betting["realised_profit"] is not None:
        raise ValueError("Unexpected unverified betting performance claim")
    return {
        "player_market_games": len(f),
        "hypothetical_probes": len(p),
        "final_sealed": True,
    }
