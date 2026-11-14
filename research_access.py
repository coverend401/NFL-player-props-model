"""Separate preview authentication. No production password/settings are read."""

import hmac
import os

import streamlit as st


def secret(name):
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets.get(name)
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return None


def require_access():
    password = secret("RESEARCH_PREVIEW_PASSWORD")
    if not password:
        st.warning(
            "Research preview locked: configure a separate RESEARCH_PREVIEW_PASSWORD secret. Do not reuse or change production authentication."
        )
        st.stop()
    if st.session_state.get("research_authenticated"):
        return
    with st.form("research_access"):
        entered = st.text_input(
            "Research preview password", type="password", key="research_password"
        )
        submit = st.form_submit_button("Unlock research preview")
    if submit and hmac.compare_digest(str(entered), str(password)):
        st.session_state["research_authenticated"] = True
        st.rerun()
    elif submit:
        st.error("Incorrect research password.")
    st.stop()
