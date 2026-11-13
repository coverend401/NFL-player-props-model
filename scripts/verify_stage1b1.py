"""Replay every archived research prediction; no fitting, activation or database access."""

import json
from pathlib import Path
import sys

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stage1b.data import prepare_panel, read_development_snapshot, market_panel
from stage1b1.artifacts import validate, validate_results
from stage1b1.runner import evaluate


def replay(directory):
    directory = Path(directory)
    manifest = validate(directory, ROOT)
    audit = validate_results(directory, ROOT)
    protocol = json.loads((directory / "protocol.json").read_text())
    panel = prepare_panel(
        read_development_snapshot(ROOT / manifest["input_path"], protocol), protocol
    )
    frames = []
    probes = []
    for path in sorted((directory / "models").glob("*.joblib")):
        bundle = joblib.load(path)
        d = market_panel(panel, bundle["market"])
        d = d[d.season.eq(bundle["year"]) & d.feature_complete & d.scorable]
        f, q = evaluate(bundle, d, protocol)
        frames.append(f)
        probes.append(q)
    f = pd.concat(frames, ignore_index=True)
    q = pd.concat(probes, ignore_index=True)
    oldf = pd.read_parquet(directory / "forecasts.parquet")
    oldq = pd.read_parquet(directory / "probes.parquet")
    keys = ["row_id"]
    qkeys = ["row_id", "version", "probe_multiplier"]
    pd.testing.assert_frame_equal(
        f.sort_values(keys).reset_index(drop=True),
        oldf.sort_values(keys).reset_index(drop=True),
        rtol=1e-12,
        atol=1e-12,
    )
    pd.testing.assert_frame_equal(
        q.sort_values(qkeys).reset_index(drop=True),
        oldq.sort_values(qkeys).reset_index(drop=True),
        rtol=1e-12,
        atol=1e-12,
    )
    print(
        json.dumps(
            {
                **audit,
                "all_predictions_and_probabilities_replayed": True,
                "paired_probes": len(q),
            }
        )
    )


if __name__ == "__main__":
    replay(
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "experiments/stage1b1/improvements-20261113-v1"
    )
