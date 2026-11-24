"""Prospectively freeze and test fixed workload challengers; never promote models."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.build_slate import MARKETS as LABELS
from stage1b.data import MARKETS
from weekly_learning.admission import utc, validate_receipt
from weekly_learning.store import ROOT, sha

from .study import holm, paired_weeks, point_metrics

PROTOCOL = Path(__file__).with_name("weekly_protocol.json")


def prospective_frame(slate, kickoffs, now):
    now = utc(now)
    frame = slate[slate.projection_status.eq("complete")].copy()
    reverse = {v: k for k, v in LABELS.items()}
    frame["market"] = frame.market.map(lambda m: m if m in MARKETS else reverse.get(m))
    if (
        frame.empty
        or frame.market.isna().any()
        or frame.duplicated(["game_id", "player_id", "market"]).any()
    ):
        raise ValueError("No unambiguous supported prospective forecast rows")
    frame["kickoff_at"] = frame.game_id.map(kickoffs)
    if (
        frame.kickoff_at.isna().any()
        or not pd.to_datetime(frame.prediction_at, utc=True).le(now).all()
        or not pd.to_datetime(frame.kickoff_at, utc=True)
        .gt(now + pd.Timedelta(minutes=60))
        .all()
    ):
        raise ValueError("Cannot backdate a workload challenger capture")
    frame["baseline"] = frame.projection
    for w in [0.25, 0.5, 0.75]:
        name = f"captured_season_recent_{w:g}"
        values = w * frame.recent_form + (1 - w) * frame.career_avg
        frame[name] = values.where(np.isfinite(values), frame.baseline)
        frame[name + "_missing_input_fallback"] = ~np.isfinite(values)
        counts = frame.market.map(lambda m: MARKETS[m][3])
        frame.loc[counts, name] = frame.loc[counts, name].clip(lower=0)
    return frame


def capture(store, directory, manifest, *, now=None):
    now = utc(now or datetime.now(UTC))
    directory = Path(directory)
    # The existing contract has already admitted this bundle in freeze_prepared.
    frame = prospective_frame(
        pd.read_parquet(directory / "slate.parquet"), manifest["game_kickoffs"], now
    )
    from selection_learning.engine import digest

    key = digest(
        {
            "release": manifest["release_id"],
            "protocol": sha(PROTOCOL),
            "code": sha(Path(__file__)),
        }
    )[:24]
    target = store.root / "performance_captures" / key
    if target.exists():
        store.validate(target)
        return target
    meta = {
        "release_id": manifest["release_id"],
        "frozen_at": now.isoformat(),
        "capture_tier": "genuine_predecision_capture",
        "source_manifest_sha256": sha(directory / "manifest.json"),
        "protocol_sha256": sha(PROTOCOL),
        "code_sha256": sha(Path(__file__)),
        "analysis_helper_sha256": sha(Path(__file__).with_name("study.py")),
        "models": manifest["models"],
        "game_kickoffs": manifest["game_kickoffs"],
        "status": "experimental_not_promoted",
        "scope": "Legacy career_avg is the model first feature (season average in current frozen models); recent_form is the last3 feature. These rounded slate values are not the historical career-average experiment.",
    }
    with store.transaction():
        return store.publish(
            "performance_captures",
            key,
            frames={"predictions.parquet": frame},
            documents={"capture.json": meta},
        )


def try_capture(store, directory, manifest):
    try:
        return capture(store, directory, manifest)
    except (ValueError, OSError, KeyError, TypeError):
        # No late/partial experimental capture can replace the champion capture.
        return None


def evaluate(store, cycle_id, release_id, result, receipt, *, now=None):
    now = utc(now or datetime.now(UTC))
    policy = json.loads((ROOT / "weekly_learning/policy.json").read_text())
    admission = validate_receipt(ROOT, receipt, policy, now=now)
    captures = sorted((store.root / "performance_captures").glob("*"))
    outputs = []
    for folder in captures:
        store.validate(folder)
        meta = json.loads((folder / "capture.json").read_text())
        if meta["release_id"] != release_id:
            continue
        from weekly_learning.admission import time_gate

        for game in meta["game_kickoffs"]:
            season, week = map(int, game.split("_")[:2])
            time_gate(policy, season, week, capture=meta, now=now)
        target = (
            store.root / "performance_evaluations" / (cycle_id + "-" + folder.name[:12])
        )
        if target.exists():
            store.validate(target)
            outputs.append(target)
            continue
        predictions = pd.read_parquet(folder / "predictions.parquet")
        observed = result[result.status.eq("scored")][
            ["game_id", "player_id", "market", "actual"]
        ]
        joined = predictions.merge(
            observed, on=["game_id", "player_id", "market"], validate="one_to_one"
        )
        if (
            not set(joined.game_id).issubset(
                {g["game_id"] for g in admission["allowed_games"]}
            )
            or meta["models"] != admission["models"]
        ):
            raise ValueError(
                "Prospective results/model identities are outside admission"
            )
        joined["y"] = joined.actual
        rows = []
        for market, g in joined.groupby("market"):
            for method in [
                "captured_season_recent_0.25",
                "captured_season_recent_0.5",
                "captured_season_recent_0.75",
            ]:
                rows.append(
                    {
                        "market": market,
                        "method": method,
                        **point_metrics(g, method),
                        "baseline_mae": point_metrics(g, "baseline")["mae"],
                        "missing_input_fallback_n": int(
                            g[method + "_missing_input_fallback"].sum()
                        ),
                        **paired_weeks(
                            g, (g.baseline - g.y).abs() - (g[method] - g.y).abs()
                        ),
                    }
                )
        holm(rows)
        report = {
            "release_id": release_id,
            "cycle_id": cycle_id,
            "captured_rows": len(predictions),
            "scored_rows": len(joined),
            "missing_or_unscored_rows": len(predictions) - len(joined),
            "capture_manifest_sha256": sha(folder / "manifest.json"),
            "operational_receipt_sha256": sha(receipt),
            "status": "RETAIN_CHAMPION",
            "reason": "Prospective point diagnostics only; probability, price-matched selection/ticket evidence and multiweek gates still required",
            "candidate_metrics": rows,
        }
        with store.transaction():
            outputs.append(
                store.publish(
                    "performance_evaluations",
                    target.name,
                    frames={"paired_predictions.parquet": joined},
                    documents={"report.json": report},
                )
            )
    return outputs
