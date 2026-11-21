"""Read-only replay of saved reconciliation and candidate arithmetic; no new test."""

import json

import joblib
import numpy as np
import pandas as pd
from scipy.stats import norm

from .engine import reconcile
from .store import ROOT, sha


def verify(store, cycle_id):
    path = store.root / "cycles" / cycle_id
    store.validate(path)
    report = json.loads((path / "report.json").read_text())
    if report["mode"] != "historical_dry_run":
        raise ValueError(
            "Use the immutable operational source snapshot for operational replay"
        )
    archive = store.root / "historical_captures" / f"2026-w{report['week']:02d}"
    store.validate(archive)
    source = ROOT / report["next_slate"]["source_path"]
    if sha(source / "manifest.json") != report["source_manifest_sha256"]:
        raise ValueError("Source release differs")
    from scripts.forecast_features import schedule_times

    players = pd.read_parquet(
        source / "features.parquet",
        filters=[("season", "==", 2026), ("week", "<=", 10)],
    )
    schedule = schedule_times(
        pd.read_parquet(
            source / "schedule.parquet",
            filters=[("season", "==", 2026), ("week", "<=", 10)],
        )
    )
    actual = reconcile(
        pd.read_parquet(archive / "forecasts.parquet"),
        players,
        schedule,
        pd.read_parquet(archive / "team_results.parquet"),
        pd.Timestamp(report["completed_at"]),
    )
    expected = pd.read_parquet(path / "reconciled.parquet")
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False, check_exact=True)
    candidate = report["candidate"]
    for name, value in candidate["inputs"].items():
        if sha(ROOT / name) != value:
            raise ValueError("Candidate input differs")
    old = pd.read_parquet(
        ROOT / "experiments/stage1b/baseline-20261113-v5/forecasts.parquet"
    )
    train = old[old.season.isin(candidate["fit_seasons"])]
    corrections = (train.y - train.projection).groupby(train.market).mean() * 0.5
    held = pd.read_parquet(
        ROOT / "experiments/sunday_script/20261120-v1/player_replay.parquet"
    )
    from stage1b.data import MARKETS

    for row in candidate["markets"]:
        m = row["market"]
        g = held[held.market.eq(m)]
        delta = float(corrections[m])
        assert delta == row["correction"]
        prediction = g.projection + delta
        if MARKETS[m][3]:
            prediction = prediction.clip(lower=0)
        error = prediction - g.y
        for key, value in {
            "mae": error.abs().mean(),
            "rmse": np.sqrt((error**2).mean()),
            "bias": error.mean(),
        }.items():
            if float(value) != row["candidate"][key]:
                raise ValueError("Candidate arithmetic replay mismatch")
        model = joblib.load(
            ROOT / f"experiments/stage1b/baseline-20261113-v5/models/{m}-2026.joblib"
        )
        line = np.floor(np.maximum(g.projection, 0)) + 0.5
        truth = g.y.gt(line).astype(int).to_numpy()
        for name, mu in [("baseline", g.projection), ("candidate", prediction)]:
            p = np.clip(
                norm.sf(
                    line, mu, model["distributions"]["stage1a_normal"].in_sample_scale
                ),
                1e-6,
                1 - 1e-6,
            )
            scores = {
                "brier": float(np.mean((p - truth) ** 2)),
                "log_loss": float(
                    np.mean(-truth * np.log(p) - (1 - truth) * np.log1p(-p))
                ),
            }
            if scores != row["probability_scores"][name]:
                raise ValueError("Probability arithmetic replay mismatch")
    return {
        "reconciliation_rows": len(actual),
        "candidate_markets_verified": len(candidate["markets"]),
        "exact_reconciliation_replay": True,
        "exact_point_probability_arithmetic": True,
        "new_holdout_test": False,
        "state_modified": False,
    }
