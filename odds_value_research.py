"""Separate password-protected research entrypoint; never the production app."""

from pathlib import Path

import pandas as pd
import streamlit as st

from release_utils import resolve_release
from research_access import require_access
from research_platform.r8 import render
from research_platform.ui import CSS

st.set_page_config(
    page_title="NFL Betting Intelligence · r8.1", page_icon="🏈", layout="centered"
)
st.markdown(CSS, unsafe_allow_html=True)
require_access()
root = Path(__file__).resolve().parent
try:
    directory, release = resolve_release(root)
    slate = pd.read_parquet(directory / "slate.parquet")
except (OSError, ValueError, KeyError, TypeError):
    st.error("Approved release unavailable. Research comparison disabled.")
    st.stop()
render(slate, release)
