"""Frozen predecision probability challenger from earlier genuine paper quotes only."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


def shadow(state, record, at):
    at = pd.Timestamp(at)
    if record.get("line") is None or float(record["line"]).is_integer():
        return {
            "status": "push-aware calibration not validated",
            "method": "platt-shadow-v1",
        }
    current_season, current_week = map(int, record["game_id"].split("_")[:2])
    rows = []
    for event in state["events"]:
        if event["kind"] != "settlement" or pd.Timestamp(event["at"]) >= at:
            continue
        r = event["payload"]
        if (
            r.get("line") is None
            or float(r["line"]).is_integer()
            or r["status"] not in ["win", "loss"]
            or r.get("hit_probability") is None
            or tuple(map(int, r["game_id"].split("_")[:2]))
            >= (current_season, current_week)
        ):
            continue
        rows.append({**r, "week": int(r["game_id"].split("_")[1])})
    d = pd.DataFrame(rows)
    if d.empty:
        return {
            "status": "insufficient_genuine_prior_quotes",
            "method": "platt-shadow-v1",
        }
    d = d.drop_duplicates(["game_id", "player_id", "market", "quote_id"])
    effective = len(d[["game_id", "player_id"]].drop_duplicates())
    if effective < 100 or d.week.nunique() < 4 or d.status.value_counts().min() < 10:
        return {
            "status": "insufficient_genuine_prior_quotes",
            "method": "platt-shadow-v1",
            "n": len(d),
            "independent_player_games": effective,
            "weeks": int(d.week.nunique()),
        }
    if len(d.status.unique()) != 2:
        return {"status": "insufficient_outcome_variation", "method": "platt-shadow-v1"}
    p = np.clip(d.hit_probability.to_numpy(), 1e-6, 1 - 1e-6)
    x = np.log(p / (1 - p)).reshape(-1, 1)
    weights = 1 / d.groupby(["game_id", "player_id"]).quote_id.transform("size")
    model = LogisticRegression(C=1, random_state=291126).fit(
        x, d.status.eq("win").astype(int), sample_weight=weights
    )
    q = float(np.clip(record["hit_probability"], 1e-6, 1 - 1e-6))
    value = float(model.predict_proba([[np.log(q / (1 - q))]])[0, 1])
    return {
        "status": "shadow_only",
        "method": "platt-shadow-v1",
        "probability": value,
        "n": len(d),
        "independent_player_games": effective,
        "weeks": int(d.week.nunique()),
        "trained_before": at.isoformat(),
        "coefficient": float(model.coef_[0, 0]),
        "intercept": float(model.intercept_[0]),
        "promoted": False,
    }
