"""Synthetic future quotes only: no provider coverage or betting performance claims."""

import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import requests
from scipy.stats import norm

from sgo_research.analysis import comparisons, normalise, paper_decision
from sgo_research.client import Client, redact_events
from sgo_research.contracts import (
    STAT_MARKETS,
    Unavailable,
    account_limits,
    odds_formats,
)
from sgo_research.store import Store

NOW = datetime(2027, 8, 1, 12, tzinfo=UTC)  # synthetic; no real results
KEY = "synthetic_not_a_real_api_key"
KICK = NOW + timedelta(hours=4)
RID = "synthetic_release"
GID = "2027_01_PIT_CIN"


def usage(used=0):
    return {
        "data": {
            "tier": "Amateur",
            "isActive": True,
            "rateLimits": {
                "per-month": {
                    "maxEntitiesPerInterval": 2500,
                    "currentIntervalEntities": used,
                    "maxRequestsPerInterval": "unlimited",
                    "currentIntervalRequests": 0,
                    "currentIntervalEndTime": (NOW + timedelta(days=25)).isoformat(),
                },
                "per-minute": {
                    "maxRequestsPerInterval": 10,
                    "currentIntervalRequests": 0,
                },
            },
        }
    }


def event():
    odds = {}
    for stat in STAT_MARKETS:
        for side in ["over", "under"]:
            oid = f"{stat}-SYNTH_PLAYER_1_NFL-game-ou-{side}"
            odds[oid] = {
                "statID": stat,
                "statEntityID": "SYNTH_PLAYER_1_NFL",
                "periodID": "game",
                "betTypeID": "ou",
                "sideID": side,
                "bookOdds": "-999",
                "bookOverUnder": "999.5",
                "byBookmaker": {
                    "williamhill": {
                        "odds": "-110",
                        "overUnder": "20.5",
                        "available": True,
                        "isMainLine": True,
                        "lastUpdatedAt": NOW.isoformat(),
                    }
                },
            }
    return {
        "eventID": "synthetic_event",
        "leagueID": "NFL",
        "players": {
            "SYNTH_PLAYER_1_NFL": {"name": "Synthetic Player", "teamID": "CIN_NFL"}
        },
        "status": {
            "started": False,
            "ended": False,
            "live": False,
            "startsAt": KICK.isoformat(),
        },
        "teams": {
            "home": {"teamID": "CIN_NFL", "names": {"short": "CIN"}, "score": 999},
            "away": {"teamID": "PIT_NFL", "names": {"short": "PIT"}},
        },
        "odds": odds,
    }


def snapshot():
    return {
        "events": [event()],
        "retrieved_at": NOW.isoformat(),
        "raw_sha256": "synthetic",
        "authenticated_response": True,
        "account_tier": "Amateur",
    }


def slate():
    return pd.DataFrame(
        [
            {
                "game_id": GID,
                "team": "CIN",
                "player": "Synthetic Player",
                "player_id": "synthetic_gsis",
                "position": "RB",
                "market": m,
                "projection": 22.0,
                "resid_std": 5.0,
                "prediction_at": (NOW - timedelta(hours=1)).isoformat(),
                "projection_status": "complete",
                "release_id": RID,
                "week": 1,
            }
            for m in STAT_MARKETS.values()
        ]
    )


REL = {"release_id": RID, "game_kickoffs": {GID: KICK.isoformat()}}
EVIDENCE = {
    "williamhill": {
        "jurisdiction": "UK",
        "evidence_ref": "synthetic-reviewed-reference",
        "rules_ref": "synthetic-rules",
    }
}


def response(body, status=200):
    return Mock(status_code=status, content=json.dumps(body).encode())


