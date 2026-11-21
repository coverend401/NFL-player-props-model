"""Read-only weekly status; never starts a job or modifies a release."""

import json

import pandas as pd
import streamlit as st

from .store import ROOT, Store


def render():
    st.markdown("### Weekly Learning")
    root = ROOT / "weekly_learning_state"
    reports = sorted((root / "cycles").glob("*/report.json"))
    if not reports:
        st.info(
            "No completed learning cycles. The certified forecast remains the champion."
        )
        return
    try:
        ordered = sorted(
            reports, key=lambda p: json.loads(p.read_text())["completed_at"]
        )
        attempt = ordered[-1]
        Store(root).validate(attempt.parent)
        attempt_report = json.loads(attempt.read_text())
        completed = [
            p
            for p in ordered
            if json.loads(p.read_text()).get("status")
            in [None, "completed", "completed_with_missing"]
        ]
        latest = completed[-1] if completed else attempt
        Store(root).validate(latest.parent)
        report = json.loads(latest.read_text())
    except (OSError, ValueError, KeyError):
        st.error(
            "Learning report failed integrity checks; certified forecasts unchanged."
        )
        return
    from .operations import preflight

    status = {}
    try:
        status = preflight(Store(root), record_capture=False)
        if not status.get("time_gate_open"):
            st.info(status.get("reason", status["status"]))
        else:
            st.caption(
                "Settlement time gate open; independent finality/source checks still required."
            )
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        st.caption(
            "Operational preflight unavailable; last certified learning report retained."
        )
    if attempt_report.get("status") in [
        "waiting_for_settlement",
        "blocked_results_integrity",
    ]:
        st.warning(
            "Latest prospective attempt: "
            + attempt_report.get("reason", attempt_report["status"])
        )
    readiness = root / "readiness" / report["cycle_id"]
    if readiness.exists():
        try:
            Store(root).validate(readiness)
            report["next_slate"] = json.loads(
                (readiness / "readiness.json").read_text()
            )
        except (OSError, ValueError, KeyError):
            st.warning(
                "Forecast readiness record failed integrity validation; no readiness claim."
            )
    st.caption(f"Last cycle: {report['cycle_id']} · {report['completed_at']}")
    st.write(
        "Champion: "
        + report.get(
            "champion_release",
            report.get("capture", {}).get("release_id", "unchanged certified Stage 1A"),
        )
    )
    if report["mode"] == "historical_dry_run":
        st.warning(
            "Historical replay, not genuinely captured pregame performance. Previously inspected development data cannot justify promotion."
        )
    if report.get("status") == "blocked_before_results_access":
        st.warning(report["reason"])
        return
    metrics = report.get("metrics", [])
    st.dataframe(
        pd.DataFrame([r for r in metrics if r["group"] == "market"]),
        hide_index=True,
        width="stretch",
    )
    if report.get("game_script_brier") is not None:
        st.caption(
            f"Experimental final-margin category Brier: {report['game_script_brier']:.4f}; not in-game lead/trail accuracy."
        )
    candidate = report.get("candidate", {})
    st.write(
        "Candidate decision: " + candidate.get("decision", "no candidate decision")
    )
    for reason in candidate.get("reasons", []):
        st.caption(reason)
    readiness = report.get("next_slate", {})
    if readiness.get("status") in {
        "certified_candidate_ready_for_selection",
        "operational_candidate_certified_not_selected",
    }:
        try:
            selected = ROOT / "weekly_learning_state/selected_research.json"
            active = json.loads(
                (
                    selected
                    if selected.exists()
                    else ROOT / "research_active_inference.json"
                ).read_text()
            )
            if active.get("manifest_sha256") == readiness.get("manifest_sha256"):
                readiness = {
                    **readiness,
                    "status": "certified_research_forecast_selected",
                }
        except (OSError, ValueError):
            pass
    source = readiness.get("source_path", readiness.get("path"))
    if source:
        try:
            manifest = json.loads((ROOT / source / "manifest.json").read_text())
            if not any(
                pd.Timestamp.now(tz="UTC") < pd.Timestamp(t) - pd.Timedelta(minutes=60)
                for t in manifest["game_kickoffs"].values()
            ):
                readiness = {
                    **readiness,
                    "status": "expired_readiness_from_previous_cycle",
                }
                st.warning(
                    "The prior readiness report has expired. No current slate certification is claimed."
                )
        except (OSError, ValueError, KeyError):
            readiness = {"status": "readiness_source_unavailable"}
    st.write("Next slate: " + readiness.get("status", "unknown"))
    if report.get("week12_readiness") and not status.get("capture_valid"):
        st.warning(
            "Week 12: " + report["week12_readiness"].get("reason", "not yet ready")
        )
    with st.expander("Recurring errors and evidence limits"):
        try:
            observations = pd.read_parquet(latest.parent / "reconciled.parquet")
            labels = observations.hypotheses.map(json.loads).explode().dropna()
            counts = (
                labels.value_counts()
                .rename_axis("Observed diagnostic / hypothesis")
                .reset_index(name="Player-market records")
            )
            st.dataframe(counts.head(6), hide_index=True, width="stretch")
            st.caption(
                "Counts overlap across props and players; they are not independent causal cases."
            )
        except (OSError, ValueError, KeyError):
            st.caption(
                "Detailed diagnostic observations are unavailable for this cycle."
            )
        st.dataframe(
            pd.DataFrame([r for r in metrics if r["group"] in ["team", "position"]]),
            hide_index=True,
            width="stretch",
        )
        for note in report.get("data_gaps", []):
            st.caption(note)
        st.caption(
            "Positive bias means overprediction. Attributions are associative evidence, not proven injury or coaching causes. Forecasts and results are stored separately; no betting profit is inferred."
        )
    with st.expander("Candidate comparison and provenance"):
        st.json(
            {
                "status_counts": report.get("status_counts"),
                "candidate": candidate,
                "source_manifest_sha256": report.get("source_manifest_sha256"),
                "next_slate": report.get("next_slate"),
            }
        )

    from script_adjustment.ui import render_weekly_status

    render_weekly_status(root)
