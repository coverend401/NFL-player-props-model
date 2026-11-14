"""Manual, explicitly authorised private-repository bootstrap and real CAS proof.

Never resets an existing budget. Never sends a SportsGameOdds request. No keys,
account details, odds, model files or production files are written to GitHub.
"""

import argparse
import base64
import json
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sgo_research.contracts import Unavailable
from sgo_research.github_quota import (
    STATE_FILE,
    GitHubAPI,
    GitHubQuotaStore,
    initial_state,
)


def initialise(repository, cache_path, *, api=None):
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository or "")
        or repository.casefold() == "coverend401/nfl-player-props-model"
    ):
        raise Unavailable("Separate private quota repository required")
    api = api or GitHubAPI()
    meta = api("GET", "repos/" + repository)
    if meta.get("private") is not True:
        raise Unavailable("Quota repository must be private")
    files = api("GET", f"repos/{repository}/contents")
    if not isinstance(files, list) or any(
        f.get("name") not in ["README.md", STATE_FILE] for f in files
    ):
        raise Unavailable(
            "Expected a dedicated private counter repository containing only README/counter"
        )
    if not any(f.get("name") == STATE_FILE for f in files):
        result = api(
            "PUT",
            f"repos/{repository}/contents/{STATE_FILE}",
            {
                "message": "Initialise lifetime research counter; no credentials or odds",
                "content": base64.b64encode(
                    json.dumps(initial_state()).encode()
                ).decode(),
            },
        )
        if result is None:
            raise Unavailable("Concurrent initialisation; stop without resetting")
    store = GitHubQuotaStore(repository, cache_path, api=api)
    state, sha = store._read()
    if state.get("conditional_updates_verified") is True:
        return {
            "private": True,
            "conditional_updates_verified": True,
            "existing_budget_preserved": True,
            "reserved_objects": state["reserved_objects"],
        }
    if state["reserved_objects"] or state["calls"]:
        raise Unavailable("Unverified counter already in use; manual review required")
    nonce = uuid.uuid4().hex
    state["verification_nonce"] = nonce
    first = api(
        "PUT",
        f"repos/{repository}/contents/{STATE_FILE}",
        {
            "message": "Verify private quota conditional persistence",
            "sha": sha,
            "content": base64.b64encode(json.dumps(state).encode()).decode(),
        },
    )
    if first is None:
        raise Unavailable("Concurrent verification; stop")
    stale = dict(state, verification_nonce="stale-write-must-be-rejected")
    conflict = api(
        "PUT",
        f"repos/{repository}/contents/{STATE_FILE}",
        {
            "message": "Safety test: stale SHA must be rejected",
            "sha": sha,
            "content": base64.b64encode(json.dumps(stale).encode()).decode(),
        },
    )
    if conflict is not None:
        raise Unavailable(
            "Conditional write safety failed; no provider request permitted"
        )
    check = GitHubQuotaStore(repository, cache_path, api=api)
    observed, _ = check._read()
    if (
        observed.get("verification_nonce") != nonce
        or observed["reserved_objects"]
        or observed["calls"]
    ):
        raise Unavailable("Persistence/CAS proof failed")

    def verify(s):
        if s.get("verification_nonce") != nonce or s["reserved_objects"] or s["calls"]:
            raise Unavailable("Counter changed during verification")
        s["conditional_updates_verified"] = True
        s["conditional_updates_verified_at"] = datetime.now(UTC).isoformat()

    check._update(verify)
    final, _ = GitHubQuotaStore(repository, cache_path, api=api)._read()
    if final.get("conditional_updates_verified") is not True:
        raise Unavailable("Private proof did not persist")
    return {
        "private": True,
        "conditional_updates_verified": True,
        "stale_sha_rejected": True,
        "new_client_readback_verified": True,
        "reserved_objects": 0,
        "sports_odds_requests": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repository", required=True)
    p.add_argument("--cache-path", type=Path, required=True)
    p.add_argument("--initialise-and-verify", action="store_true", required=True)
    a = p.parse_args()
    try:
        print(json.dumps(initialise(a.repository, a.cache_path), indent=2))
    except Unavailable as error:
        print(str(error))
        raise SystemExit(2) from None
