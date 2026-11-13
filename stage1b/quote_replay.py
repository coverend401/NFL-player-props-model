"""Offline repricing at exact historical lines, never interpolated probe prices."""

import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from stage1b.artifacts import validate
from stage1b.data import prepare_panel, market_panel, read_development_snapshot
from stage1b.runner import price_bundle


def reprice_quotes(quotes, experiment, root):
    experiment, root = Path(experiment), Path(root)
    manifest = validate(experiment, root)
    protocol = json.loads((experiment / "protocol.json").read_text())
    panel = prepare_panel(
        read_development_snapshot(root / manifest["input_relative_path"], protocol),
        protocol,
    )
    q = quotes.copy()
    q["decision_at"] = pd.to_datetime(q.decision_at, utc=True)
    if (q.decision_at >= pd.Timestamp(protocol["final_start"])).any():
        raise ValueError("Sealed final period")
    output = []
    for market, g in q.groupby("market"):
        d = market_panel(panel, market)
        joined = g.merge(
            d,
            on=["game_id", "player_id"],
            how="left",
            suffixes=("", "_observation"),
            validate="many_to_one",
        )
        # Existing entering-game features are valid for the registered one-hour
        # decision only. Other timings require a new as-of history build.
        if (
            not pd.to_datetime(joined.kickoff_at, utc=True)
            .eq(joined.kickoff_at_observation)
            .all()
        ):
            raise ValueError("Bookmaker event mapping disagrees with NFL kickoff")
        if (
            not joined.decision_at.eq(joined.prediction_at).all()
            or not joined.feature_complete.fillna(False).all()
        ):
            raise ValueError("No features at this exact historical decision time")
        for year, h in joined.groupby("season"):
            bundle = joblib.load(experiment / "models" / f"{market}-{int(year)}.joblib")
            if not (
                h.decision_at > pd.Timestamp(bundle["model_fit_available_at"])
            ).all():
                raise ValueError("Model unavailable at decision")
            probabilities = price_bundle(bundle, h, h.line.to_numpy())
            z = h[
                [
                    "game_id",
                    "player_id",
                    "market",
                    "line",
                    "decision_at",
                    "history_available_at",
                ]
            ].copy()
            z["model_fit_available_at"] = bundle["model_fit_available_at"]
            z[["p_over", "p_under", "p_push"]] = probabilities
            z["outcome"] = h.y.to_numpy()
            z["outcome_available_at"] = h.completed_at.to_numpy()
            z["positive_offensive_participation"] = h.scorable.to_numpy()
            z["participation_verified"] = h.scorable.to_numpy()
            z["action_status"] = np.where(h.scorable, "action", "unknown")
            output.append(z)
    if not output:
        return pd.DataFrame()
    return pd.concat(output, ignore_index=True).drop_duplicates(
        ["game_id", "player_id", "market", "line", "decision_at"]
    )
