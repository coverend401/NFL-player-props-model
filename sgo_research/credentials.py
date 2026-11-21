"""Research quota credential resolution. No credential-derived text is returned."""

import os

import streamlit as st

from .diagnostics import CollectionBlocked

NAME = "SGO_GITHUB_QUOTA_TOKEN"


def quota_credential():
    # Cloud root secrets are authoritative, including an explicitly empty value.
    # Do not let an older process environment value shadow an edited Cloud secret.
    try:
        present = NAME in st.secrets
        value = st.secrets.get(NAME) if present else None
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        present, value = False, None
    source = "Streamlit Secrets" if present else "environment"
    if not present:
        value = os.environ.get(NAME)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise CollectionBlocked("CONFIG_TOKEN")
    if not isinstance(value, str):
        raise CollectionBlocked("TOKEN_TYPE")
    token = value.strip()  # Only surrounding whitespace; never remove quotes/prefixes.
    if any(c in token for c in ('"', "'")):
        raise CollectionBlocked("TOKEN_QUOTES")
    if token.casefold().startswith("bearer "):
        raise CollectionBlocked("TOKEN_SCHEME")
    if any(c.isspace() for c in token):
        raise CollectionBlocked("TOKEN_WHITESPACE")
    if any(not 33 <= ord(c) <= 126 for c in token):
        raise CollectionBlocked("TOKEN_HEADER")
    # GitHub, not a guessed prefix/length/alphabet regex, decides validity.
    return token, source


def credential_status():
    try:
        _, source = quota_credential()
        return f"Quota credential: present; header-safe string; source: {source}. Acceptance is unverified until GitHub responds."
    except CollectionBlocked as error:
        return (
            "Quota credential: missing."
            if error.code == "CONFIG_TOKEN"
            else f"Quota credential local check: {error.code}. No credential content is shown."
        )
