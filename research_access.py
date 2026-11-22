"""Separate preview authentication. No production password/settings are read."""

import hashlib
import hmac
import importlib.metadata
import os
from pathlib import Path

import streamlit as st


def secret(name):
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets.get(name)
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return None


def require_access(*, diagnostic_preflight=None):
    password = secret("RESEARCH_PREVIEW_PASSWORD")
    if not password:
        st.warning(
            "Research preview locked: configure a separate RESEARCH_PREVIEW_PASSWORD secret. Do not reuse or change production authentication."
        )
        st.stop()
    proof = hmac.new(
        str(password).encode(), b"research-preview-session", hashlib.sha256
    ).hexdigest()
    if hmac.compare_digest(
        str(st.session_state.get("research_authenticated", "")), proof
    ):
        # Preserve the certified entrypoint bytes. Only that authenticated script
        # can select the explicitly recertified serving route; other callers and
        # the original dependency environment retain their existing behaviour.
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        from research_platform.startup_diagnostics import render

        context = get_script_run_ctx()
        root = Path(__file__).resolve().parent
        if (
            diagnostic_preflight is None
            and context is not None
            and Path(context.main_script_path).resolve()
            == root / "odds_value_research.py"
            and (root / "research_cloud_active.json").is_file()
            and importlib.metadata.version("certifi") != "2026.10.23"
        ):
            from research_platform.cloud_dashboard import render_authenticated
            from research_platform.cloud_runtime import preflight

            render(preflight_check=preflight)
            render_authenticated()
            st.stop()
        render(preflight_check=diagnostic_preflight)
        return
    with st.form("research_access"):
        entered = st.text_input(
            "Research preview password", type="password", key="research_password"
        )
        submit = st.form_submit_button("Unlock research preview")
    if submit and hmac.compare_digest(str(entered), str(password)):
        st.session_state["research_authenticated"] = proof
        st.rerun()
    elif submit:
        st.error("Incorrect research password.")
    st.stop()
