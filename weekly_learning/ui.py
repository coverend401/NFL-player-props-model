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
        latest = ordered[-1]
        Store(root).validate(latest.parent)
        report = json.loads(latest.read_text())
    except (OSError, ValueError, KeyError):
        st.error(
            "Learning report failed integrity checks; certified forecasts unchanged."
        )
        return
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
    st.write("Next slate: " + report.get("next_slate", {}).get("status", "unknown"))
    if report.get("week12_readiness"):
        st.warning(
            "Week 12: " + report["week12_readiness"].get("reason", "not yet ready")
        )
    with st.expander("Recurring errors and evidence limits"):
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
