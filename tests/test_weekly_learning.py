"""Focused learning invariants. Fixtures do not contact any provider or write production."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from weekly_learning.engine import POLICY, reconcile
from weekly_learning.sources import fetch, permitted
from weekly_learning.store import ROOT, Store, sha


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def test_immutable_bundle_and_tamper_rejection(self):
        with self.store.transaction():
            p = self.store.publish(
                "captures", "test", documents={"capture.json": {"x": 1}}
            )
        before = sha(p / "capture.json")
        with self.assertRaises(ValueError):
            self.store.publish("captures", "test", documents={"capture.json": {"x": 2}})
        self.assertEqual(sha(p / "capture.json"), before)
        (p / "capture.json").write_text("{}")
        with self.assertRaises(ValueError):
            self.store.validate(p)

    def test_concurrent_writer_fails_closed(self):
        with (
            self.store.transaction(),
            self.assertRaises(FileExistsError),
            self.store.transaction(),
        ):
            pass

    def test_holdout_new_protocol_blocked_same_plan_replay_only(self):
        with self.store.transaction():
            first = self.store.reserve_holdout("test-block", "a", fresh=False)
            same = self.store.reserve_holdout("test-block", "a", fresh=False)
            self.assertFalse(first["fresh"])
            self.assertTrue(same["replay_only"])
            with self.assertRaises(ValueError):
                self.store.reserve_holdout("test-block", "b", fresh=True)

    def test_future_registration_cannot_be_backdated(self):
        with self.assertRaises(ValueError):
            self.store.reserve_holdout(
                "past", "a", fresh=True, registered_before="2020-01-01T00:00:00+00:00"
            )

    def test_no_repository_archive_or_production_writes(self):
        for path in [
            ROOT,
            ROOT / "data",
            ROOT / "experiments" / "bad",
            ROOT / "research_inputs" / "bad",
        ]:
            with self.assertRaises(ValueError):
                Store(path)


class ResultsTests(unittest.TestCase):
    def fixture(self):
        forecast = pd.DataFrame(
            [
                {
                    "game_id": "g",
                    "player_id": "p",
                    "market": "rushing_attempts",
                    "projection": 4.0,
                    "prediction_at": "2026-11-01T17:00:00Z",
                    "team": "KC",
                    "position": "RB",
                    "expected_attempts": 30.0,
                    "expected_carries": 20.0,
                }
            ]
        )
        players = pd.DataFrame(
            [
                {
                    "game_id": "g",
                    "player_id": "p",
                    "stats_observed": True,
                    "offense_pct": 0.4,
                    "carries": 0.0,
                }
            ]
        )
        schedule = pd.DataFrame(
            [
                {
                    "game_id": "g",
                    "kickoff_at": pd.Timestamp("2026-11-01T18:00:00Z"),
                    "completed_at": pd.Timestamp("2026-11-02T02:00:00Z"),
                    "home_team": "KC",
                    "home_score": 7,
                    "away_score": 21,
                }
            ]
        )
        team = pd.DataFrame(
            [
                {
                    "game_id": "g",
                    "team": "KC",
                    "attempts": 40.0,
                    "carries": 10.0,
                    "offensive_plays": 53,
                }
            ]
        )
        return forecast, players, schedule, team

    def run_case(self, players=None):
        f, p, s, t = self.fixture()
        return reconcile(
            f,
            p if players is None else players,
            s,
            t,
            pd.Timestamp("2026-11-03T00:00:00Z"),
        )

    def test_true_zero_preserved_and_components_sum_to_error(self):
        result = self.run_case().iloc[0]
        self.assertEqual(result.status, "scored")
        self.assertEqual(result.actual, 0.0)
        self.assertAlmostEqual(
            result.team_volume_component_actual_minus_forecast
            + result.player_share_component_actual_minus_forecast,
            -result.error,
        )
        self.assertNotIn("injury caused", result.hypotheses)

    def test_missing_box_not_zero_and_no_snaps_not_inactive(self):
        _, p, _, _ = self.fixture()
        p["stats_observed"] = False
        row = self.run_case(p).iloc[0]
        self.assertEqual(row.status, "missing_box_confirmed_participation")
        self.assertTrue(np.isnan(row.actual))
        p["offense_pct"] = 0
        self.assertIn("not_proof_of_inactive", self.run_case(p).iloc[0].status)

    def test_future_result_and_postkickoff_forecast_not_scored(self):
        f, p, s, t = self.fixture()
        r = reconcile(f, p, s, t, pd.Timestamp("2026-11-01T20:00:00Z"))
        self.assertEqual(r.iloc[0].status, "game_not_available")
        f.prediction_at = "2026-11-01T19:00:00Z"
        with self.assertRaises(ValueError):
            reconcile(f, p, s, t, pd.Timestamp("2026-11-03T00:00:00Z"))

    def test_seal_blocks_before_http(self):
        policy = json.loads(POLICY.read_text())
        with patch("weekly_learning.sources.requests.get") as get:
            with self.assertRaises(ValueError):
                fetch("/tmp/not-created-learning-source", 2026, 11, policy)
            get.assert_not_called()
        permitted(2026, 10, policy)

    def test_rejected_candidate_cannot_promote(self):
        from weekly_learning.promotion import promote

        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            with self.assertRaises(ValueError):
                promote(
                    store, {"accepted": False}, ROOT, {}, json.loads(POLICY.read_text())
                )
            self.assertFalse((Path(temp) / "champion.json").exists())


@unittest.skipUnless(sys.version_info[:2] == (3, 14), "Runtime-pinned real bundle")
class ActualCycleTests(unittest.TestCase):
    def test_existing_dry_run_manifest_counts_rejection_and_seal(self):
        root = ROOT / "weekly_learning_state"
        path = root / "cycles" / "2026-w09-dryrun-v1"
        if not path.exists():
            self.skipTest("Committed dry run not built yet")
        Store(root).validate(path)
        report = json.loads((path / "report.json").read_text())
        self.assertEqual(report["candidate"]["decision"], "RETAIN_CHAMPION")
        self.assertFalse(report["candidate"]["accepted"])
        self.assertFalse(report["candidate"]["holdout"]["fresh"])
        self.assertEqual(len(report["candidate"]["markets"]), 9)
        self.assertEqual(report["next_slate"]["checks"]["forecast_rows"], 618)
        self.assertEqual(report["next_slate"]["checks"]["complete_rows"], 568)
        self.assertEqual(report["next_slate"]["checks"]["top_picks"], 22)
        self.assertEqual(report["week12_readiness"]["status"], "blocked")
        data = pd.read_parquet(path / "reconciled.parquet")
        self.assertTrue(data.week.eq(9).all())
        self.assertTrue(data[data.status.eq("scored")].actual.notna().all())

    def test_real_weekly_dashboard_no_provider_requests(self):
        import os

        from streamlit.testing.v1 import AppTest

        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic-learning",
                    "SPORTSGAMEODDS_API_KEY": "",
                    "SGO_RESEARCH_STORE": str(Path(temp) / "cache.sqlite"),
                },
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            app = AppTest.from_file(
                str(ROOT / "odds_value_research.py"), default_timeout=90
            ).run()
            app.text_input(key="research_password").input("synthetic-learning")
            app.button[0].click().run()
            app.selectbox[0].select("Weekly Learning").run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(any("Weekly Learning" in e.value for e in app.markdown))
            get.assert_not_called()
            request.assert_not_called()
