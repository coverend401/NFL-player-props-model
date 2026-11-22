"""Authenticated runtime-profile route for the unchanged research entrypoint."""

import pandas as pd
import streamlit as st

from .cloud_runtime import admit
from .r8 import render


def render_authenticated():
    try:
        directory, release = admit()
        slate = pd.read_parquet(directory / "slate.parquet")
    except (OSError, ValueError, KeyError, TypeError):
        st.error(
            "Approved Cloud serving release unavailable. Admission remains blocked; use the authenticated diagnostic."
        )
        st.stop()
    st.caption(
        "Certified serving runtime: certifi 2026.11.20 · frozen training provenance unchanged"
    )
    render(slate, release)
    # The legacy source is deliberately immutable for its original certificate.
    # Its old-runtime resolver must not run after this independently admitted view.
    st.stop()
