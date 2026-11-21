"""Free weekly research operations; immutable state, no production or odds access."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from types import FunctionType

import pandas as pd

from .engine import POLICY, dry_run, reconcile, summaries
from .engine import capture as capture_legacy
from .selection import capture_current as capture
from .sources import fetch, load_results, permitted
from .store import ROOT, Store, encoded, safe_id, sha


def freeze_prepared(store, directory, manifest):
    # Freeze the next slate before selection and before any Thursday cutoff.
    # Reuse the existing capture checks without changing global app selection.
    from .contract import TYPE

    if manifest.get("release_type") == TYPE:
        return capture(store, prepared=(directory, manifest))
    namespace = {
        **capture_legacy.__globals__,
        "resolve_research_release": lambda repo: (directory, manifest),
    }
    isolated = FunctionType(
        capture_legacy.__code__,
        namespace,
        capture_legacy.__name__,
        capture_legacy.__defaults__,
        capture_legacy.__closure__,
    )
    return isolated(store)


def retained_decision(store):
    prior = store.root / "cycles" / "2026-w09-dryrun-v1"
    store.validate(prior)
    decision = json.loads((prior / "report.json").read_text())["candidate"]
    return {
        **decision,
        "accepted": False,
        "decision": "RETAIN_CHAMPION",
        "replay_only": True,
        "holdout": {**decision["holdout"], "replay_only": True},
        "current_cycle_promotion": "No fresh registered challenger/certification; retrospective decision is not retested",
    }


def script_diagnostics(result):
    if "final_margin_state_brier" not in result:
        return {"game_script_brier": None, "game_script_team_games": 0}
    values = result.dropna(subset=["final_margin_state_brier"]).drop_duplicates(
        ["game_id", "team"]
    )
    return {
        "game_script_brier": float(values.final_margin_state_brier.mean())
        if len(values)
        else None,
        "game_script_team_games": len(values),
        "game_script_scope": "Experimental final margin categories, not in-game occupancy",
    }


def _operational(store, results_week, target_week, cycle_id, source_dir=None):
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
        from .admission import time_gate

        time_gate(
            policy, 2026, results_week, capture=document
        ) if results_week >= policy["final_week"] else permitted(
            2026, results_week, policy
        )
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
                        "status": "waiting_for_settlement",
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
    finality = {}

    def confirm(path):
        from .admission import prove_schedule

        finality.update(
            prove_schedule(ROOT, path, str(captured.relative_to(ROOT)), policy)
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
            schedule_ready=confirm if results_week >= policy["final_week"] else None,
        )
    )
    if results_week >= policy["final_week"]:
        from .admission import approve_snapshot, validate_receipt

        admission = source / "operational_admission.json"
        if admission.exists():
            validate_receipt(ROOT, admission, policy)
        else:
            approve_snapshot(
                ROOT,
                source,
                str(captured.relative_to(ROOT)),
                policy,
                proof=finality or None,
            )
    players, schedule, teams = load_results(source, 2026, results_week, policy)
    from scripts.build_slate import MARKETS

    reverse = {v: k for k, v in MARKETS.items()}
    frame = frame[
        frame.week.eq(results_week) & frame.projection_status.eq("complete")
    ].copy()
    context = captured / "experimental_context.parquet"
    if context.exists():
        import pyarrow.parquet as pq

        available = set(pq.read_schema(context).names)
        extra = pd.read_parquet(
            context,
            columns=[
                name
                for name in [
                    "game_id",
                    "player_id",
                    "market",
                    "expected_attempts",
                    "expected_carries",
                    "p_trailing",
                    "p_close",
                    "p_leading",
                    "expected_margin",
                ]
                if name in available
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
        decision = retained_decision(store)
        report = {
            "cycle_id": cycle_id,
            "completed_at": datetime.now(UTC).isoformat(),
            "mode": "operational",
            "status": "completed"
            if result.status.eq("scored").all()
            else "completed_with_missing",
            "status_counts": result.status.value_counts().to_dict(),
            "metrics": summaries(result),
            "candidate": decision,
            "champion_retained": not decision.get("accepted", False),
            "capture": document,
            "sources_sha256": sha(source / "sources.json"),
            "admission_sha256": sha(source / "operational_admission.json")
            if (source / "operational_admission.json").exists()
            else None,
            "code_sha256": {
                "weekly_learning/" + p.name: sha(p)
                for p in Path(__file__).parent.glob("*.py")
            },
            **script_diagnostics(result),
            "data_gaps": [
                "Missing/zero-snap observations are not zero outcomes or confirmed voids",
                "Team/script comparisons are experimental context, not causal attribution",
            ],
            "next_slate": {"status": "pending_certification"},
        }
        folder = store.publish(
            "cycles",
            cycle_id,
            frames={"reconciled.parquet": result},
            documents={"report.json": report},
        )
    # Normal missing individual targets remain explicit and cannot support promotion.
    # A fresh champion forecast still requires independent source/eligibility certification.
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
        freeze_prepared(store, release, manifest)
        selection = {
            "path": str(release.relative_to(ROOT)),
            "release_id": manifest["release_id"],
            "manifest_sha256": sha(release / "manifest.json"),
        }
        with store.transaction():
            store.publish(
                "readiness",
                cycle_id,
                documents={
                    "readiness.json": {
                        "status": "operational_candidate_certified_not_selected",
                        "target_week": target_week,
                        **selection,
                    }
                },
            )
            store.audit(
                "next_forecast_certified",
                {"cycle": cycle_id, **selection, "selected": False},
            )
    except (ValueError, OSError, KeyError, AssertionError) as error:
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


def operational(store, results_week, target_week, cycle_id, source_dir=None):
    try:
        return _operational(store, results_week, target_week, cycle_id, source_dir)
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        existing = store.root / "cycles" / cycle_id
        if existing.exists():
            with store.transaction():
                store.audit(
                    "operational_stage_failed",
                    {
                        "cycle": cycle_id,
                        "error_type": type(error).__name__,
                        "reason": str(error),
                    },
                )
            return existing
        with store.transaction():
            return store.publish(
                "cycles",
                cycle_id,
                documents={
                    "report.json": {
                        "cycle_id": cycle_id,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "mode": "operational",
                        "status": "blocked_results_integrity",
                        "reason": str(error),
                        "error_type": type(error).__name__,
                        "champion_retained": True,
                        "next_slate": {"status": "blocked", "target_week": target_week},
                    }
                },
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["capture", "cycle", "replay", "preflight", "prepare", "select"],
    )
    parser.add_argument(
        "--mode", choices=["dry-run", "operational", "auto"], default="dry-run"
    )
    parser.add_argument("--state", type=Path, default=ROOT / "weekly_learning_state")
    parser.add_argument("--week", type=int, default=9)
    parser.add_argument("--target-week", type=int, default=12)
    parser.add_argument("--id", default="2026-w09-dryrun-v1")
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--refresh-fixtures", action="store_true")
    args = parser.parse_args()
    safe_id(args.id)
    store = Store(args.state)
    if args.command == "preflight":
        from .operations import preflight

        print(encoded(preflight(store, refresh_fixtures=args.refresh_fixtures)))
        return
    if args.command == "prepare":
        from .operations import prepare_latest

        result = prepare_latest(store, args.id)
        print(encoded(result))
        if result.get("status") == "blocked":
            raise SystemExit(2)
        return
    if args.command == "select":
        if args.candidate is None:
            raise ValueError("--candidate is required for explicit research selection")
        from .selection import select

        print(encoded(select(store, args.candidate)))
        return
    if args.command == "replay":
        from .replay import verify

        print(encoded(verify(store, args.id)))
        return
    if args.command == "capture":
        out = capture(store)
    elif args.mode == "dry-run":
        capture(store)
        out = dry_run(store, args.week, args.id)
    elif args.mode == "auto":
        captured = capture(store)
        json.loads((captured / "capture.json").read_text())
        frame = pd.read_parquet(captured / "forecasts.parquet", columns=["week"])
        week = int(frame.week.max())
        out = operational(store, week, week + 1, args.id, args.sources)
    else:
        out = operational(store, args.week, args.target_week, args.id, args.sources)
    report_path = out / "report.json"
    status = (
        json.loads(report_path.read_text()).get("status")
        if report_path.exists()
        else None
    )
    readiness = store.root / "readiness" / args.id / "readiness.json"
    blocked = str(status).startswith("blocked") or (
        readiness.exists()
        and json.loads(readiness.read_text()).get("status") == "blocked"
    )
    print(
        encoded(
            {
                "status": status,
                "blocked": blocked,
                "artifact": str(out),
                "production_changed": False,
                "model_retrained": False,
            }
        )
    )

    if blocked:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
