"""Finite prospective shadow tests; champion and betting probabilities are unchanged."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .store import ROOT, sha

FEATURES = ["projection", "career_avg", "recent_form", "games_played_prior"]
POLICY = {
    "version": "prospective-corrections-v1",
    "families": ["shrunk_market_bias", "role_residual_ridge"],
    "minimum_training_weeks": 2,
    "minimum_training_rows": 100,
    "bias_prior_rows": 100,
    "ridge_alpha": 10,
    "promotion": "Never automatic; requires >=8 prospectively frozen test weeks, paired uncertainty, multiplicity control, probability/selection validation and no important-market regression",
}


def fit_predict(history, future):
    """Training ends before this forecast; actual_* columns cannot be predictors."""
    future = future.copy()
    out = []
    for market, g in future.groupby("market"):
        h = history[history.market.eq(market)].copy() if len(history) else history
        row = {
            "market": market,
            "training_rows": len(h),
            "training_weeks": int(h.week.nunique()) if len(h) else 0,
        }
        if len(h) < 100 or row["training_weeks"] < 2:
            out.append({**row, "status": "insufficient_prior_prospective_data"})
            continue
        cutoff = pd.to_datetime(g.prediction_at, utc=True).min()
        if not pd.to_datetime(h.settled_at, utc=True).lt(cutoff).all():
            raise ValueError("Future settlement entered challenger fitting")
        error = h.actual - h.projection
        columns = [c for c in FEATURES if c in h and c in g]
        model = make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True),
            StandardScaler(),
            Ridge(alpha=10),
        )
        model.fit(h[columns].apply(pd.to_numeric, errors="coerce"), error)
        values = {
            "shrunk_market_bias": np.full(
                len(g), error.mean() * len(h) / (len(h) + 100)
            ),
            "role_residual_ridge": model.predict(
                g[columns].apply(pd.to_numeric, errors="coerce")
            ),
        }
        for method, delta in values.items():
            future.loc[g.index, method] = g.projection.to_numpy() + delta
            if "yards" not in market:
                future.loc[g.index, method] = future.loc[g.index, method].clip(lower=0)
        out.append({**row, "status": "shadow_only", "features": columns})
    return future, out


def prior(store, before):
    rows = []
    from .admission import validate_receipt

    policy = json.loads((ROOT / "weekly_learning/policy.json").read_text())
    receipts = {
        sha(p): p for p in (store.root / "sources").glob("*/operational_admission.json")
    }
    for p in (store.root / "cycles").glob("*/report.json"):
        r = json.loads(p.read_text())
        if (
            r.get("mode") != "operational"
            or r.get("status") not in ["completed", "completed_with_missing"]
            or pd.Timestamp(r["completed_at"]) >= before
        ):
            continue
        store.validate(p.parent)
        receipt = receipts.get(r.get("admission_sha256"))
        if receipt is None:
            continue
        validate_receipt(ROOT, receipt, policy)
        d = pd.read_parquet(p.parent / "reconciled.parquet")
        d = d[d.status.eq("scored")].copy()
        d["settled_at"] = r["completed_at"]
        rows.append(d)
    if not rows:
        return pd.DataFrame()
    return (
        pd.concat(rows, ignore_index=True)
        .sort_values("prediction_at")
        .drop_duplicates(["game_id", "player_id", "market"], keep="last")
    )


def capture(store, directory):
    m = json.loads((directory / "manifest.json").read_text())
    identity = m["release_id"]
    target = store.root / "learning_shadows" / identity
    if target.exists():
        store.validate(target)
        return target
    from scripts.build_slate import MARKETS

    f = pd.read_parquet(directory / "slate.parquet")
    f = f[f.projection_status.eq("complete")].copy()
    f["market"] = f.market.map({v: k for k, v in MARKETS.items()})
    history = prior(store, pd.Timestamp(m["prediction_at"]))
    frame, details = fit_predict(history, f)
    at = datetime.now(UTC)
    if not all(
        pd.Timestamp(at) < pd.Timestamp(t) - pd.Timedelta(minutes=60)
        for t in m["game_kickoffs"].values()
    ):
        raise ValueError("Cannot backdate prospective challenger capture")
    report = {
        "policy": POLICY,
        "code_sha256": sha(Path(__file__)),
        "training_sha256": __import__("hashlib")
        .sha256(history.to_json(orient="records", double_precision=15).encode())
        .hexdigest(),
        "release_id": identity,
        "frozen_at": at.isoformat(),
        "parent_manifest_sha256": sha(directory / "manifest.json"),
        "details": details,
        "champion_changed": False,
    }
    with store.transaction():
        return store.publish(
            "learning_shadows",
            identity,
            frames={"predictions.parquet": frame},
            documents={"protocol.json": report},
        )


def evaluate(store, actuals, cycle):
    output = []
    for p in (store.root / "learning_shadows").glob("*/protocol.json"):
        store.validate(p.parent)
        meta = json.loads(p.read_text())
        f = pd.read_parquet(p.parent / "predictions.parquet")
        g = f.merge(
            actuals[actuals.status.eq("scored")][
                ["game_id", "player_id", "market", "actual"]
            ],
            on=["game_id", "player_id", "market"],
            how="inner",
            validate="one_to_one",
        )
        if g.empty:
            continue
        for market, h in g.groupby("market"):
            for method in POLICY["families"]:
                if method not in h or h[method].isna().all():
                    continue
                paired = h[h[method].notna()]
                base = paired.projection - paired.actual
                error = paired[method] - paired.actual
                output.append(
                    {
                        "release_id": meta["release_id"],
                        "market": market,
                        "method": method,
                        "n": len(paired),
                        "baseline_mae": float(base.abs().mean()),
                        "shadow_mae": float(error.abs().mean()),
                        "baseline_rmse": float(np.sqrt((base**2).mean())),
                        "shadow_rmse": float(np.sqrt((error**2).mean())),
                        "bias": float(error.mean()),
                        "scope": "Prospective shadow predictions; no promotion or betting-profit inference",
                    }
                )
    with store.transaction():
        return store.publish(
            "learning_evaluations",
            cycle,
            documents={
                "report.json": {
                    "comparisons": output,
                    "promotion": "RETAIN_CHAMPION",
                    "policy": POLICY,
                }
            },
        )
