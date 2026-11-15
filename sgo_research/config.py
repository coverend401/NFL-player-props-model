"""Explicit free research configuration; production settings are never read."""

import os
import tempfile
from pathlib import Path

from research_access import secret

from .contracts import Unavailable
from .diagnostics import CollectionBlocked
from .github_quota import GitHubAPI, GitHubQuotaStore
from .store import Store


def quota_store():
    repository = secret("SGO_QUOTA_REPOSITORY")
    if repository:
        if not isinstance(repository, str):
            raise CollectionBlocked("CONFIG_REPOSITORY")
        path = os.environ.get(
            "SGO_RESEARCH_STORE",
            str(Path(tempfile.gettempdir()) / "nfl-research-odds-cache.sqlite"),
        )
        token = secret("SGO_GITHUB_QUOTA_TOKEN")
        if not isinstance(token, str) or not token.strip():
            raise CollectionBlocked("CONFIG_TOKEN")
        return GitHubQuotaStore(repository.strip(), path, api=GitHubAPI(token.strip()))
    path = os.environ.get("SGO_RESEARCH_STORE")
    if not path or os.environ.get("SGO_PERSISTENT_VOLUME_APPROVED") != "1":
        raise Unavailable(
            "No private durable quota store configured. A verified private GitHub lifetime counter or approved persistent private volume is required."
        )
    return Store(path, persistent=True)
