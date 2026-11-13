"""Independent provenance contract; frozen Stage 1B validation is never relaxed."""

import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from stage1b.data import MARKETS
from stage1b.artifacts import (
    digest,
    runtime,
    validate as validate_baseline,
    sources as base_sources,
)


def source_hashes(root):
    root = Path(root).resolve()
    paths = [
        *base_sources(root),
        *root.glob("stage1b1/*.py"),
        root / "stage1b1/protocol.json",
    ]
    return {str(p.relative_to(root)): digest(p) for p in sorted(set(paths))}


def validate(directory, root):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    m = json.loads((directory / "manifest.json").read_text())
    if m.get("status") != "passed" or m.get("final_period_sealed") is not True:
        raise ValueError("Experiment not validated/sealed")
    if m["source_hashes"] != source_hashes(root):
        raise ValueError("Stage 1B.1 source/config mismatch")
    if m["runtime"] != runtime(root):
        raise ValueError("Stage 1B.1 runtime mismatch")
    base = root / m["baseline_path"]
    validate_baseline(base, root)
    if digest(base / "manifest.json") != m["baseline_manifest_sha256"]:
        raise ValueError("Frozen baseline changed")
    source = (root / m["input_path"]).resolve()
    if root not in source.parents or digest(source) != m["input_sha256"]:
        raise ValueError("Input snapshot changed")
    actual = {
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if actual != set(m["files"]):
        raise ValueError("Incomplete/unexpected experiment files")
    for name, h in m["files"].items():
        raw = directory / name
        p = raw.resolve()
        if raw.is_symlink() or directory not in p.parents or digest(p) != h:
            raise ValueError("Payload integrity mismatch")
    return m


def validate_results(directory, root):
    directory, root = Path(directory), Path(root)
    m = validate(directory, root)
    f = pd.read_parquet(directory / "forecasts.parquet")
    p = pd.read_parquet(directory / "probes.parquet")
    config = json.loads((directory / "protocol.json").read_text())
    if config != json.loads((root / "stage1b1/protocol.json").read_text()):
        raise ValueError("Archived protocol differs from frozen source")
    base = root / m["baseline_path"]
    old = pd.read_parquet(base / "forecasts.parquet")
    if f.row_id.duplicated().any() or set(f.row_id) != set(old.row_id):
        raise ValueError("Benchmark population changed")
    pair = f[["row_id", "y"]].merge(
        old[["row_id", "y"]],
        on="row_id",
        suffixes=("_new", "_old"),
        validate="one_to_one",
    )
    if not pair.y_new.eq(pair.y_old).all():
        raise ValueError("Benchmark outcomes changed")
    reference = f.set_index("row_id").sort_index()
    original = old.set_index("row_id").sort_index()
    if not np.allclose(
        reference.stage1b_projection, original.projection, rtol=0, atol=1e-12
    ):
        raise ValueError("Frozen point comparator changed")
    for key in [
        "season",
        "week",
        "prediction_at",
        "history_available_at",
        "completed_at",
    ]:
        if not reference[key].eq(original[key]).all():
            raise ValueError("Frozen comparator chronology changed")
    if (f.prediction_at >= pd.Timestamp(config["final_start"])).any() or (
        (f.season == 2026) & (f.week >= 11)
    ).any():
        raise ValueError("Final evaluation period unsealed")
    if not (
        (f.history_available_at < f.prediction_at) & (f.prediction_at < f.completed_at)
    ).all():
        raise ValueError("Invalid forecast chronology")
    if (
        not np.isfinite(f[["projection", "y", "lower90", "upper90", "interval_score"]])
        .all()
        .all()
        or f.lower90.gt(f.upper90).any()
    ):
        raise ValueError("Invalid predictions/intervals")
    if (
        not p.probability.between(0, 1).all()
        or not np.isfinite(p[["probability", "brier", "log_loss"]]).all().all()
    ):
        raise ValueError("Invalid probability scores")
    if not p.groupby("row_id").size().eq(6).all() or set(p.row_id) != set(f.row_id):
        raise ValueError("Incomplete paired probes")
    expected = {
        f"{market}-{year}.joblib"
        for market in MARKETS
        for year in config["evaluation_seasons"]
    }
    if {p.name for p in (directory / "models").glob("*.joblib")} != expected:
        raise ValueError("Missing/unexpected market-season model")
    if len(f) != m["n_player_market_games"]:
        raise ValueError("Manifest row count mismatch")
    if set(p.version) != {"stage1b", "stage1b1"} or set(p.probe_multiplier) != set(
        config["probe_multipliers"]
    ):
        raise ValueError("Unexpected probe versions/thresholds")
    if p.duplicated(["row_id", "version", "probe_multiplier"]).any():
        raise ValueError("Duplicated pricing probe")
    joined = p.merge(f[["row_id", "y"]], on="row_id", validate="many_to_one")
    if not joined.event.eq(joined.y > joined.line).all():
        raise ValueError("Incorrect pricing-probe outcome")
    old_probes = pd.read_parquet(base / "probes.parquet")
    old_probes = old_probes[old_probes.version.eq("selected_stage1b")]
    comparator = p[p.version.eq("stage1b")].merge(
        old_probes,
        on=["row_id", "probe_multiplier"],
        suffixes=("_new", "_old"),
        validate="one_to_one",
    )
    if len(comparator) != len(f) * 3 or not np.allclose(
        comparator.probability_new, comparator.probability_old, rtol=0, atol=1e-12
    ):
        raise ValueError("Frozen probability comparator changed")
    for (market, year), g in f.groupby(["market", "season"]):
        b = joblib.load(directory / "models" / f"{market}-{year}.joblib")
        if not (
            pd.Timestamp(b["max_training_available_at"])
            < pd.Timestamp(b["information_available_at"])
            < g.prediction_at.min()
        ):
            raise ValueError("Future information in model")
    if m["genuine_quotes"] != 0 or m["betting_profit"] is not None:
        raise ValueError("Unverified genuine betting claim")
    return {
        "player_market_games": len(f),
        "models": len(list((directory / "models").glob("*.joblib"))),
        "final_sealed": True,
    }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("directory", type=Path)
    a = p.parse_args()
    print(
        json.dumps(validate_results(a.directory, Path(__file__).resolve().parents[1]))
    )