class PricingTests(unittest.TestCase):
    def compare(self, s=None, f=None, now=NOW, **kwargs):
        return comparisons(
            s or snapshot(),
            f if f is not None else slate(),
            REL,
            now,
            book_evidence=kwargs.pop("book_evidence", EVIDENCE),
            **kwargs,
        )[0]

    def test_all_seven_markets_actual_line_not_consensus(self):
        rows = self.compare()
        self.assertEqual(len(rows), 14)
        for r in rows:
            self.assertTrue(r["eligible"], r["comparison_status"])
            self.assertEqual(r["line"], 20.5)
            p = (
                1 - norm.cdf(20.5, 22, 5)
                if r["side"] == "Over"
                else norm.cdf(20.5, 22, 5)
            )
            self.assertAlmostEqual(r["model_probability"], p)
            self.assertAlmostEqual(r["ev_pct"], 100 * (p * (1 + 100 / 110) - 1))
            self.assertAlmostEqual(r["implied_probability"], 1 / (1 + 100 / 110))

    def test_price_formats(self):
        self.assertEqual(odds_formats("-110"), (1 + 100 / 110, "10/11"))
        self.assertEqual(odds_formats("+150"), (2.5, "3/2"))
        for raw in ["1.9", "10/11", 0, "nan", "inf", None]:
            with self.assertRaises(Unavailable):
                odds_formats(raw)

    def test_push_and_quarter_lines_excluded(self):
        for line in [20, 20.25]:
            s = snapshot()
            for o in s["events"][0]["odds"].values():
                o["byBookmaker"]["williamhill"]["overUnder"] = line
            for r in self.compare(s):
                self.assertFalse(r["eligible"])
                self.assertIsNone(r["ev_pct"])

    def test_no_uk_inference_from_brand(self):
        for r in self.compare(book_evidence={}):
            self.assertFalse(r["eligible"])
            self.assertIn("UK_bookmaker_variant_unverified", r["comparison_status"])

    def test_missing_opposite_side(self):
        s = snapshot()
        s["events"][0]["odds"] = {
            k: v for k, v in s["events"][0]["odds"].items() if v["sideID"] == "over"
        }
        self.assertTrue(
            all(
                not r["eligible"] and "opposite_side" in r["comparison_status"]
                for r in self.compare(s)
            )
        )

    def test_stale_and_missing_timestamp(self):
        for stamp in [
            None,
            (NOW - timedelta(minutes=16)).isoformat(),
            (NOW + timedelta(seconds=1)).isoformat(),
        ]:
            s = snapshot()
            for o in s["events"][0]["odds"].values():
                o["byBookmaker"]["williamhill"]["lastUpdatedAt"] = stamp
            self.assertTrue(all(not r["eligible"] for r in self.compare(s)))

    def test_unmatched_fixture_player_and_team(self):
        for field, value in [("name", "Different Person"), ("teamID", "WRONG")]:
            s = snapshot()
            s["events"][0]["players"]["SYNTH_PLAYER_1_NFL"][field] = value
            self.assertTrue(all(not r["eligible"] for r in self.compare(s)))
        f = slate()
        f["game_id"] = "other"
        self.assertTrue(all(not r["eligible"] for r in self.compare(f=f)))

    def test_homonyms_ambiguous(self):
        f = pd.concat([slate(), slate().assign(player_id="another")])
        self.assertTrue(all(not r["eligible"] for r in self.compare(f=f)))

        # Distinct people sharing a name must not be resolved by which market
        # each happens to have in the forecast slate.
        split = slate()
        split.loc[split.market.eq("Receptions"), "player_id"] = (
            "different_person_same_name"
        )
        self.assertTrue(all(not r["eligible"] for r in self.compare(f=split)))

    def test_explicit_id_map_still_requires_team(self):
        s = snapshot()
        s["events"][0]["players"]["SYNTH_PLAYER_1_NFL"]["name"] = "Different Name"
        self.assertTrue(
            all(
                r["eligible"]
                for r in self.compare(
                    s, player_map={"SYNTH_PLAYER_1_NFL": "synthetic_gsis"}
                )
            )
        )

    def test_qb_rushing_model_selected(self):
        f = slate()
        f["position"] = "QB"
        f["market"] = f.market.replace(
            {
                "Rushing Yards": "QB Rushing Yards",
                "Rushing Attempts": "QB Rushing Attempts",
            }
        )
        rows = self.compare(f=f)
        self.assertTrue(all(r["eligible"] for r in rows))
        self.assertEqual(sum(r["model_market"].startswith("QB ") for r in rows), 4)

    def test_future_forecast_and_wrong_release_rejected(self):
        for field, value in [
            ("prediction_at", (NOW + timedelta(seconds=1)).isoformat()),
            ("release_id", "wrong"),
            ("projection_status", "scenario"),
            ("resid_std", 0),
        ]:
            f = slate()
            f[field] = value
            self.assertTrue(all(not r["eligible"] for r in self.compare(f=f)))

    def test_t60_and_missing_auth(self):
        self.assertTrue(
            all(
                not r["eligible"]
                for r in self.compare(now=KICK - timedelta(minutes=59))
            )
        )
        s = snapshot()
        s["authenticated_response"] = False
        self.assertTrue(all(not r["eligible"] for r in self.compare(s)))

    def test_paper_freeze_deterministic_no_settlement(self):
        r = self.compare()[0]
        a = paper_decision(r, NOW)
        self.assertEqual(a, paper_decision(r, NOW))
        self.assertEqual(a["real_stake"], 0)
        self.assertFalse(a["settlement_authorised"])
        with self.assertRaises(Unavailable):
            paper_decision(r, KICK)
        with self.assertRaises(Unavailable):
            paper_decision(r, NOW + timedelta(minutes=16))

    def test_duplicate_not_best_price(self):
        s = snapshot()
        o = next(iter(s["events"][0]["odds"].values()))
        s["events"][0]["odds"]["duplicate"] = copy.deepcopy(o)
        quotes, issues = normalise(s)
        self.assertEqual(len(quotes), 13)
        self.assertTrue(issues)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "private.db", persistent=True)
        self.get = Mock(side_effect=[response(usage()), response({"data": [event()]})])
        self.client = Client(
            KEY, self.store, terms_ack=True, get=self.get, clock=lambda: NOW
        )

    def fetch(self, **kwargs):
        return self.client.fetch(
            (NOW + timedelta(hours=1)).isoformat(),
            (NOW + timedelta(hours=6)).isoformat(),
            **kwargs,
        )

    def test_authenticated_cache_and_redaction(self):
        s = self.fetch()
        self.assertTrue(s["authenticated_response"])
        self.assertFalse(s["live_uk_coverage_verified"])
        self.assertNotIn("score", str(s))
        self.assertNotIn("bookOdds", str(s))
        self.assertTrue(self.fetch()["cache_hit"])
        self.assertEqual(self.get.call_count, 2)
        for call in self.get.call_args_list:
            self.assertEqual(call.kwargs["headers"]["x-api-key"], KEY)
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertNotIn(KEY, call.args[0])
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)

    def test_missing_key_no_http(self):
        self.client.key = None
        with self.assertRaises(Unavailable):
            self.fetch()
        self.get.assert_not_called()

    def test_configurable_cap_cannot_exceed_free_ceiling(self):
        with self.assertRaises(Unavailable):
            Client(KEY, self.store, object_cap=2501)
        self.client.object_cap = 10
        with self.assertRaises(Unavailable):
            self.fetch()
        self.assertEqual(self.get.call_count, 1)  # usage only; no events

    def test_missing_terms_no_http(self):
        self.client.terms_ack = False
        with self.assertRaises(Unavailable):
            self.fetch()
        self.get.assert_not_called()

    def test_ephemeral_store_no_http(self):
        self.store.persistent = False
        with self.assertRaises(Unavailable):
            self.fetch()
        self.get.assert_not_called()

    def test_paid_tier_never_fetches_events(self):
        u = usage()
        u["data"]["tier"] = "Pro"
        self.get.side_effect = [response(u)]
        with self.assertRaises(Unavailable):
            self.fetch()
        self.assertEqual(self.get.call_count, 1)

    def test_reset_timestamp_mandatory(self):
        u = usage()
        del u["data"]["rateLimits"]["per-month"]["currentIntervalEndTime"]
        self.get.side_effect = [response(u)]
        with self.assertRaises(Unavailable):
            self.fetch()
        self.assertEqual(self.get.call_count, 1)

    def test_error_reserved_not_refunded(self):
        self.get.side_effect = [response(usage()), response({}, 500)]
        with self.assertRaises(Unavailable):
            self.fetch()
        with self.store.connection() as c:
            self.assertEqual(
                c.execute("SELECT SUM(objects) FROM reservations").fetchone()[0], 16
            )

    def test_429_halts_across_restart(self):
        self.get.side_effect = [response({}, 429)]
        with self.assertRaises(Unavailable):
            self.fetch()
        again = Store(self.store.path, persistent=True)
        with self.assertRaises(Unavailable):
            again.http_slot(NOW + timedelta(minutes=2))

    def test_network_exception_sanitised(self):
        self.get.side_effect = requests.RequestException(KEY)
        with self.assertRaises(Unavailable) as error:
            self.fetch()
        self.assertNotIn(KEY, str(error.exception))
        self.assertEqual(self.get.call_count, 1)

    def test_credential_echo_rejected(self):
        self.get.side_effect = [response({"echo": KEY})]
        with self.assertRaises(Unavailable):
            self.fetch()

    def test_provider_overlimit_rejected(self):
        self.get.side_effect = [response(usage()), response({"data": [event()] * 17})]
        with self.assertRaises(Unavailable):
            self.fetch()
        self.assertIsNone(self.store.cached("anything", NOW))

    def test_no_past_or_large_window(self):
        with self.assertRaises(Unavailable):
            self.client.fetch((NOW - timedelta(days=1)).isoformat(), KICK.isoformat())
        with self.assertRaises(Unavailable):
            self.client.fetch(KICK.isoformat(), (KICK + timedelta(days=9)).isoformat())
        with self.assertRaises(Unavailable):
            self.fetch(books=["paidbook"])
        self.get.assert_not_called()

    def test_no_started_cancelled_or_results(self):
        for field in ["started", "ended", "live", "cancelled"]:
            e = event()
            e["status"][field] = True
            with self.assertRaises(Unavailable):
                redact_events([e], NOW)
        e = event()
        e["results"] = {"do_not_inspect": True}
        with self.assertRaises(Unavailable):
            redact_events([e], NOW)

    def test_quota_restart_and_headroom(self):
        limits = account_limits(usage(1980))
        self.store.reserve(limits, 16, NOW)
        with self.assertRaises(Unavailable):
            Store(self.store.path, persistent=True).reserve(limits, 16, NOW)

    def test_rate_no_automatic_retry(self):
        for _ in range(6):
            self.store.http_slot(NOW)
        with self.assertRaises(Unavailable):
            self.store.http_slot(NOW)

    def test_concurrent_reservations_atomic(self):
        from concurrent.futures import ThreadPoolExecutor

        limits = account_limits(usage(1980))

        def attempt(_):
            try:
                Store(self.store.path, persistent=True).reserve(limits, 16, NOW)
                return True
            except Unavailable:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_expired_cache_not_reused_and_pruned(self):
        self.store.save_cache("key", {"no": "real quotes"}, NOW)
        self.assertIsNone(self.store.cached("key", NOW + timedelta(minutes=10)))
        self.assertIsNone(self.store.cached("key", NOW + timedelta(days=2)))
        with self.store.connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM cache").fetchone()[0], 0)

    def test_finite_limit_without_usage_rejected(self):
        limits = account_limits(usage())
        limits["per-hour"].update(max_entities=100, used_entities=None)
        with self.assertRaises(Unavailable):
            self.store.reserve(limits, 16, NOW)
        limits = account_limits(usage())
        limits["per-month"].update(max_requests=0, used_requests=0)
        with self.assertRaises(Unavailable):
            self.store.reserve(limits, 16, NOW)

    def test_no_early_month_reset(self):
        limits = account_limits(usage())
        self.store.reserve(limits, 16, NOW)
        limits["per-month"]["end"] = (NOW + timedelta(days=26)).isoformat()
        with self.assertRaises(Unavailable):
            self.store.reserve(limits, 16, NOW)

    def test_paper_persistence_and_settlement_locked(self):
        with self.assertRaises(Unavailable):
            self.store.freeze_paper({})
        with self.assertRaises(Unavailable):
            self.store.settle()

    def test_current_account_probe_schema(self):
        from scripts.probe_sgo_free_account import account_only

        report = account_only(KEY, get=lambda *args, **kwargs: response(usage()))
        self.assertEqual(report["rate_limits"]["per-month"]["max-entities"], 2500)
        self.assertFalse(report["gate_passed"])

    def test_malformed_provider_structures_fail_closed(self):
        for bad in [None, [], {"leagueID": "NFL", "status": None}]:
            with self.assertRaises(Unavailable):
                redact_events([bad], NOW)
        u = usage()
        u["data"]["rateLimits"] = []
        with self.assertRaises(Unavailable):
            account_limits(u)

    def test_repo_store_prohibited(self):
        with self.assertRaises(Unavailable):
            Store(Path(__file__).resolve().parents[1] / "forbidden.db")


