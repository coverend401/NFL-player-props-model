"""Private durable lifetime quota; no automatic reset, keys, odds or workflows.

The separate repository must already exist and be private. This module never
creates it or bootstraps missing state. Contents API SHA checks make updates
atomic; conflicts retry only the GitHub transaction, never the odds request.
"""

import base64
import json
import os
import re
import subprocess
import uuid
from datetime import timedelta

import requests

from .contracts import Unavailable, utc
from .store import Store

STATE_FILE = "quota.json"
MODE = "lifetime_no_reset_v1"


def initial_state():
    return {
        "schema": 1,
        "mode": MODE,
        "reserved_objects": 0,
        "reservations": [],
        "calls": [],
        "halt": None,
    }


class GitHubAPI:
    def __init__(self, token=None):
        self.token = token or os.environ.get("SGO_GITHUB_QUOTA_TOKEN")

    def __call__(self, method, path, payload=None):
        if self.token:
            try:
                r = requests.request(
                    method,
                    "https://api.github.com/" + path,
                    headers={
                        "Authorization": "Bearer " + self.token,
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json=payload,
                    timeout=(5, 20),
                    allow_redirects=False,
                )
                if r.status_code == 409:
                    return None
                if r.status_code not in [200, 201]:
                    raise Unavailable("Private quota GitHub request failed")
                return r.json()
            except (requests.RequestException, ValueError):
                raise Unavailable(
                    "Private quota service unavailable; no odds request"
                ) from None
        # Local Codex uses existing gh authentication without reading/logging a token.
        args = ["gh", "api", "--method", method, path]
        if payload is not None:
            args += ["--input", "-"]
        try:
            r = subprocess.run(
                args,
                input=json.dumps(payload) if payload is not None else None,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise Unavailable("Private quota authentication unavailable") from None
        if r.returncode:
            if "HTTP 409" in r.stderr:
                return None
            raise Unavailable("Private quota GitHub request failed; no odds request")
        try:
            return json.loads(r.stdout)
        except ValueError:
            raise Unavailable("Invalid private quota response") from None


class GitHubQuotaStore:
    requires_interval_end = False
    persistent = True

    def __init__(self, repository, cache_path, *, api=None):
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository or "")
            or repository.casefold() == "coverend401/nfl-player-props-model"
        ):
            raise Unavailable(
                "A separate private research quota repository is required"
            )
        self.repository = repository
        self.api = api or GitHubAPI()
        self.cache = Store(cache_path, persistent=False)
        self._read()  # Missing/public/uninitialised state never becomes a new budget.

    def _read(self):
        meta = self.api("GET", "repos/" + self.repository)
        if not isinstance(meta, dict) or meta.get("private") is not True:
            raise Unavailable("Quota repository must be private")
        body = self.api("GET", f"repos/{self.repository}/contents/{STATE_FILE}")
        try:
            state = json.loads(base64.b64decode(body["content"], validate=False))
            if (
                state.get("schema") != 1
                or state.get("mode") != MODE
                or type(state.get("reserved_objects")) is not int
                or not 0 <= state["reserved_objects"] <= 2000
            ):
                raise ValueError
            if not isinstance(state.get("calls"), list) or not isinstance(
                state.get("reservations"), list
            ):
                raise TypeError
            for t in state["calls"]:
                utc(t)
            if (
                sum(r["objects"] for r in state["reservations"])
                != state["reserved_objects"]
            ):
                raise ValueError
            if any(
                type(r["objects"]) is not int or not 1 <= r["objects"] <= 16
                for r in state["reservations"]
            ):
                raise ValueError
            for r in state["reservations"]:
                utc(r["at"])
            return state, body["sha"]
        except (ValueError, TypeError, KeyError, AttributeError):
            raise Unavailable(
                "Private quota state invalid/missing; no automatic reset"
            ) from None

    def _update(self, mutate):
        for _ in range(3):
            state, sha = self._read()
            mutate(state)
            body = {
                "message": "Reserve research API quota (no odds or credentials)",
                "sha": sha,
                "content": base64.b64encode(
                    json.dumps(state, sort_keys=True, allow_nan=False).encode()
                ).decode(),
            }
            if (
                self.api("PUT", f"repos/{self.repository}/contents/{STATE_FILE}", body)
                is not None
            ):
                return
        raise Unavailable("Private quota write conflict; no odds request")

    def http_slot(self, now):
        def mutate(s):
            if s["halt"]:
                raise Unavailable("Collector halted; manual review required")
            if sum(utc(t) > now - timedelta(minutes=1) for t in s["calls"]) >= 6:
                raise Unavailable("Conservative six-request/minute limit reached")
            # Keep only rate-accounting calls; lifetime object total is never pruned.
            s["calls"] = [t for t in s["calls"] if utc(t) > now - timedelta(days=31)]
            s["calls"].append(now.isoformat())

        self._update(mutate)

    def reserve(self, limits, objects, now, *, cap=2000, headroom=200):
        if (
            type(objects) is not int
            or not 1 <= objects <= 16
            or not 1 <= cap <= 2000
            or headroom < 200
        ):
            raise Unavailable("Invalid lifetime quota request")
        month = limits["per-month"]
        if (
            type(month["max_entities"]) is not int
            or type(month["used_entities"]) is not int
        ):
            raise Unavailable("Monthly usage is not established")

        def mutate(s):
            if s["halt"]:
                raise Unavailable("Collector halted")
            ceiling = min(cap, month["max_entities"] - headroom, 2500 - headroom)
            if month["used_entities"] + s["reserved_objects"] + objects > ceiling:
                raise Unavailable(
                    "Conservative lifetime/free monthly budget reached; no reset"
                )
            for name, seconds in [
                ("per-minute", 60),
                ("per-hour", 3600),
                ("per-day", 86400),
                ("per-month", 31 * 86400),
            ]:
                rule = limits.get(name, {})
                for maximum, used, local in [
                    (
                        "max_requests",
                        "used_requests",
                        sum(
                            utc(t) > now - timedelta(seconds=seconds)
                            for t in s["calls"]
                        ),
                    ),
                    (
                        "max_entities",
                        "used_entities",
                        sum(
                            r["objects"]
                            for r in s["reservations"]
                            if utc(r["at"]) > now - timedelta(seconds=seconds)
                        ),
                    ),
                ]:
                    if type(rule.get(maximum)) is int and (
                        type(rule.get(used)) is not int
                        or rule[used]
                        + local
                        + (1 if maximum == "max_requests" else objects)
                        > rule[maximum]
                    ):
                        raise Unavailable("Account interval allowance insufficient")
            s["reserved_objects"] += objects
            s["reservations"].append(
                {"id": uuid.uuid4().hex, "at": now.isoformat(), "objects": objects}
            )

        self._update(mutate)

    def halt(self, reason):
        self._update(lambda s: s.update(halt="manual_review_required"))

    def cached(self, key, now, ttl=600):
        return self.cache.cached(key, now, ttl)

    def save_cache(self, key, payload, now):
        self.cache.save_cache(key, payload, now)

    def freeze_paper(self, *a, **kw):
        raise Unavailable("Paper archival remains disabled")

    def settle(self, *a, **kw):
        raise Unavailable("Settlement remains disabled")
