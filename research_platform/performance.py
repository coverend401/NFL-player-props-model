"""Read only hash-verified aggregate development metrics. No outcomes or models."""

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = "experiments/stage1b1/improvements-20261113-v1"
PIN = "a8c13933a5254fc207990c77677f6dc99ad925cf6630e72471e6599f85c16eef"


def load(root=ROOT):
    directory = Path(root) / EXPERIMENT
    raw = (directory / "manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != PIN:
        raise ValueError("Frozen performance manifest mismatch")
    m = json.loads(raw)
    if m.get("final_period_sealed") is not True or m.get("status") != "passed":
        raise ValueError("Frozen evaluation governance mismatch")
    result = {}
    for name in ["accuracy.csv", "probability_metrics.csv", "reliability.csv"]:
        p = directory / name
        if (
            p.is_symlink()
            or hashlib.sha256(p.read_bytes()).hexdigest() != m["files"][name]
        ):
            raise ValueError("Frozen aggregate integrity mismatch")
        frame = pd.read_csv(p)
        # Never display any final evaluation tier, even if a later artifact contains it.
        if not set(frame.evaluation_tier) <= {"development_oos", "monitoring"}:
            raise ValueError("Unexpected evaluation tier")
        result[name] = frame[frame.evaluation_tier.eq("development_oos")].copy()
    base = Path(root) / m["baseline_path"]
    base_raw = (base / "manifest.json").read_bytes()
    if hashlib.sha256(base_raw).hexdigest() != m["baseline_manifest_sha256"]:
        raise ValueError("Frozen baseline manifest mismatch")
    bm = json.loads(base_raw)
    if bm.get("final_period_sealed") is not True:
        raise ValueError("Frozen baseline seal mismatch")
    bp = base / "probability_metrics.csv"
    if (
        bp.is_symlink()
        or hashlib.sha256(bp.read_bytes()).hexdigest()
        != bm["files"]["probability_metrics.csv"]
    ):
        raise ValueError("Frozen baseline probability integrity mismatch")
    bf = pd.read_csv(bp)
    if not set(bf.evaluation_tier) <= {"development_oos", "monitoring"}:
        raise ValueError("Unexpected baseline evaluation tier")
    result["legacy_probability.csv"] = bf[
        bf.evaluation_tier.eq("development_oos") & bf.version.eq("stage1a_normal_rule")
    ].copy()
    result["manifest"] = m
    return result
