"""Local preview only: streamlit run odds_value_research.py. No hosting authorised."""

from pathlib import Path

import pandas as pd
import streamlit as st

from release_utils import resolve_release
from sgo_research.ui import render

st.set_page_config(page_title="NFL research odds", layout="centered")
root = Path(__file__).resolve().parent
try:
    directory, release = resolve_release(root)
    slate = pd.read_parquet(directory / "slate.parquet")
except (OSError, ValueError, KeyError, TypeError):
    st.error("Approved release unavailable. Research comparison disabled.")
    st.stop()
render(slate, release)
