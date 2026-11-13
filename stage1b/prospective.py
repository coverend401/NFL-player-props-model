"""Pre-kickoff capture using the frozen experiment; no outcomes or clock override.

This is an offline research utility, not an active production updater. The owner
must supply reviewed, as-of feature vectors; no injury/roster facts are inferred.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import joblib
import numpy as np
import pandas as pd
from stage1b.artifacts import validate, digest
from stage1b.data import MARKETS
from stage1b.runner import model_predictions, cdf_for
from stage1b.probability import outcomes


def capture(experiment, root, features, output, raw_snapshots):
    experiment, root, output = (
        Path(experiment).resolve(),
        Path(root).resolve(),
        Path(output).resolve(),
    )
    manifest = validate(experiment, root)
    protocol = json.loads((experiment / "protocol.json").read_text())
    now = pd.Timestamp(datetime.now(timezone.utc))
    if output.exists():
        raise ValueError("Prospective records are immutable")
    if (
        output.resolve() in [root / "data", root / "release_candidates"]
        or root / "data" in output.resolve().parents
        or root / "release_candidates" in output.resolve().parents
    ):
        raise ValueError("Research capture cannot write production directories")
    if root in output.parents and root / "experiments" not in output.parents:
        raise ValueError(
            "Captures inside the checkout must stay in research experiments"
        )
    records = []
    for market, d in features.groupby("market"):
        bundle = joblib.load(experiment / "models" / f"{market}-2026.joblib")
        allowed = set(bundle["features"]) | {
            "market",
            "player_id",
            "game_id",
            "kickoff_at",
            "history_available_at",
            "source_snapshot_sha256",
            "line",
        }
        if set(d) - allowed:
            raise ValueError(
                "Unexpected fields: outcomes and retrospective context are prohibited"
            )
        if market not in MARKETS or d[["player_id", "game_id"]].duplicated().any():
            raise ValueError("Invalid candidate identity")
        kickoff = pd.to_datetime(d.kickoff_at, utc=True)
        decision = kickoff - pd.Timedelta(hours=protocol["prediction_lead_hours"])
        if (kickoff < pd.Timestamp(protocol["final_start"])).any() or not (
            (decision <= now) & (now < decision + pd.Timedelta(minutes=5))
        ).all():
            raise ValueError(
                "Capture is outside registered pregame final-period decision window"
            )
        if not (pd.to_datetime(d.history_available_at, utc=True) < now).all():
            raise ValueError("History unavailable at capture")
        if (
            not d.games_played_prior.ge(3).all()
            or not d.offense_pct_last3_avg.gt(0).all()
        ):
            raise ValueError("Pregame participation-history eligibility failed")
        for expected in d.source_snapshot_sha256.unique():
            if (
                expected not in raw_snapshots
                or digest(Path(raw_snapshots[expected])) != expected
            ):
                raise ValueError("Raw as-observed snapshot is missing or changed")
        if d.source_snapshot_sha256.str.fullmatch("[0-9a-f]{64}").ne(True).any():
            raise ValueError("Source snapshot identity required")
        if not np.isfinite(d[bundle["features"]].to_numpy(float)).all():
            raise ValueError("Incomplete or invalid feature vector")
        pred = model_predictions(bundle, d)
        cdf = cdf_for(
            bundle, bundle["selected_kind"], pred, bundle["selected_calibration"]
        )
        p = outcomes(cdf, d.line.to_numpy(float))
        z = d[
            [
                "market",
                "player_id",
                "game_id",
                "kickoff_at",
                "history_available_at",
                "source_snapshot_sha256",
                "line",
            ]
        ].copy()
        z["line_kind"] = "owner_supplied_line_no_price_claim"
        z["prediction_at"] = now.isoformat()
        z["projection"] = pred[0]
        z[["p_over", "p_under", "p_push"]] = p
        z["frozen_experiment"] = manifest["experiment_id"]
        records.append(z)
    if not records:
        raise ValueError("No prospective candidates")
    output.mkdir(parents=True)
    (output / "sources").mkdir()
    for expected in features.source_snapshot_sha256.unique():
        shutil.copyfile(raw_snapshots[expected], output / "sources" / expected)
    data = pd.concat(records, ignore_index=True)
    data.to_parquet(output / "predictions.parquet", index=False)
    (output / "capture.json").write_text(
        json.dumps(
            {
                "observed_at": now.isoformat(),
                "experiment_manifest_sha256": digest(experiment / "manifest.json"),
                "predictions_sha256": digest(output / "predictions.parquet"),
                "outcomes_present": False,
                "source_limitation": "Feature-vector source hashes must resolve to owner-preserved, reviewed pregame raw snapshots; capture alone does not authenticate external facts.",
            },
            indent=2,
        )
        + "\n"
    )
    return data
