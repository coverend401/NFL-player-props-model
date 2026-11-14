"""Private persistence and no-reset accounting; no live GitHub/provider calls."""

import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from sgo_research.client import Client
from sgo_research.contracts import Unavailable, account_limits
from sgo_research.github_quota import GitHubQuotaStore, initial_state
from tests.test_sgo_research import KEY, KICK, NOW, event, response, usage


class API:
    def __init__(self):
        self.state = initial_state()
        self.version = 1
        self.private = True
        self.conflict = 0

    def __call__(self, method, path, payload=None):
        if method == "GET" and "/contents/" not in path:
            return {"private": self.private}
        if method == "GET":
            return {
                "sha": str(self.version),
                "content": base64.b64encode(json.dumps(self.state).encode()).decode(),
            }
        if self.conflict:
            self.conflict -= 1
            self.version += 1
            return None
        if payload["sha"] != str(self.version):
            return None
        self.state = json.loads(base64.b64decode(payload["content"]))
        self.version += 1
        return {"commit": {"sha": str(self.version)}}


class PrivateQuotaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = API()
        self.store = GitHubQuotaStore(
            "example/private-quota", Path(self.temp.name) / "cache.db", api=self.api
        )
        self.body = usage()
        del self.body["data"]["rateLimits"]["per-month"]["currentIntervalEndTime"]
        self.limits = account_limits(self.body, require_end=False)

    def test_old_local_contract_still_requires_reset(self):
        with self.assertRaises(Unavailable):
            account_limits(self.body)

    def test_lifetime_counter_survives_new_client(self):
        self.store.reserve(self.limits, 16, NOW)
        again = GitHubQuotaStore(
            "example/private-quota", Path(self.temp.name) / "other.db", api=self.api
        )
        again.reserve(self.limits, 16, NOW)
        self.assertEqual(self.api.state["reserved_objects"], 32)

    def test_no_monthly_reset_even_if_provider_usage_returns_zero(self):
        self.store.reserve(self.limits, 16, NOW)
        changed = copy.deepcopy(self.limits)
        changed["per-month"]["end"] = "2099-01-01T00:00:00Z"
        self.store.reserve(changed, 16, NOW)
        self.assertEqual(self.api.state["reserved_objects"], 32)

    def test_public_and_production_repositories_rejected(self):
        self.api.private = False
        with self.assertRaises(Unavailable):
            self.store.http_slot(NOW)
        with self.assertRaises(Unavailable):
            GitHubQuotaStore(
                "coverend401/NFL-player-props-model",
                Path(self.temp.name) / "no.db",
                api=self.api,
            )

    def test_missing_corrupt_or_reset_state_rejected(self):
        for state in [
            {},
            dict(initial_state(), reserved_objects=1),
            dict(initial_state(), mode="monthly_reset"),
        ]:
            self.api.state = state
            with self.assertRaises(Unavailable):
                self.store.http_slot(NOW)

    def test_sha_conflict_retries_do_not_double_reserve(self):
        self.api.conflict = 1
        self.store.reserve(self.limits, 1, NOW)
        self.assertEqual(self.api.state["reserved_objects"], 1)
        self.assertEqual(len(self.api.state["reservations"]), 1)

    def test_repeated_conflicts_fail_closed(self):
        self.api.conflict = 9
        with self.assertRaises(Unavailable):
            self.store.reserve(self.limits, 1, NOW)
        self.assertEqual(self.api.state["reserved_objects"], 0)

    def test_quota_and_halt_persist(self):
        self.store.reserve(self.limits, 16, NOW, cap=20)
        with self.assertRaises(Unavailable):
            self.store.reserve(self.limits, 16, NOW, cap=20)
        self.store.halt("error")
        with self.assertRaises(Unavailable):
            self.store.http_slot(NOW)

    def test_rate_is_atomic_and_never_deletes_object_total(self):
        for _ in range(6):
            self.store.http_slot(NOW)
        with self.assertRaises(Unavailable):
            self.store.http_slot(NOW)

    def test_actual_shape_without_reset_supports_bounded_capture(self):
        get = Mock(side_effect=[response(self.body), response({"data": [event()]})])
        s = Client(KEY, self.store, terms_ack=True, get=get, clock=lambda: NOW).fetch(
            (NOW.replace(hour=13)).isoformat(), KICK.isoformat(), limit=1
        )
        self.assertTrue(s["authenticated_response"])
        self.assertEqual(self.api.state["reserved_objects"], 1)
        self.assertNotIn(KEY, json.dumps(self.api.state))
        self.assertNotIn("odds", json.dumps(self.api.state))


if __name__ == "__main__":
    unittest.main()
