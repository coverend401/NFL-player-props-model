"""Local preview only: streamlit run odds_value_research.py. No hosting authorised."""

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from matchup_research.ui import render as render_matchups
from release_utils import resolve_release
from research_access import require_access, secret
from sgo_research.market_ui import render

st.set_page_config(page_title="NFL research odds", layout="centered")
require_access()
# Explicit research-only secrets; production secrets/configuration are never copied.
for setting in (
    "SPORTSGAMEODDS_API_KEY",
    "SGO_QUOTA_REPOSITORY",
    "SGO_GITHUB_QUOTA_TOKEN",
    "SGO_PRIVATE_CACHE_TERMS_ACK",
    "SGO_OBJECT_CAP",
):
    value = secret(setting)
    if value is not None:
        os.environ[setting] = str(value)
root = Path(__file__).resolve().parent
try:
    directory, release = resolve_release(root)
    slate = pd.read_parquet(directory / "slate.parquet")
except (OSError, ValueError, KeyError, TypeError):
    st.error("Approved release unavailable. Research comparison disabled.")
    st.stop()
st.caption(
    f"Sunday research preview r2 · baseline release {release['release_id']} · no production changes"
)
odds_tab, script_tab = st.tabs(["Market Intelligence", "Game-Script Intelligence"])
with odds_tab:
    render(slate, release)
with script_tab:
    render_matchups(release)
