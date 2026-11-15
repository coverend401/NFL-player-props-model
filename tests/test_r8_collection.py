"""Bounded event-specific transport and real UI regressions; no live API requests."""

import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

from research_platform.coverage8 import (
    collect8,
    explain_error,
    identity_players,
    match_event,
    plan8,
    price_merge,
    private_records,
    record_price,
    state8,
    two8,
    write_audit,
)
from research_platform.slate import model_candidates
from sgo_research.client import redact_events
from sgo_research.contracts import Unavailable
from sgo_research.event_client import EventClient
from sgo_research.github_quota import GitHubQuotaStore
from tests.test_r7_research import fixture_set, scoped_snapshot
from tests.test_sgo_private_quota import API
from tests.test_sgo_research import (
    GID,
    KEY,
    KICK,
    NOW,
    REL,
    event,
    response,
    slate,
    usage,
)

BOOKS = ["fanduel", "draftkings", "betmgm"]


class EventTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.api = API()
        self.store = GitHubQuotaStore(
            "example/private-quota", Path(self.tmp.name) / "cache.db", api=self.api
        )
        self.get = Mock()
        self.time = NOW
        self.client = EventClient(
            KEY,
            self.store,
            terms_ack=True,
            get=self.get,
            clock=lambda: self.time,
            sleep=self.advance,
        )

    def advance(self, seconds):
        self.time += timedelta(seconds=seconds)

    def spec(self):
        return {
            "game_id": GID,
            "kickoff": KICK.isoformat(),
            "eventID": "synthetic_event",
        }

    def serve(self, events=None, cursor=None):
        def get(url, **kw):
            if url.endswith("/account/usage"):
                return response(usage())
            self.assertGreater(self.api.state["reserved_objects"], 0)
            return response(
                {
                    "data": events if events is not None else [event()],
                    "nextCursor": cursor,
                }
            )

        self.get.side_effect = get

    def test_discovery_shapes_small_payload_without_requiring_player_odds(self):
        self.serve(cursor="opaque+/=")
        got = self.client.discover(
            NOW.isoformat(), (KICK + timedelta(hours=1)).isoformat(), BOOKS
        )
        params = self.get.call_args.kwargs["params"]
        self.assertEqual(params["oddID"], "points-home-game-ml-home")
        self.assertNotIn("oddsAvailable", params)
        self.assertEqual(got["events"][0]["odds"], {})
        self.assertEqual(got["next_cursor"], "opaque+/=")
        self.assertEqual(self.api.state["reserved_objects"], 16)
        self.client.discover(
            NOW.isoformat(), (KICK + timedelta(hours=1)).isoformat(), BOOKS
        )
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.store.cache.cached("not-a-price", NOW), None)

    def test_cursor_passed_unchanged(self):
        self.serve(events=[])
        self.client.discover(
            NOW.isoformat(), KICK.isoformat(), BOOKS, cursor="opaque+/="
        )
        self.assertEqual(self.get.call_args.kwargs["params"]["cursor"], "opaque+/=")

    def test_event_ids_player_shape_reservation_and_local_identity(self):
        self.serve()
        got = self.client.prices([self.spec()], BOOKS, ["SYNTH_PLAYER_1_NFL"])
        self.assertEqual(
            self.get.call_args.kwargs["params"]["eventIDs"], "synthetic_event"
        )
        self.assertEqual(
            self.get.call_args.kwargs["params"]["playerID"], "SYNTH_PLAYER_1_NFL"
        )
        self.assertEqual(self.api.state["reserved_objects"], 1)
        self.assertEqual(len(got["events"]), 1)
        bad = event()
        bad["eventID"] = "wrong"
        self.get.reset_mock()
        self.serve([bad])
        with self.assertRaisesRegex(Unavailable, "Unexpected event ID"):
            self.client.prices([dict(self.spec(), eventID="unexpected")], BOOKS)

    def test_alias_and_local_kickoff_validation(self):
        e = event()
        e["aliases"] = ["old-ID"]
        self.serve([e])
        self.client.prices([dict(self.spec(), eventID="old-ID")], BOOKS)
        self.serve([e])
        with self.assertRaisesRegex(Unavailable, "identity/time"):
            self.client.prices(
                [
                    dict(
                        self.spec(),
                        eventID="old-ID",
                        kickoff=(KICK + timedelta(hours=1)).isoformat(),
                    )
                ],
                BOOKS,
            )

    def test_t60_no_http(self):
        self.time = KICK - timedelta(minutes=60)
        with self.assertRaises(Unavailable):
            self.client.prices([self.spec()], BOOKS)
        self.get.assert_not_called()

    def test_no_result_data_and_nfl_checks_even_if_provider_ignores_filters(self):
        for change in [{"results": {"secret_result": 1}}, {"leagueID": "NBA"}]:
            e = {**event(), **change}
            self.serve([e])
            with self.assertRaises(Unavailable):
                self.client.prices([self.spec()], BOOKS)

    def test_halt_retained_and_no_http_or_reservation(self):
        self.store.halt("unsafe_response")
        before = copy.deepcopy(self.api.state)
        with self.assertRaisesRegex(Unavailable, "halted"):
            self.client.prices([self.spec()], BOOKS)
        self.get.assert_not_called()
        self.assertEqual(self.api.state, before)

    def test_six_call_rate_is_paced_not_bypassed(self):
        for _ in range(6):
            self.store.http_slot(NOW)
        self.serve()
        self.client.prices([self.spec()], BOOKS)
        self.assertGreaterEqual((self.time - NOW).total_seconds(), 60)
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.api.state["reserved_objects"], 1)

    def test_pacing_cannot_send_price_request_after_cutoff(self):
        self.time = KICK - timedelta(minutes=60, seconds=30)
        for _ in range(6):
            self.store.http_slot(self.time)
        self.serve()
        with self.assertRaisesRegex(Unavailable, "T60 window closed during pacing"):
            self.client.prices([self.spec()], BOOKS)
        self.get.assert_not_called()
        self.assertEqual(self.api.state["reserved_objects"], 0)

    def test_size_guard_records_only_size_and_never_parses(self):
        large = Mock(status_code=200, content=b"x" * (8 * 1024 * 1024 + 1))
        self.get.side_effect = [response(usage()), large]
        with self.assertRaises(Unavailable) as caught:
            self.client.prices([self.spec()], BOOKS)
        self.assertEqual(
            explain_error(caught.exception, self.client)[0], "RESPONSE_SIZE_LIMIT"
        )
        self.assertTrue(self.api.state["halt"])
        large.json.assert_not_called()
        self.assertEqual(self.api.state["reserved_objects"], 1)

    def test_echo_guard_separate_no_secret_in_diagnostic(self):
        self.get.side_effect = [response(usage()), response({"data": [], "echo": KEY})]
        with self.assertRaises(Unavailable) as caught:
            self.client.prices([self.spec()], BOOKS)
        diagnostic = explain_error(caught.exception, self.client)
        self.assertEqual(diagnostic[0], "CREDENTIAL_ECHO")
        self.assertNotIn(KEY, str(diagnostic))

    def test_audit_private_restore_and_no_quota_mutation(self):
        self.client.catalog_cached("init")
        before = copy.deepcopy(self.api.state)
        result = {"audit": {GID: {"stage": "not_attempted"}}, "fetches": 0}
        write_audit(self.client, result, REL["release_id"])
        got = private_records(self.store.cache.path, "r8_audit", NOW)
        self.assertEqual(got[0]["audit"], result["audit"])
        self.assertEqual(self.api.state, before)
        self.assertEqual(
            private_records(self.store.cache.path, "r8_audit", NOW + timedelta(days=2)),
            [],
        )


