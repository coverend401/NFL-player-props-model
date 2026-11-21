"""Operational preflight and current-fixture research; no result access before admission."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from .admission import capture_check, time_gate
from .engine import POLICY
from .selection import capture_current
from .store import ROOT, sha

FIXTURES = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"


def fixture_plan(store, *, season=2026, week=12, get=None):
    name = f"week{week}-fixtures-{datetime.now(UTC).strftime('%Y%m%d')}"
    target = store.root / "plans" / name
    if target.exists():
        store.validate(target)
        return json.loads((target / "plan.json").read_text())
    get = get or requests.get
    with tempfile.TemporaryDirectory(prefix="nfl-fixture-metadata-") as tmp:
        raw = Path(tmp) / "quarantined.parquet"
        size = 0
        with get(FIXTURES, stream=True, timeout=(5, 30)) as response:
            response.raise_for_status()
            with raw.open("xb") as out:
                for block in response.iter_content(1024 * 1024):
                    size += len(block)
                    if size > 32 * 1024 * 1024:
                        raise ValueError("Fixture source exceeds size bound")
                    out.write(block)
        source = {
            "url": FIXTURES,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "sha256": sha(raw),
        }
        columns = [
            "season",
            "week",
            "game_id",
            "game_type",
            "gameday",
            "gametime",
            "home_team",
            "away_team",
            "roof",
        ]
        frame = pd.read_parquet(
            raw,
            columns=columns,
            filters=[
                ("season", "==", season),
                ("week", "==", week),
                ("game_type", "==", "REG"),
            ],
        )
        if frame.empty or frame.game_id.duplicated().any():
            raise ValueError("Missing/ambiguous target fixture metadata")
        local = pd.to_datetime(
            frame.gameday.astype(str) + " " + frame.gametime.astype(str),
            errors="coerce",
        )
        frame["kickoff_at"] = (
            local.dt.tz_localize(
                "America/New_York", ambiguous="raise", nonexistent="raise"
            )
            .dt.tz_convert("UTC")
            .map(lambda t: None if pd.isna(t) else t.isoformat())
        )
        records = frame[
            ["game_id", "home_team", "away_team", "kickoff_at", "roof"]
        ].to_dict("records")
    plan = {
        "season": season,
        "week": week,
        "fixtures": records,
        "source": source,
        "outcome_columns_read": False,
        "forecasts_generated": False,
        "eligibility": "Fresh target-week roster/depth evidence required after settlement; no prior-week eligibility reuse",
    }
    with store.transaction():
        store.publish("plans", name, documents={"plan.json": plan})
    return plan


def preflight(store, *, refresh_fixtures=False, record_capture=True):
    if record_capture:
        captured = capture_current(store)
    else:
        from .selection import resolve_current

        _, selected = resolve_current()
        captured = store.root / "captures" / selected["release_id"]
        if not captured.exists():
            return {
                "capture_valid": False,
                "status": "capture_required",
                "reason": "No genuine immutable capture exists for the current release",
            }
    policy = json.loads(POLICY.read_text())
    meta, _ = capture_check(ROOT, str(captured.relative_to(ROOT)))
    season = int(next(iter(meta["game_kickoffs"])).split("_")[0])
    week = int(next(iter(meta["game_kickoffs"])).split("_")[1])
    result = {
        "capture": str(captured.relative_to(ROOT)),
        "capture_valid": True,
        "results_week": week,
        "target_week": week + 1,
        "time_gate_open": False,
        "finality_verified": False,
        "source_results_accessed": False,
        "candidate_generated": False,
        "recurring_jobs_activated": False,
    }
    try:
        cutoff = time_gate(policy, season, week, capture=meta)
        result.update(
            time_gate_open=True,
            settlement_cutoff=cutoff.isoformat(),
            status="awaiting_fresh_sources_and_confirmed_finals",
        )
    except ValueError as error:
        result.update(status="waiting_for_settlement", reason=str(error))
    if refresh_fixtures:
        result["fixture_plan"] = fixture_plan(store, season=season, week=week + 1)
    return result


def render_game_research(release):
    from .contract import TYPE

    if release.get("release_type") != TYPE:
        return
    directory = ROOT / "research_inference_releases" / release["release_id"]
    research = json.loads((directory / "game_script.json").read_text())
    st.markdown("### Current fixture research")
    st.caption(
        "Measured admitted history only. No unvalidated adjustment to player projections and no fabricated game-state probabilities."
    )
    for game in research["fixtures"]:
        with st.expander(
            f"{game['game_id']} · {game['team']} against {game['opponent']}"
        ):
            st.write(
                f"Recorded history: {game['recent_games']} recent games; pass attempts {game['pass_attempts_last3']}, carries {game['carries_last3']}. Last-eight mean margin {game['mean_margin_last8']}."
            )
            st.write(game["interpretation"])
            st.dataframe(
                pd.DataFrame(game["historical_final_margin_groups"]),
                hide_index=True,
                width="stretch",
            )
            for item in game["missing"]:
                st.caption(item)


def prepare_latest(store, cycle_id):
    """Friday/Sunday refresh from the latest admitted week, without unsealing next week."""
    from .admission import approve_snapshot, prove_schedule, validate_receipt
    from .cli import freeze_prepared
    from .forecast import prepare_next
    from .sources import fetch
    from .store import safe_id

    safe_id(cycle_id)
    policy = json.loads(POLICY.read_text())
    # No receipt outcome content may be inspected before the global settlement floor.
    time_gate(
        policy,
        policy["operational_scope"]["season"],
        policy["operational_scope"]["first_week"],
    )
    admissions = [
        validate_receipt(ROOT, p, policy)
        for p in (store.root / "sources").glob("*/operational_admission.json")
    ]
    if not admissions:
        raise ValueError(
            "No admitted results week; complete prospective settlement first"
        )
    receipt = max(admissions, key=lambda r: (r["through_week"], r["created_at"]))
    target = receipt["target_week"]
    readiness = store.root / "readiness" / cycle_id
    if readiness.exists():
        store.validate(readiness)
        return json.loads((readiness / "readiness.json").read_text())
    capture_path = receipt["capture_path"]
    cap = ROOT / capture_path
    parent = json.loads((cap / "release_manifest.json").read_text())["model_parent"][
        "path"
    ]
    try:
        proof = {}

        def confirm(path):
            proof.update(prove_schedule(ROOT, path, capture_path, policy))

        source = fetch(
            store.root / "sources" / cycle_id,
            receipt["season"],
            receipt["through_week"],
            policy,
            forecasting=True,
            schedule_ready=confirm,
        )
        approve_snapshot(ROOT, source, capture_path, policy, proof=proof)
        release = prepare_next(
            source,
            store.root / "builds" / cycle_id / "inputs",
            target,
            policy,
            "weekly-" + cycle_id,
            model_parent=parent,
        )
        manifest = json.loads((release / "manifest.json").read_text())
        freeze_prepared(store, release, manifest)
        result = {
            "status": "operational_candidate_certified_not_selected",
            "target_week": target,
            "path": str(release.relative_to(ROOT)),
            "manifest_sha256": sha(release / "manifest.json"),
            "release_id": manifest["release_id"],
        }
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        result = {
            "status": "blocked",
            "target_week": target,
            "reason": str(error),
            "reason_type": type(error).__name__,
        }
    with store.transaction():
        store.publish("readiness", cycle_id, documents={"readiness.json": result})
        store.audit("refresh_candidate_readiness", result)
    return result
