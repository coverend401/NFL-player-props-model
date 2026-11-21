"""One in-memory diagnostic sequence, never live GitHub or provider requests."""

import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

from sgo_research.contracts import STAT_MARKETS, Unavailable
from sgo_research.diagnostic_client import DiagnosticClient
from sgo_research.github_quota import GitHubQuotaStore
from tests import test_sunday_recovery as recovery_fixtures
from tests.test_sgo_research import GID, KEY, KICK, NOW, event, response, usage


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        _, self.api, _state = recovery_fixtures.RecoveryTests().setup_store()
        self.api.state["halt"] = None
        self.baseline = copy.deepcopy(self.api.state)
        self.store = GitHubQuotaStore(
            "example/private", Path(self.tmp.name) / "cache.sqlite", api=self.api
        )
        self.now = NOW
        self.get = Mock(
            side_effect=[
                response(usage()),
                response({"data": [event()]}),
                response({"data": [event()]}),
            ]
        )
        self.client = DiagnosticClient(
            KEY, self.store, terms_ack=True, get=self.get, clock=lambda: self.now
        )
        self.spec = {
            "game_id": GID,
            "eventID": event()["eventID"],
            "kickoff": KICK.isoformat(),
        }

    def discover(self):
        return self.client.discover(
            NOW.isoformat(), (NOW + timedelta(hours=8)).isoformat(), ["fanduel"]
        )

    def prices(self):
        return self.client.prices([self.spec], ["fanduel"], ["SYNTH_PLAYER_1_NFL"])

    def test_three_calls_two_objects_and_exact_filters(self):
        self.discover()
        self.prices()
        self.assertEqual(self.get.call_count, 3)
        self.assertEqual(self.client.provider_calls, 3)
        self.assertEqual(self.api.state["reserved_objects"], 83)
        self.assertEqual(
            self.api.state["reservations"][:11], self.baseline["reservations"]
        )
        self.assertEqual(len(self.api.state["reservations"]), 13)
        discovery = self.get.call_args_list[1].kwargs["params"]
        price = self.get.call_args_list[2].kwargs["params"]
        self.assertEqual(discovery["limit"], 1)
        self.assertNotIn("cursor", discovery)
        self.assertEqual(price["eventIDs"], self.spec["eventID"])
        self.assertEqual(price["playerID"], "SYNTH_PLAYER_1_NFL")
        self.assertEqual(len(price["oddID"].split(",")), len(STAT_MARKETS))
        self.assertEqual(price["bookmakerID"], "fanduel")
        self.assertEqual(price["includeOpposingOdds"], "true")
        self.assertEqual(price["includeAltLines"], "false")
        with self.assertRaises(Unavailable):
            self.prices()
        with self.assertRaises(Unavailable):
            self.discover()
        self.assertEqual(self.get.call_count, 3)

    def test_halt_blocks_account_discovery_and_cached_account(self):
        self.api.state["halt"] = "manual_review_required"
        before = copy.deepcopy(self.api.state)
        with self.assertRaises(Unavailable):
            self.discover()
        self.get.assert_not_called()
        self.assertEqual(self.api.state, before)

    def test_new_halt_blocks_reused_account_without_http(self):
        self.discover()
        self.api.state["halt"] = "manual_review_required"
        before = copy.deepcopy(self.api.state)
        with self.assertRaises(Unavailable):
            self.prices()
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.api.state, before)

    def test_slow_reservation_cannot_use_stale_account(self):
        self.discover()
        original = self.store.reserve

        def slow(*args, **kwargs):
            original(*args, **kwargs)
            self.now += timedelta(seconds=31)

        self.store.reserve = slow
        with self.assertRaisesRegex(Unavailable, "expired before HTTP"):
            self.prices()
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.api.state["reserved_objects"], 83)
        self.assertEqual(
            self.api.state["reservations"][:11], self.baseline["reservations"]
        )

    def test_expired_account_does_not_trigger_fourth_call(self):
        self.discover()
        self.now += timedelta(seconds=31)
        with self.assertRaisesRegex(Unavailable, "expired"):
            self.prices()
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.api.state["reserved_objects"], 82)

    def test_unknown_player_or_wrong_fixture_no_price_request(self):
        self.discover()
        self.spec["game_id"] = "2026_09_KC_ARI"
        with self.assertRaises(Unavailable):
            self.prices()
        self.assertEqual(self.get.call_count, 2)

    def test_pagination_and_unknown_event_fail_before_http(self):
        with self.assertRaises(Unavailable):
            self.client.discover(
                NOW.isoformat(),
                (NOW + timedelta(hours=8)).isoformat(),
                ["fanduel"],
                cursor="synthetic",
            )
        with self.assertRaises(Unavailable):
            self.prices()
        self.get.assert_not_called()