class PreviewTests(unittest.TestCase):
    def test_synthetic_cards_and_filters_without_http(self):
        from streamlit.testing.v1 import AppTest

        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(
                os.environ,
                {
                    "SPORTSGAMEODDS_API_KEY": KEY,
                    "SGO_RESEARCH_STORE": str(Path(temp) / "cards.db"),
                    "SGO_PERSISTENT_VOLUME_APPROVED": "1",
                    "SGO_PRIVATE_CACHE_TERMS_ACK": "1",
                },
            ),
            patch("requests.get") as get,
            patch("sgo_research.ui.datetime") as clock,
        ):
            clock.now.return_value = NOW
            app = AppTest.from_string(
                "from tests.test_sgo_research import snapshot,slate,REL\nimport streamlit as st\nfrom sgo_research.ui import render\nst.session_state['sgo_snapshot']=snapshot()\nrender(slate(),REL)"
            ).run()
            self.assertFalse(app.exception, app.exception)
            self.assertGreaterEqual(len(app.markdown), 14)
            self.assertTrue(
                any("UK_bookmaker_variant_unverified" in c.value for c in app.caption)
            )
            self.assertNotIn(KEY, str(app.markdown))
            app.text_input(key="sgo_player").input("No such player").run()
            self.assertFalse(app.exception)
            get.assert_not_called()

    @unittest.skipUnless(
        sys.version_info[:2] == (3, 14),
        "Approved bundle is runtime-pinned to Python 3.14",
    )
    def test_missing_key_mobile_card_preview_no_http(self):
        from streamlit.testing.v1 import AppTest

        with (
            patch.dict(os.environ, {"SPORTSGAMEODDS_API_KEY": ""}),
            patch("requests.get") as get,
        ):
            app = AppTest.from_file(
                str(Path(__file__).resolve().parents[1] / "odds_value_research.py"),
                default_timeout=60,
            ).run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(any("No research API key" in v.value for v in app.info))
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
