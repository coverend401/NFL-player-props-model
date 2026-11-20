"""Free weekly research operations; immutable state, no production or odds access."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from .engine import POLICY, capture, dry_run, evaluate_candidate, reconcile, summaries
from .sources import fetch, load_results, permitted
from .store import ROOT, Store, encoded, safe_id, sha


def operational(store, results_week, target_week, cycle_id, source_dir=None):
    safe_id(cycle_id)
    existing = store.root / "cycles" / cycle_id
    if existing.exists():
        store.validate(existing)
        return existing
    policy = json.loads(POLICY.read_text())
    # Capture existing approved forecasts first; already archived releases are idempotent.
    captured = capture(store)
    document = json.loads((captured / "capture.json").read_text())
    try:
        permitted(2026, results_week, policy)
    except ValueError as error:
        with store.transaction():
            return store.publish(
                "cycles",
                cycle_id,
                documents={
                    "report.json": {
                        "cycle_id": cycle_id,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "mode": "operational",
                        "status": "blocked_before_results_access",
                        "reason": str(error),
                        "champion_retained": True,
                        "next_slate": {"status": "blocked", "target_week": target_week},
                        "capture": document,
                    }
                },
            )
    frame = pd.read_parquet(captured / "forecasts.parquet")
    if not frame.week.eq(results_week).any():
        raise ValueError(
            "No genuine predecision forecast capture for requested results week; use dry-run explicitly for historical data"
        )
    source = (
        Path(source_dir)
        if source_dir
        else fetch(
            store.root / "sources" / cycle_id,
            2026,
            results_week,
            policy,
            forecasting=True,
        )
    )
    players, schedule, teams = load_results(source, 2026, results_week, policy)
    from scripts.build_slate import MARKETS

    reverse = {v: k for k, v in MARKETS.items()}
    frame = frame[
        frame.week.eq(results_week) & frame.projection_status.eq("complete")
    ].copy()
    context = captured / "experimental_context.parquet"
    if context.exists():
        extra = pd.read_parquet(
            context,
            columns=[
                "game_id",
                "player_id",
                "market",
                "expected_attempts",
                "expected_carries",
                "p_trailing",
                "p_close",
                "p_leading",
                "expected_margin",
            ],
        )
        frame = frame.merge(
            extra,
            on=["game_id", "player_id", "market"],
            how="left",
            validate="one_to_one",
        )
    frame["market"] = frame.market.map(reverse)
    if frame.market.isna().any():
        raise ValueError("Unsupported canonical market")
    result = reconcile(frame, players, schedule, teams, pd.Timestamp.now(tz="UTC"))
    with store.transaction():
        decision = evaluate_candidate(store, policy)
        report = {
            "cycle_id": cycle_id,
            "completed_at": datetime.now(UTC).isoformat(),
            "mode": "operational",
            "status_counts": result.status.value_counts().to_dict(),
            "metrics": summaries(result),
            "candidate": decision,
            "champion_retained": True,
            "capture": document,
            "sources_sha256": sha(source / "sources.json"),
            "next_slate": {"status": "pending_certification"},
        }
        folder = store.publish(
            "cycles",
            cycle_id,
            frames={"reconciled.parquet": result},
            documents={"report.json": report},
        )
    # Never promote after incomplete reconciliation.
    if not result.status.eq("scored").all():
        with store.transaction():
            store.audit(
                "next_forecast_blocked",
                {
                    "cycle": cycle_id,
                    "reason": "Incomplete outcomes; last certified release preserved",
                },
            )
        return folder
    from .forecast import prepare_next

    # Seal / eligibility / provenance / original replay validator still apply.
    try:
        original = json.loads((captured / "release_manifest.json").read_text())
        parent = original["model_parent"]["path"]
        if (store.root / "champion.json").exists():
            champion = json.loads((store.root / "champion.json").read_text())
            champion_manifest = json.loads(
                (ROOT / champion["path"] / "manifest.json").read_text()
            )
            parent = champion_manifest["model_parent"]["path"]
        release = prepare_next(
            source,
            store.root / "builds" / cycle_id / "inputs",
            target_week,
            policy,
            "weekly-" + cycle_id,
            model_parent=parent,
        )
        manifest = json.loads((release / "manifest.json").read_text())
        if (
            manifest["certification"]["status"] != "passed"
            or not manifest["certification"]["checks"]["exact_replay"]
        ):
            raise ValueError("Next forecast has no exact-replay certification")
        selection = {
            "path": str(release.relative_to(ROOT)),
            "release_id": manifest["release_id"],
            "manifest_sha256": sha(release / "manifest.json"),
        }
        pointer = ROOT / "research_active_inference.json"
        with store.transaction():
            store.publish(
                "selections",
                cycle_id,
                documents={
                    "previous_pointer.json": json.loads(pointer.read_text()),
                    "new_pointer.json": selection,
                },
            )
            temp = ROOT / ".research-learning-pointer.next.json"
            with temp.open("x") as f:
                f.write(encoded(selection))
            os.replace(temp, pointer)
            store.publish(
                "readiness",
                cycle_id,
                documents={
                    "readiness.json": {
                        "status": "certified_research_forecast_selected",
                        "target_week": target_week,
                        **selection,
                    }
                },
            )
            store.audit(
                "next_forecast_certified",
                {"cycle": cycle_id, **selection, "selected": True},
            )
    except (ValueError, OSError, KeyError) as error:
        with store.transaction():
            store.publish(
                "readiness",
                cycle_id,
                documents={
                    "readiness.json": {
                        "status": "blocked",
                        "target_week": target_week,
                        "reason_type": type(error).__name__,
                        "reason": str(error),
                    }
                },
            )
            store.audit(
                "next_forecast_blocked",
                {
                    "cycle": cycle_id,
                    "reason_type": type(error).__name__,
                    "reason": str(error),
                },
            )
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["capture", "cycle"])
    parser.add_argument(
        "--mode", choices=["dry-run", "operational", "auto"], default="dry-run"
    )
    parser.add_argument("--state", type=Path, default=ROOT / "weekly_learning_state")
    parser.add_argument("--week", type=int, default=9)
    parser.add_argument("--target-week", type=int, default=12)
    parser.add_argument("--id", default="2026-w09-dryrun-v1")
    parser.add_argument("--sources", type=Path)
    args = parser.parse_args()
    safe_id(args.id)
    store = Store(args.state)
    if args.command == "capture":
        out = capture(store)
    elif args.mode == "dry-run":
        capture(store)
        out = dry_run(store, args.week, args.id)
    elif args.mode == "auto":
        captured = capture(store)
        doc = json.loads((captured / "capture.json").read_text())
        last = max(pd.Timestamp(t) for t in doc["game_kickoffs"].values())
        if pd.Timestamp.now(tz="UTC") < last + pd.Timedelta(hours=8):
            print(
                encoded(
                    {
                        "status": "forecasts_captured_waiting_for_completed_games",
                        "capture": str(captured),
                    }
                )
            )
            return
        frame = pd.read_parquet(captured / "forecasts.parquet", columns=["week"])
        week = int(frame.week.max())
        out = operational(store, week, week + 1, args.id, args.sources)
    else:
        out = operational(store, args.week, args.target_week, args.id, args.sources)
    print(
        encoded(
            {
                "artifact": str(out),
                "production_changed": False,
                "model_retrained": False,
            }
        )
    )


if __name__ == "__main__":
    main()
