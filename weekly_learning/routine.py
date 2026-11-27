"""Routine research operation: settle admitted captures, prepare, certify and publish.

Never trains the champion, reads premature results or changes main/production.
Publication is a separate target-runtime stage with standing owner authority.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from .admission import (
    approve_snapshot,
    capture_check,
    prove_schedule,
    time_gate,
    validate_receipt,
)
from .authority import validate as authority
from .engine import POLICY, reconcile, summaries
from .sources import fetch, load_results
from .store import ROOT, Store, encoded, safe_id, sha


def pending(store, policy, now):
    completed = set()
    for path in (store.root / "cycles").glob("*/report.json"):
        report = json.loads(path.read_text())
        if report.get("mode") == "operational" and (
            report.get("status") == "completed"
            or (
                report.get("status") == "completed_with_missing"
                and pd.Timestamp(now) - pd.Timestamp(report["completed_at"])
                < pd.Timedelta(hours=24)
            )
        ):
            completed.add(report.get("capture", {}).get("release_id"))
    due = []
    waiting = []
    for path in (store.root / "captures").glob("*/capture.json"):
        meta = json.loads(path.read_text())
        if (
            meta.get("capture_tier") != "genuine_predecision_capture"
            or meta["release_id"] in completed
        ):
            continue
        season, week = map(int, next(iter(meta["game_kickoffs"])).split("_")[:2])
        try:
            time_gate(policy, season, week, capture=meta, now=now)
        except ValueError:
            waiting.append(meta["release_id"])
            continue
        capture_check(ROOT, str(path.parent.relative_to(ROOT)))
        due.append((season, week, path.parent, meta))
    return sorted(due, key=lambda x: (x[0], x[1], x[3]["frozen_at"])), waiting


def settle(store, run_id, now):
    policy = json.loads(POLICY.read_text())
    due, waiting = pending(store, policy, now)
    sources = {}
    completed = []
    private = []
    for season, week, path, meta in due:
        key = (season, week)
        if key not in sources:
            source = store.root / "sources" / f"{run_id}-results-{season}-{week}"
            proof = {}

            def confirm(folder, proof=proof, path=path):
                proof.update(
                    prove_schedule(ROOT, folder, str(path.relative_to(ROOT)), policy)
                )

            fetch(
                source, season, week, policy, forecasting=True, schedule_ready=confirm
            )
            approve_snapshot(
                ROOT, source, str(path.relative_to(ROOT)), policy, proof=proof
            )
            sources[key] = source
        source = sources[key]
        validate_receipt(ROOT, source / "operational_admission.json", policy)
        players, games, teams = load_results(source, season, week, policy)
        _, frame = capture_check(ROOT, str(path.relative_to(ROOT)))
        frame = frame[frame.projection_status.eq("complete")].copy()
        from scripts.build_slate import MARKETS

        reverse = {v: k for k, v in MARKETS.items()}
        frame["market"] = frame.market.map(lambda x, reverse=reverse: reverse.get(x, x))
        actual_kickoffs = games.set_index("game_id").kickoff_at
        if (
            not frame.game_id.isin(actual_kickoffs.index).all()
            or not (
                pd.to_datetime(frame.prediction_at, utc=True)
                < frame.game_id.map(actual_kickoffs) - pd.Timedelta(minutes=60)
            ).all()
        ):
            raise ValueError("Captured prediction was not before actual T-60")
        context = path / "experimental_context.parquet"
        if context.exists():
            extra = pd.read_parquet(context)
            keys = ["game_id", "player_id", "market"]
            columns = keys + [c for c in extra if c not in frame and c not in keys]
            frame = frame.merge(
                extra[columns], on=keys, how="left", validate="one_to_one"
            )
        observed = datetime.now(UTC)
        result = reconcile(frame, players, games, teams, pd.Timestamp(observed))
        cycle = (
            "settle-"
            + sha(path / "manifest.json")[:16]
            + "-"
            + sha(source / "operational_admission.json")[:16]
        )
        report = {
            "cycle_id": cycle,
            "mode": "operational",
            "status": "completed"
            if result.status.eq("scored").all()
            else "completed_with_missing",
            "completed_at": observed.isoformat(),
            "capture": meta,
            "metrics": summaries(result),
            "cohort_metrics": cohort_metrics(result),
            "status_counts": result.status.value_counts().to_dict(),
            "sources_sha256": sha(source / "sources.json"),
            "admission_sha256": sha(source / "operational_admission.json"),
            "champion_retained": True,
            "candidate": {
                "decision": "RETAIN_CHAMPION",
                "reason": "Only independently qualified challengers may be promoted",
            },
            "next_slate": {"status": "routine_refresh_pending"},
        }
        with store.transaction():
            store.publish(
                "cycles",
                cycle,
                frames={"reconciled.parquet": result},
                documents={"report.json": report},
            )
        completed.append(cycle)
        from .learning import evaluate

        evaluate(store, result, cycle)
    private = settle_private(store)
    return {
        "completed_cycles": completed,
        "waiting_for_authorised_cutoff": waiting,
        "private_settlement": private,
    }


def settle_private(store):
    """Retry durable settlement independently of public-result refresh success."""
    import os

    from selection_learning.settlement import reconcile_cycle
    from selection_learning.store import GitHubJournal

    if not (
        os.environ.get("NFL_SELECTION_GITHUB_REPOSITORY")
        and os.environ.get("NFL_SELECTION_GITHUB_TOKEN")
    ):
        return [{"status": "private_storage_not_configured"}]
    attempts = []
    for path in sorted((store.root / "cycles").glob("*/report.json")):
        report = json.loads(path.read_text())
        if (
            report.get("mode") != "operational"
            or report.get("status") not in ["completed", "completed_with_missing"]
            or not report.get("admission_sha256")
        ):
            continue
        marker = store.root / "private_settlements" / path.parent.name
        if marker.exists():
            store.validate(marker)
            continue
        try:
            game = next(iter(report["capture"]["game_kickoffs"]))
            season, week = map(int, game.split("_")[:2])
            journal = GitHubJournal(
                os.environ["NFL_SELECTION_GITHUB_REPOSITORY"],
                os.environ["NFL_SELECTION_GITHUB_TOKEN"],
                week=f"{season}-{week:02d}",
            )
            status = reconcile_cycle(journal, path.parent)["status"]
            attempts.append({"cycle": path.parent.name, "status": status})
            with store.transaction():
                store.publish(
                    "private_settlements",
                    path.parent.name,
                    documents={
                        "receipt.json": {
                            "status": status,
                            "public_cycle_sha256": sha(path.parent / "manifest.json"),
                            "private_details": "Only in private journal",
                        }
                    },
                )
        except (ValueError, OSError, KeyError, TypeError):
            attempts.append(
                {
                    "cycle": path.parent.name,
                    "status": "private_settlement_blocked; next run retries",
                }
            )
            break
        if len(attempts) >= 4:
            break
    return attempts


def cohort_metrics(result):
    from .engine import metrics

    rows = []
    d = result[result.status.eq("scored")].copy()
    d["workload_band"] = pd.cut(
        pd.to_numeric(
            d.get("games_played_prior", pd.Series(index=d.index, dtype=float)),
            errors="coerce",
        ),
        [-1, 3, 8, float("inf")],
        labels=["limited_history", "developing_history", "established_history"],
    ).astype(str)
    for cohort in ["player_id", "team", "position", "workload_band"]:
        if cohort not in d:
            continue
        for (market, value), g in d.groupby(["market", cohort]):
            rows.append(
                {"market": market, "cohort": cohort, "value": str(value), **metrics(g)}
            )
    return rows


def recent_candidate(store, now, max_age):
    from .contract import validate_operational

    choices = []
    for path in (store.root / "readiness").glob("*/readiness.json"):
        info = json.loads(path.read_text())
        relative = info.get("path", info.get("source_path"))
        if not relative:
            continue
        directory = (ROOT / relative).resolve()
        if not directory.is_relative_to(ROOT / "research_inference_releases"):
            continue
        try:
            m = json.loads((directory / "manifest.json").read_text())
            stamp = pd.Timestamp(m["prediction_at"])
            if stamp > pd.Timestamp(now) or pd.Timestamp(now) - stamp > pd.Timedelta(
                hours=max_age
            ):
                continue
            if not all(
                pd.Timestamp(now) < pd.Timestamp(t) - pd.Timedelta(minutes=60)
                for t in m["game_kickoffs"].values()
            ):
                continue
            authority(directory)
            validate_operational(directory, ROOT)
            choices.append((stamp, directory))
        except (OSError, ValueError, KeyError, TypeError, AssertionError):
            continue
    return max(choices, key=lambda x: x[0])[1] if choices else None


def prepare(store, run_id, *, reuse=True):
    safe_id(run_id)
    existing = store.root / "routine_plans" / run_id
    if existing.exists():
        store.validate(existing)
        return existing
    policy = authority()
    now = datetime.now(UTC)
    result = settle(store, run_id, now)
    directory = (
        recent_candidate(store, now, policy["minimum_refresh_hours"]) if reuse else None
    )
    if directory is None:
        from .operations import prepare_latest

        ready = prepare_latest(store, run_id)
        if ready["status"] != "operational_candidate_certified_not_selected":
            raise ValueError(
                "Routine forecast refresh blocked: "
                + ready.get("reason", ready["status"])
            )
        directory = ROOT / ready["path"]
    authority(directory)
    from .learning import capture as capture_shadow

    capture_shadow(store, directory)
    m = json.loads((directory / "manifest.json").read_text())
    profile = ROOT / "research_runtime_profiles" / ("routine-" + m["release_id"])
    profile.mkdir(exist_ok=True)
    try:
        receipt = json.loads((directory / "admission.json").read_text())
        players = pd.read_parquet(
            ROOT / receipt["source_path"] / "players.parquet",
            columns=["gsis_id", "espn_id"],
        )
        mapping = {
            str(int(r.espn_id)): str(r.gsis_id) for r in players.dropna().itertuples()
        }
        (profile / "player_ids.json").write_text(encoded(mapping))
        from .availability import collect as collect_availability

        result["availability"] = collect_availability(store, run_id, mapping)
    except (ValueError, OSError, KeyError, TypeError):
        result["availability"] = {"status": "unavailable; no player declared healthy"}
    from .fixture_evidence import collect

    if not (profile / "fixture_verification.json").exists():
        collect(directory, profile)
    from scripts.certify_weekly_serving import run

    run(baseline=True, profile=profile, directory=directory)
    plan = {
        "run_id": run_id,
        "release_id": m["release_id"],
        "directory": str(directory.relative_to(ROOT)),
        "profile": str(profile.relative_to(ROOT)),
        "authority_sha256": sha(ROOT / "weekly_learning/standing_authority.json"),
        "manifest_sha256": sha(directory / "manifest.json"),
        "prepared_at": datetime.now(UTC).isoformat(),
        "settlement": result,
        "status": "prepared_not_published",
    }
    with store.transaction():
        target = store.publish("routine_plans", run_id, documents={"plan.json": plan})
    return target


def publish(store, plan_path):
    store.validate(plan_path)
    plan = json.loads((Path(plan_path) / "plan.json").read_text())
    directory, profile = ROOT / plan["directory"], ROOT / plan["profile"]
    authority(directory)
    if plan["authority_sha256"] != sha(
        ROOT / "weekly_learning/standing_authority.json"
    ) or plan["manifest_sha256"] != sha(directory / "manifest.json"):
        raise ValueError("Prepared routine plan changed")
    from scripts.certify_weekly_serving import run

    run(profile=profile, directory=directory)
    from .code_trust import approved_code

    revision = approved_code(store)
    from .publication import publish_validated

    return publish_validated(store, directory, profile, revision, plan)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["prepare", "publish", "availability"])
    p.add_argument("--id", required=True)
    p.add_argument("--no-reuse", action="store_true")
    a = p.parse_args()
    store = Store(ROOT / "weekly_learning_state")
    try:
        if a.stage == "prepare":
            print(prepare(store, a.id, reuse=not a.no_reuse))
        elif a.stage == "publish":
            print(encoded(publish(store, store.root / "routine_plans" / a.id)))
        else:
            from research_platform.weekly_serving import ACTIVE, selected

            from .availability import collect
            from .code_trust import approved_code

            approved_code(store)
            if selected() is None:
                raise ValueError(
                    "No admitted current serving release for availability refresh"
                )
            profile = ROOT / json.loads(ACTIVE.read_text())["profile"]
            mapping = json.loads((profile / "player_ids.json").read_text())
            print(encoded(collect(store, a.id, mapping)))
    except (ValueError, OSError, KeyError, TypeError, AssertionError) as error:
        with store.transaction():
            store.publish(
                "routine_failures",
                a.id + "-" + a.stage,
                documents={
                    "failure.json": {
                        "stage": a.stage,
                        "error_type": type(error).__name__,
                        "reason": str(error),
                        "last_release_preserved": True,
                        "at": datetime.now(UTC).isoformat(),
                    }
                },
            )
        raise SystemExit(
            "Routine operation blocked; last certified release preserved"
        ) from None
