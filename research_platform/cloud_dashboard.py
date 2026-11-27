"""Authenticated runtime-profile route for the unchanged research entrypoint."""

import pandas as pd
import streamlit as st

from .cloud_runtime import admit
from .r8 import render


def render_authenticated():
    from .weekly_serving import selected

    try:
        weekly = selected()
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        st.error(
            "Selected weekly serving release failed admission. No stale slate is substituted."
        )
        st.stop()
    if weekly is not None:
        from .weekly_ui import render as render_weekly

        render_weekly(*weekly)
        st.stop()
    try:
        directory, release = admit()
        slate = pd.read_parquet(directory / "slate.parquet")
    except (OSError, ValueError, KeyError, TypeError):
        st.error(
            "Approved Cloud serving release unavailable. Admission remains blocked; use the authenticated diagnostic."
        )
        st.stop()
    from .weekly_serving import CANDIDATES
    from .weekly_serving import admit as admit_weekly

    available = {
        p: d for p, d in CANDIDATES.items() if (p / "certificate.json").exists()
    }
    if available:
        with st.expander(
            "Certified Week 12 candidate — review before activation", expanded=False
        ):
            preview_profile = st.radio(
                "Candidate bundle",
                list(available),
                format_func=lambda p: (
                    "Remaining Week 12 fixtures — refreshed 27 November"
                    if "remaining" in p.name
                    else "Original full Week 12 — frozen 24 November"
                ),
            )
            preview = st.checkbox(
                "Preview Week 12 (not selected; freezing disabled)",
                key="weekly_candidate_preview",
            )
        if preview:
            try:
                frame, fixtures, candidate = admit_weekly(
                    preview_profile, available[preview_profile]
                )
            except (OSError, ValueError, KeyError, TypeError, AssertionError):
                st.error(
                    "Week 12 candidate serving admission failed. No preview or pricing is loaded."
                )
                st.stop()
            from .weekly_ui import render as render_weekly

            render_weekly(frame, fixtures, {**candidate, "preview_only": True})
            st.stop()
    st.caption(
        "Certified serving runtime: certifi 2026.11.20 · frozen training provenance unchanged"
    )
    render(slate, release)
    # The legacy source is deliberately immutable for its original certificate.
    # Its old-runtime resolver must not run after this independently admitted view.
    st.stop()
