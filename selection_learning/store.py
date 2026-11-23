"""Private append-only selection journal, atomic GitHub Contents CAS; no quota access."""

import base64
import json
import re

import requests

from sgo_research.github_quota import QuotaBearerAuth

from .engine import digest

FILE = "selection-journal-v1.json"
MAX_BYTES = 900_000


class StorageError(ValueError):
    pass


def initial():
    return {"schema": 1, "events": []}


def validate(state):
    if (
        set(state) != {"schema", "events"}
        or state["schema"] != 1
        or not isinstance(state["events"], list)
    ):
        raise StorageError("Unsupported private selection journal")
    previous = None
    ids = set()
    for e in state["events"]:
        body = {k: v for k, v in e.items() if k != "sha256"}
        if (
            set(body) != {"kind", "id", "at", "payload", "previous_sha256"}
            or e["kind"] not in ["freeze", "settlement", "weekly_report"]
            or body["previous_sha256"] != previous
            or e["sha256"] != digest(body)
            or (e["kind"], e["id"]) in ids
        ):
            raise StorageError("Selection history integrity failure")
        ids.add((e["kind"], e["id"]))
        previous = e["sha256"]
    return state


def append(state, kind, identity, at, payload):
    validate(state)
    prior = next(
        (e for e in state["events"] if e["kind"] == kind and e["id"] == identity), None
    )
    if prior:
        if prior["payload"] != payload:
            raise StorageError("Immutable selection record already exists")
        return state
    body = {
        "kind": kind,
        "id": identity,
        "at": str(at),
        "payload": payload,
        "previous_sha256": state["events"][-1]["sha256"] if state["events"] else None,
    }
    result = {
        "schema": 1,
        "events": [*state["events"], {**body, "sha256": digest(body)}],
    }
    validate(result)
    return result


class GitHubJournal:
    """Requires an owner-configured private repository separate from quota/model repos."""

    def __init__(self, repository, token, *, request=None):
        if (
            not isinstance(repository, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or repository.lower()
            in {
                "coverend401/nfl-props-research-quota",
                "coverend401/nfl-player-props-model",
            }
        ):
            raise StorageError(
                "Configure a separate private selection repository; quota and model repositories are forbidden"
            )
        if (
            not isinstance(token, str)
            or token != token.strip()
            or not token
            or any(c.isspace() for c in token)
            or token[0] in "\"'"
        ):
            raise StorageError("Private selection token missing or malformed")
        self.repository, self._token, self._request = (
            repository,
            token,
            request or requests.request,
        )

    def call(self, method, suffix="", payload=None):
        try:
            r = self._request(
                method,
                "https://api.github.com/repos/" + self.repository + suffix,
                auth=QuotaBearerAuth(self._token),
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json=payload,
                timeout=(5, 20),
                allow_redirects=False,
                stream=True,
            )
            with r:
                if (
                    r.status_code == 404
                    and method == "GET"
                    and suffix.startswith("/contents/")
                ):
                    return None
                if r.status_code not in [200, 201]:
                    reason = {
                        401: "token rejected",
                        403: "permission denied",
                        404: "repository unavailable",
                        409: "concurrent update; reload before retry",
                        422: "update rejected; reload before retry",
                    }.get(r.status_code, "GitHub unavailable")
                    raise StorageError("Private selection storage: " + reason)
                raw = bytearray()
                for block in r.iter_content(65536):
                    raw.extend(block)
                    if len(raw) > 2 * MAX_BYTES:
                        raise StorageError("Private selection response exceeds bound")
                if self._token.encode() in raw:
                    raise StorageError("Unsafe private selection response")
                return json.loads(raw)
        except requests.RequestException:
            raise StorageError(
                "Private selection storage network failure; no retry"
            ) from None

    def read(self):
        metadata = self.call("GET")
        if (
            metadata.get("private") is not True
            or metadata.get("full_name", "").lower() != self.repository.lower()
        ):
            raise StorageError(
                "Selection repository is not the expected private repository"
            )
        body = self.call("GET", "/contents/" + FILE)
        if body is None:
            return initial(), None
        if (
            body.get("encoding") != "base64"
            or body.get("size", MAX_BYTES + 1) > MAX_BYTES
        ):
            raise StorageError("Unsupported private selection file")
        raw = base64.b64decode(body["content"])
        if len(raw) > MAX_BYTES:
            raise StorageError("Private selection journal full; no history pruned")
        return validate(json.loads(raw)), body["sha"]

    def write(self, before, after, sha):
        validate(before)
        validate(after)
        if after["events"][: len(before["events"])] != before["events"]:
            raise StorageError("Cannot modify historical selection records")
        if before == after:
            return
        raw = json.dumps(after, sort_keys=True, allow_nan=False).encode()
        if len(raw) > MAX_BYTES:
            raise StorageError(
                "Private selection journal full; archive requires owner review"
            )
        payload = {
            "message": "Append frozen research selection records",
            "content": base64.b64encode(raw).decode(),
        }
        if sha is not None:
            payload["sha"] = sha
        self.call("PUT", "/contents/" + FILE, payload)
        persisted, _ = self.read()
        # A concurrent append is acceptable only if our whole prefix persists.
        if (
            persisted != after
            and persisted["events"][: len(after["events"])] != after["events"]
        ):
            raise StorageError("Selection persistence verification failed")
