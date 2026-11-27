"""One bounded private-storage health write; never creates selections or touches quota."""

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

FILE = "selection-storage-healthcheck-v1.json"


def probe(journal):
    # Explicit PAT authentication, exact private repository and existing history validated first.
    journal.read()
    old = journal.call("GET", "/contents/" + FILE)
    content = {
        "schema": 1,
        "purpose": "private selection storage healthcheck, not a selection",
        "nonce": uuid4().hex,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    payload = {
        "message": "Verify private research selection storage",
        "content": base64.b64encode(
            json.dumps(content, sort_keys=True).encode()
        ).decode(),
    }
    if old is not None:
        payload["sha"] = old["sha"]
    journal.call("PUT", "/contents/" + FILE, payload)
    for _ in range(2):
        read = journal.call("GET", "/contents/" + FILE)
        if read is None or json.loads(base64.b64decode(read["content"])) != content:
            raise ValueError("Private storage read-back failed; no retry")
    return {
        "private": True,
        "conditional_write": True,
        "read_backs": 2,
        "selection_records_created": 0,
        "checked_at": content["checked_at"],
    }


if __name__ == "__main__":
    import os

    from .store import GitHubJournal

    print(
        json.dumps(
            probe(
                GitHubJournal(
                    os.environ.get("NFL_SELECTION_GITHUB_REPOSITORY"),
                    os.environ.get("NFL_SELECTION_GITHUB_TOKEN"),
                )
            )
        )
    )
