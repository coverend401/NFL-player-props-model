"""Free bounded capture, ranking, cache privacy and parlay integrity regressions."""

import copy
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from research_platform.engine import evaluate
from research_platform.slate import (
    cached_snapshots,
    collection_plan,
    coverage,
    execute_plan,
    model_candidates,
    parlay_research,
    scope_for,
    top_two,
    unique_watch,
)
from sgo_research.contracts import Unavailable
from sgo_research.store import Store
from tests.test_market_benchmarks import source
from tests.test_sgo_research import KICK, NOW, REL, slate


def fixture_set(n=5):
    pairs = [("PIT", "CIN"), ("NE", "DET"), ("SF", "LA"), ("BUF", "MIA"), ("GB", "CHI")]
    rows = []
    kickoffs = {}
    for i, (away, home) in enumerate(pairs[:n]):
        gid = f"2027_01_{away}_{home}"
        kickoffs[gid] = (KICK + timedelta(hours=i)).isoformat()
        frame = slate().assign(
            game_id=gid, team=home, player_id=f"synthetic_{i}", player=f"Synthetic {i}"
        )
        rows.append(frame)
    return pd.concat(rows, ignore_index=True), {**REL, "game_kickoffs": kickoffs}


def scoped_snapshot(scope=None):
    s = source()
    s["request_scope"] = scope or scope_for(KICK.isoformat(), ["fanduel", "draftkings"])
    return s


class R7CollectionTests(unittest.TestCase):
    def test_plan_hard_bound_and_cutoff(self):
        f, r = fixture_set()
        p = collection_plan(f, r, NOW)
        self.assertEqual(p["max_reserved_objects"], 48)
        self.assertEqual(p["max_provider_http_calls"], 6)
        later = collection_plan(f, r, KICK - timedelta(minutes=59))
        self.assertIn("2027_01_PIT_CIN", later["excluded"])
        f.loc[f.game_id.eq("2027_01_NE_DET"), "projection_status"] = "scenario_only"
        self.assertIn("2027_01_NE_DET", collection_plan(f, r, NOW)["excluded"])

    def test_three_attempt_limit_partial_not_full(self):
        f, r = fixture_set()
        p = collection_plan(f, r, NOW)
        client = Mock()
        client.clock.return_value = NOW
        client.fetch.return_value = scoped_snapshot()
        result = execute_plan(p, client, NOW)
        self.assertEqual(client.fetch.call_count, 3)
        self.assertEqual(result["max_objects_exposed"], 48)
        self.assertEqual(
            sum(
                s["status"] == "not_requested_bounded_partial"
                for s in result["statuses"]
            ),
            2,
        )

    def test_cache_reuse_does_not_call_provider_or_refresh_timestamp(self):
        f, r = fixture_set(1)
        p = collection_plan(f, r, NOW, ["fanduel", "draftkings"])
        snap = scoped_snapshot(p["windows"][0]["scope"])
        client = Mock()
        client.clock.return_value = NOW
        result = execute_plan(p, client, NOW, [snap])
        client.fetch.assert_not_called()
        self.assertEqual(result["snapshots"][0]["retrieved_at"], NOW.isoformat())
        self.assertEqual(result["max_objects_exposed"], 0)

    def test_expiring_cache_cannot_exceed_declared_bound(self):
        f, r = fixture_set()
        p = collection_plan(f, r, NOW)
        client = Mock()
        client.clock.return_value = NOW + timedelta(minutes=11)
        client.fetch.return_value = scoped_snapshot()
        stale = [scoped_snapshot(w["scope"]) for w in p["windows"]]
        result = execute_plan(p, client, NOW, stale)
        self.assertLessEqual(result["max_objects_exposed"], p["max_reserved_objects"])
        self.assertEqual(client.fetch.call_count, 3)

    def test_failure_stops_new_requests_and_keeps_success(self):
        f, r = fixture_set()
        p = collection_plan(f, r, NOW)
        client = Mock()
        client.clock.return_value = NOW
        client.fetch.side_effect = [
            scoped_snapshot(),
            Unavailable("Conservative six-request/minute limit reached"),
        ]
        result = execute_plan(p, client, NOW)
        self.assertEqual(len(result["snapshots"]), 1)
        self.assertEqual(client.fetch.call_count, 2)
        self.assertEqual(result["statuses"][1]["code"], "RATE")

    def test_cutoff_crossed_during_batch_is_skipped(self):
        f, r = fixture_set(1)
        p = collection_plan(f, r, NOW)
        client = Mock()
        client.clock.return_value = KICK - timedelta(minutes=59)
        result = execute_plan(p, client, NOW)
        client.fetch.assert_not_called()
        self.assertEqual(result["statuses"][0]["status"], "cutoff_closed")

    def test_offline_cache_private_ttl_and_no_counter_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.sqlite"
            store = Store(path, persistent=False)
            snapshot = scoped_snapshot()
            store.save_cache("synthetic", snapshot, NOW)
            with store.connection() as c:
                c.execute("INSERT INTO controls VALUES ('sentinel','unchanged')")
            with patch("requests.get") as get, patch("requests.request") as req:
                loaded = cached_snapshots(NOW, path)
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0]["retrieved_at"], NOW.isoformat())
                self.assertEqual(
                    cached_snapshots(NOW + timedelta(minutes=11), path), []
                )
                get.assert_not_called()
                req.assert_not_called()
            with store.connection() as c:
                self.assertEqual(
                    c.execute("SELECT value FROM controls").fetchone()[0], "unchanged"
                )
            os.chmod(path, 0o644)
            self.assertEqual(cached_snapshots(NOW, path), [])

    def test_missing_fixture_is_reported_not_assumed_covered(self):
        f, r = fixture_set(2)
        p = collection_plan(f, r, NOW)
        report = coverage([], r, p, [scoped_snapshot()])
        self.assertEqual(report["priced"], 0)
        self.assertEqual(len(report["missing"]), 2)
        self.assertIn("Event returned", report["missing"]["2027_01_PIT_CIN"])