class MultiFixtureTests(unittest.TestCase):
    def setUp(self):
        self.frame, self.rel = fixture_set()
        self.plan = plan8(self.frame, self.rel, NOW, BOOKS)
        self.client = Mock()
        self.client.clock.return_value = NOW
        self.client.transport = {}

    def catalog(self):
        es = []
        for i, gid in enumerate(self.plan["games"]):
            e = event()
            a, h = gid.split("_")[-2:]
            e["eventID"] = gid
            e["status"]["startsAt"] = self.rel["game_kickoffs"][gid]
            e["teams"]["away"]["names"]["short"] = a
            e["teams"]["home"]["names"]["short"] = h
            e["odds"] = {}
            es.append(e)
        return {"events": es, "retrieved_at": NOW.isoformat(), "next_cursor": None}

    def test_all_games_discovered_and_two_event_price_batches(self):
        self.client.discover.return_value = self.catalog()
        self.client.prices.side_effect = lambda *a, **k: {
            "events": [],
            "retrieved_at": NOW.isoformat(),
        }
        result = collect8(self.plan, self.frame, self.rel, self.client)
        self.assertEqual(self.client.discover.call_count, 1)
        self.assertEqual(
            [len(c.args[0]) for c in self.client.prices.call_args_list], [2, 2, 1]
        )
        self.assertEqual(result["reserved_upper_used"], 21)
        self.assertEqual({s["category"] for s in result["audit"].values()}, {"B"})

    def test_short_page_with_cursor_is_followed_opaque(self):
        c = self.catalog()
        self.client.discover.side_effect = [
            dict(c, events=c["events"][:1], next_cursor="opaque+/="),
            dict(c, events=c["events"][1:]),
        ]
        self.client.prices.return_value = {
            "events": [],
            "retrieved_at": NOW.isoformat(),
        }
        collect8(self.plan, self.frame, self.rel, self.client)
        self.assertEqual(self.client.discover.call_args.kwargs["cursor"], "opaque+/=")

    def test_missing_event_after_complete_discovery_not_fake_coverage(self):
        self.client.discover.return_value = dict(self.catalog(), events=[])
        result = collect8(self.plan, self.frame, self.rel, self.client)
        self.client.prices.assert_not_called()
        self.assertEqual(
            {s["stage"] for s in result["audit"].values()}, {"no_event_returned"}
        )

    def test_blocked_batch_stops_later_requests_with_exact_category(self):
        self.client.discover.return_value = self.catalog()
        self.client.prices.side_effect = Unavailable("unsafe response")
        self.client.transport = {"size_exceeded": True, "response_bytes": 9000000}
        result = collect8(self.plan, self.frame, self.rel, self.client)
        self.assertEqual(self.client.prices.call_count, 1)
        self.assertEqual(
            [s["category"] for s in result["audit"].values()].count("A"), 3
        )
        self.assertEqual(result["reserved_upper_used"], 18)

    def test_catalogue_reuse_skips_discovery_and_missing_identity_does_not_filter(self):
        self.client.prices.return_value = {
            "events": [],
            "retrieved_at": NOW.isoformat(),
        }
        collect8(
            self.plan, self.frame, self.rel, self.client, catalogue=[self.catalog()]
        )
        self.client.discover.assert_not_called()
        self.assertTrue(
            all(not c.kwargs["player_ids"] for c in self.client.prices.call_args_list)
        )

    def test_dynamic_states_do_not_infer_provider_absence_and_track_cache_loss(self):
        models = model_candidates(self.frame, self.rel, NOW)
        states = state8([], models, [], {}, self.plan, self.rel, NOW)
        self.assertEqual(sum(s["model_only"] for s in states.values()), 5)
        self.assertEqual(sum(s["bookmaker"] for s in states.values()), 0)
        gid = self.plan["games"][0]
        audit = {gid: {"stage": "fresh_bookmaker", "category": "available"}}
        lost = state8([], models, [], audit, self.plan, self.rel, NOW)
        self.assertEqual(lost[gid]["stage"], "cache_unavailable")
        self.assertEqual(lost[gid]["category"], "F")

    def test_corrupt_or_future_session_cache_is_ignored(self):
        self.assertEqual(
            price_merge(
                [
                    None,
                    {},
                    {"retrieved_at": "invalid"},
                    {"retrieved_at": (NOW + timedelta(seconds=1)).isoformat()},
                ],
                NOW,
            ),
            [],
        )

    def test_local_event_matching_timezones_boundary(self):
        e = self.catalog()["events"][0]
        self.assertEqual(
            match_event(e, self.rel, self.plan["games"]), self.plan["games"][0]
        )
        e["status"]["startsAt"] = (KICK + timedelta(seconds=61)).isoformat()
        self.assertIsNone(match_event(e, self.rel, self.plan["games"]))

    def test_event_scoped_withdrawal_does_not_remove_other_fixture(self):
        old = scoped_snapshot()
        other = copy.deepcopy(old["events"][0])
        other["eventID"] = "other"
        old["events"].append(other)
        new = dict(
            old,
            events=[],
            retrieved_at=(NOW + timedelta(seconds=1)).isoformat(),
            request_scope={
                "eventIDs": "synthetic_event",
                "bookmakerID": "fanduel,draftkings",
            },
        )
        got = price_merge([old, new], NOW + timedelta(seconds=2))
        self.assertTrue(
            any(o["byBookmaker"] for o in got[0]["events"][1]["odds"].values())
        )
        self.assertTrue(
            all(not o["byBookmaker"] for o in got[0]["events"][0]["odds"].values())
        )

    def test_expired_discovery_does_not_restore_quotes(self):
        s = scoped_snapshot()
        self.assertEqual(price_merge([s], NOW + timedelta(minutes=16)), [])
        self.assertEqual(price_merge([dict(s, purpose="catalogue")], NOW), [])

    def test_top_two_model_fallback_every_fixture_distinct_players_no_ev(self):
        models = model_candidates(self.frame, self.rel, NOW)
        result = two8([], models, self.rel)
        self.assertEqual(len(result), 5)
        self.assertTrue(all(len(p) == 1 for p in result.values()))
        self.assertTrue(
            all(p[0]["classification"] == "MODEL ONLY" for p in result.values())
        )
        self.assertTrue(all(p[0].get("ev_pct") is None for p in result.values()))

    def test_missing_markets_are_separate_from_matching_and_absence(self):
        e = redact_events([event()], NOW)[0]
        e["odds"] = {}
        s = {"events": [e], "retrieved_at": NOW.isoformat()}
        self.assertEqual(record_price(s, GID, slate(), REL, NOW)["category"], "C")
        self.assertEqual(
            record_price(dict(s, events=[]), GID, slate(), REL, NOW)["category"], "B"
        )

    def test_identity_filter_requires_complete_unambiguous_observed_mapping(self):
        e = event()
        self.assertEqual(identity_players(e, slate(), GID), ["SYNTH_PLAYER_1_NFL"])
        e["players"]["duplicate"] = e["players"]["SYNTH_PLAYER_1_NFL"]
        self.assertEqual(identity_players(e, slate(), GID), [])


