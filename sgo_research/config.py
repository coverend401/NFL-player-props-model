"""Explicit free research configuration; production settings are never read."""

import os
import tempfile
from pathlib import Path

from .contracts import Unavailable
from .github_quota import GitHubQuotaStore
from .store import Store


def quota_store():
    repository = os.environ.get("SGO_QUOTA_REPOSITORY")
    if repository:
        path = os.environ.get(
            "SGO_RESEARCH_STORE",
            str(Path(tempfile.gettempdir()) / "nfl-research-odds-cache.sqlite"),
        )
        return GitHubQuotaStore(repository, path)
    path = os.environ.get("SGO_RESEARCH_STORE")
    if not path or os.environ.get("SGO_PERSISTENT_VOLUME_APPROVED") != "1":
        raise Unavailable(
            "No private durable quota store configured. A verified private GitHub lifetime counter or approved persistent private volume is required."
        )
    return Store(path, persistent=True)