class R7RankingTests(unittest.TestCase):
    def test_model_candidates_no_invented_price_and_no_expired_scenario(self):
        f = slate()
        m = model_candidates(f, REL, NOW)
        self.assertTrue(m)
        self.assertTrue(
            all(
                r["ev_pct"] is None
                and r["model_probability"] is None
                and r["decimal_odds"] is None
                and r["side"] is None
                for r in m
            )
        )
        self.assertEqual(model_candidates(f, REL, KICK), [])
        self.assertEqual(
            model_candidates(f.assign(projection_status="scenario_only"), REL, NOW), []
        )

    def test_top_two_never_fills_one_watch_with_unpriced_model(self):
        rows, _ = evaluate([source()], slate(), REL, NOW)
        picks = top_two(rows, model_candidates(slate(), REL, NOW), REL)
        self.assertEqual(
            len(picks[next(iter(REL["game_kickoffs"]))]), 1
        )  # one player; no forced second
        self.assertEqual(
            top_two(
                [r for r in rows if r["classification"] == "PASS"],
                model_candidates(slate(), REL, NOW),
                REL,
            )[next(iter(REL["game_kickoffs"]))],
            [],
        )

    def test_watch_ranking_and_book_deduplication(self):
        rows, _ = evaluate([source()], slate(), REL, NOW)
        ranked = unique_watch(rows)
        self.assertEqual(
            [r["ev_pct"] for r in ranked],
            sorted([r["ev_pct"] for r in ranked], reverse=True),
        )
        self.assertEqual(
            len({(r["player_id"], r["market"], r["side"]) for r in ranked}), len(ranked)
        )

    def test_parlay_product_is_never_offered_odds_probability_or_ev(self):
        rows, _ = evaluate([source()], slate(), REL, NOW)
        legs = unique_watch(rows)[:2]
        other = copy.deepcopy(legs[1])
        other["game_id"] = "2027_01_NE_DET"
        other["player_id"] = "other"
        result = parlay_research([legs[0], other], NOW)
        self.assertAlmostEqual(
            result["leg_price_product"], legs[0]["decimal_odds"] * other["decimal_odds"]
        )
        self.assertIsNone(result["quoted_combined_odds"])
        self.assertIsNone(result["joint_probability"])
        self.assertIsNone(result["ev"])
        self.assertIsNone(parlay_research(legs, NOW)["leg_price_product"])
        same = parlay_research(legs, NOW, allow_same_game=True)
        self.assertTrue(any("Same-game" in w for w in same["warnings"]))
        self.assertTrue(any("same-player" in w for w in same["warnings"]))
        self.assertIsNone(
            parlay_research([legs[0], other], NOW + timedelta(minutes=16))[
                "leg_price_product"
            ]
        )
        self.assertIsNone(
            parlay_research([legs[0], legs[0]], NOW, True)["leg_price_product"]
        )