class R8JourneyTests(unittest.TestCase):
    def test_cached_landing_cards_first_and_all_workspaces_no_network(self):
        import os
        from unittest.mock import patch

        from streamlit.testing.v1 import AppTest

        from research_platform.slate import cached_snapshots
        from sgo_research.store import Store
        from tests.test_r7_research import two_player_fixture

        snap, _frame = two_player_fixture()
        snap["events"][0]["aliases"] = ["older-event-id"]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cache.sqlite"
            Store(path, persistent=False).save_cache("test", snap, NOW)
            restored = cached_snapshots(NOW, path)
            self.assertEqual(restored[0]["events"][0]["aliases"], ["older-event-id"])
            with (
                patch.dict(
                    os.environ,
                    {
                        "SGO_RESEARCH_STORE": str(path),
                        "SPORTSGAMEODDS_API_KEY": "synthetic_never_sent",
                    },
                ),
                patch("research_platform.r8.datetime") as clock,
                patch("requests.get") as get,
                patch("requests.request") as request,
            ):
                clock.now.return_value = NOW
                app = AppTest.from_string(
                    "from tests.test_r7_research import two_player_fixture\nfrom tests.test_sgo_research import REL\nfrom research_platform.r8 import render\ns,f=two_player_fixture()\nrender(f,REL)"
                ).run(timeout=30)
                self.assertFalse(app.exception, app.exception)
                cards = [
                    i
                    for i, e in app.main.children.items()
                    if e.type == "markdown" and '<article class="desk-card' in e.value
                ]
                panels = [
                    i
                    for i, e in app.main.children.items()
                    if e.type == "expander" and "Collect missing slate" in e.label
                ]
                self.assertLess(cards[0], panels[0])
                self.assertFalse(
                    next(
                        e for e in app.expander if "Collect missing slate" in e.label
                    ).proto.expanded
                )
                self.assertTrue(any("WATCH" in e.value for e in app.markdown))
                for section in ["Top 2 by Game", "Parlay Research", "Top Picks"]:
                    app.selectbox[0].select(section).run(timeout=30)
                    self.assertFalse(app.exception, app.exception)
                get.assert_not_called()
                request.assert_not_called()

    def test_one_click_invokes_new_bounded_collector_persists_audit_and_rerenders(self):
        from unittest.mock import patch

        from streamlit.testing.v1 import AppTest

        fake = Mock()
        fake.clock.return_value = NOW
        result = {
            "snapshots": [],
            "catalogue": [],
            "audit": {
                GID: {
                    "stage": "no_event_returned",
                    "category": "B",
                    "detail": "Synthetic accepted empty discovery",
                }
            },
            "fetches": 1,
            "reserved_upper_used": 16,
        }
        with (
            patch("research_platform.r8.datetime") as clock,
            patch("research_platform.r8.cached_snapshots", return_value=[]),
            patch("research_platform.r8.private_records", return_value=[]),
            patch("research_platform.r8.research_key", return_value=KEY),
            patch("research_platform.r8.quota_store"),
            patch("research_platform.r8.EventClient", return_value=fake),
            patch("research_platform.r8.collect8", return_value=result) as collect,
            patch("research_platform.r8.write_audit") as write,
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            clock.now.return_value = NOW
            app = AppTest.from_string(
                "from tests.test_sgo_research import slate,REL\nfrom research_platform.r8 import render\nrender(slate(),REL)"
            ).run(timeout=30)
            next(b for b in app.button if "Discover & collect" in b.label).click().run(
                timeout=30
            )
            self.assertFalse(app.exception, app.exception)
            collect.assert_called_once()
            write.assert_called_once()
            self.assertEqual(collect.call_args.args[0]["max_reserved_objects"], 33)
            self.assertTrue(
                any("No provider event returned" in e.value for e in app.markdown)
            )
            get.assert_not_called()
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