class R7JourneyTests(unittest.TestCase):
    def test_cached_landing_order_collapsed_controls_and_new_workspaces(self):
        from streamlit.testing.v1 import AppTest

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.sqlite"
            store = Store(path, persistent=False)
            store.save_cache("synthetic", scoped_snapshot(), NOW)
            with (
                patch.dict(
                    os.environ,
                    {
                        "SGO_RESEARCH_STORE": str(path),
                        "SPORTSGAMEODDS_API_KEY": "synthetic_key_never_sent",
                    },
                ),
                patch("research_platform.r7.datetime") as clock,
                patch("sgo_research.market_ui.datetime") as old_clock,
                patch("requests.get") as get,
                patch("requests.request") as request,
            ):
                clock.now.return_value = NOW
                old_clock.now.return_value = NOW
                app = AppTest.from_string(
                    "from tests.test_sgo_research import slate, REL\nfrom research_platform.r7 import render\nrender(slate(), REL)"
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
                    if e.type == "expander"
                    and e.label == "Refresh prices — slate-wide collection"
                ]
                self.assertTrue(cards)
                self.assertTrue(panels)
                self.assertLess(cards[0], panels[0])
                panel = next(
                    e
                    for e in app.expander
                    if e.label == "Refresh prices — slate-wide collection"
                )
                self.assertFalse(panel.proto.expanded)
                self.assertTrue(
                    any(
                        "WATCH" in e.value and "Synthetic Player" in e.value
                        for e in app.markdown
                    )
                )
                for section in ["Top 2 by Game", "Parlay Research", "Top Picks"]:
                    app.selectbox[0].select(section).run(timeout=30)
                    self.assertFalse(app.exception, app.exception)
                get.assert_not_called()
                request.assert_not_called()

    def test_empty_landing_immediately_has_model_only_cards(self):
        from streamlit.testing.v1 import AppTest

        with (
            patch("research_platform.r7.cached_snapshots", return_value=[]),
            patch("research_platform.r7.datetime") as clock,
            patch("sgo_research.market_ui.research_key", return_value=None),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            clock.now.return_value = NOW
            app = AppTest.from_string(
                "from tests.test_sgo_research import slate, REL\nfrom research_platform.r7 import render\nrender(slate(), REL)"
            ).run(timeout=30)
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any(
                    "MODEL ONLY" in e.value and "<article" in e.value
                    for e in app.markdown
                )
            )
            get.assert_not_called()
            request.assert_not_called()

    def test_one_bulk_click_uses_bounded_executor_and_rerenders(self):
        from streamlit.testing.v1 import AppTest

        with (
            patch("research_platform.r7.cached_snapshots", return_value=[]),
            patch("research_platform.r7.datetime") as clock,
            patch("sgo_research.market_ui.datetime") as old_clock,
            patch(
                "research_platform.r7.research_key",
                return_value="synthetic_key_never_sent",
            ),
            patch(
                "sgo_research.market_ui.research_key",
                return_value="synthetic_key_never_sent",
            ),
            patch(
                "research_platform.r7.execute_plan",
                return_value={
                    "snapshots": [],
                    "statuses": [],
                    "max_objects_exposed": 0,
                },
            ) as execute,
            patch("requests.request") as request,
            patch("requests.get") as get,
        ):
            clock.now.return_value = NOW
            old_clock.now.return_value = NOW
            app = AppTest.from_string(
                "from tests.test_sgo_research import slate, REL\nfrom research_platform.r7 import render\nrender(slate(), REL)"
            ).run(timeout=30)
            next(
                b
                for b in app.button
                if b.label == "Collect eligible slate — bounded free requests"
            ).click().run(timeout=30)
            self.assertFalse(app.exception, app.exception)
            execute.assert_called_once()
            self.assertEqual(execute.call_args.args[0]["max_reserved_objects"], 16)
            request.assert_not_called()
            get.assert_not_called()


def two_player_fixture():
    s = scoped_snapshot(
        scope_for(KICK.isoformat(), ["fanduel", "draftkings", "betmgm"])
    )
    event = s["events"][0]
    pid = "SYNTH_PLAYER_2_NFL"
    event["players"][pid] = {"name": "Second Synthetic Player", "teamID": "CIN_NFL"}
    for key, odd in list(event["odds"].items()):
        if odd["statID"] not in ["receiving_yards", "receiving_receptions"]:
            continue
        new = copy.deepcopy(odd)
        new["statEntityID"] = pid
        event["odds"][key.replace("SYNTH_PLAYER_1_NFL", pid)] = new
    extra = slate()
    extra = extra[extra.market.isin(["Receiving Yards", "Receptions"])].assign(
        player_id="synthetic_second", player="Second Synthetic Player"
    )
    return s, pd.concat([slate(), extra], ignore_index=True)


class R7ActualQuotaAdapterTests(unittest.TestCase):
    def test_batch_adapter_reserves_atomic_private_quota_before_events(self):
        from research_platform.slate import LazyCollector
        from sgo_research.github_quota import GitHubQuotaStore
        from tests.test_sgo_private_quota import API
        from tests.test_sgo_research import KEY, response, usage

        with tempfile.TemporaryDirectory() as directory:
            store = GitHubQuotaStore(
                "example/private-quota", Path(directory) / "cache.sqlite", api=API()
            )

            def reply(url, **kwargs):
                if url.endswith("/account/usage"):
                    return response(usage())
                state, _ = store._read()
                self.assertEqual(state["reserved_objects"], 16)
                return response({"data": [scoped_snapshot()["events"][0]]})

            with (
                patch("sgo_research.config.quota_store", return_value=store),
                patch("requests.get", side_effect=reply) as get,
            ):
                collector = LazyCollector(KEY, lambda: NOW, terms_ack=True)
                plan = collection_plan(slate(), REL, NOW)
                result = execute_plan(plan, collector, NOW)
                self.assertEqual(result["new_attempts"], 1)
                self.assertEqual(get.call_count, 2)
                self.assertEqual(len(result["snapshots"]), 1)
                self.assertEqual(store._read()[0]["reserved_objects"], 16)

    def test_top_two_has_two_distinct_players_when_evidence_exists(self):
        s, f = two_player_fixture()
        rows, _ = evaluate([s], f, REL, NOW)
        picks = top_two(rows, model_candidates(f, REL, NOW), REL)[
            next(iter(REL["game_kickoffs"]))
        ]
        self.assertEqual(len(picks), 2)
        self.assertEqual(len({p["player_id"] for p in picks}), 2)


class R7BoundFailureTests(unittest.TestCase):
    def test_modified_attempt_limit_cannot_exceed_displayed_bound(self):
        f, r = fixture_set()
        p = collection_plan(f, r, NOW)
        p["max_new_windows"] = 99
        client = Mock()
        with self.assertRaises(Unavailable):
            execute_plan(p, client, NOW)
        client.fetch.assert_not_called()

    def test_cache_write_failure_stops_without_refund_or_retry(self):
        import sqlite3

        f, r = fixture_set()
        p = collection_plan(f, r, NOW)
        client = Mock()
        client.clock.return_value = NOW
        client.fetch.side_effect = sqlite3.OperationalError(
            "synthetic private path not exposed"
        )
        result = execute_plan(p, client, NOW)
        self.assertEqual(client.fetch.call_count, 1)
        self.assertEqual(result["statuses"][0]["code"], "CACHE_STORAGE")
        self.assertNotIn("synthetic private path", result["statuses"][0]["message"])
