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
        with (
            patch("weekly_learning.sources.requests.get") as get,
            patch(
                "weekly_learning.admission.time_gate",
                side_effect=ValueError("Settlement window closed"),
            ),
        ):
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


class PromotionContractTests(unittest.TestCase):
    def fixture(self, store):
        from stage1b.data import MARKETS

        baseline = {k: {"sha256": "a" * 64} for k in MARKETS}
        challenger = {k: {"sha256": "b" * 64} for k in MARKETS}
        h = store.reserve_holdout(
            "synthetic-future",
            "plan",
            fresh=True,
            registered_before="2099-01-01T00:00:00+00:00",
            baseline_models=baseline,
            challenger_models=challenger,
        )
        rows = [
            {
                "market": k,
                "weeks": 8,
                "baseline": {"n": 100, "mae": 10},
                "relative_mae_gain": 0.03,
                "holm_rejects_no_improvement": True,
                "probability_scores": {
                    "baseline": {"brier": 0.2, "log_loss": 0.6},
                    "candidate": {"brier": 0.19, "log_loss": 0.59},
                },
            }
            for k in MARKETS
        ]
        candidate = {
            "accepted": True,
            "statistical_gate": True,
            "holdout": h,
            "plan_sha256": "plan",
            "first_holdout_kickoff": "2099-01-01T01:00:00+00:00",
            "baseline_models": baseline,
            "challenger_models": challenger,
            "markets": rows,
            "candidate_release_sha256": "digest",
        }
        return candidate, baseline, challenger

    def test_acceptance_requires_certification_and_cannot_reuse_holdout(self):
        from weekly_learning.promotion import promote

        policy = json.loads(POLICY.read_text())
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            with store.transaction():
                candidate, baseline, challenger = self.fixture(store)
                manifest = {"release_id": "synthetic-certified", "models": challenger}
                release = (
                    Path(temp) / "research_inference_releases" / "synthetic-certified"
                )
                release.mkdir(parents=True)
                (release / "manifest.json").write_text(json.dumps(manifest))
                with (
                    patch("weekly_learning.promotion.ROOT", Path(temp)),
                    patch(
                        "weekly_learning.promotion.validate_inference",
                        return_value={"exact_replay": True},
                    ) as verify,
                    patch("weekly_learning.promotion.sha", return_value="digest"),
                ):
                    result = promote(
                        store,
                        candidate,
                        release,
                        baseline,
                        policy,
                    )
                    self.assertEqual(result["rollback_models"], baseline)
                    verify.assert_called_once()
                self.assertTrue((Path(temp) / "champion.json").exists())
                with self.assertRaises(ValueError):
                    promote(
                        store,
                        candidate,
                        release,
                        baseline,
                        policy,
                    )

    def test_missing_market_rejected_before_release_access(self):
        from weekly_learning.promotion import promote

        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            with store.transaction():
                candidate, baseline, _ = self.fixture(store)
                candidate["markets"] = candidate["markets"][:-1]
                with patch("weekly_learning.promotion.validate_inference") as verify:
                    with self.assertRaises(ValueError):
                        promote(
                            store,
                            candidate,
                            ROOT
                            / "research_inference_releases"
                            / "synthetic-certified",
                            baseline,
                            json.loads(POLICY.read_text()),
                        )
                    verify.assert_not_called()
            self.assertFalse((Path(temp) / "champion.json").exists())


class SelectionFailureTests(unittest.TestCase):
    def run_cycle(self, temp, *, fail_readiness=False):
        from weekly_learning.cli import operational

        root = Path(temp)
        store = Store(root / "state")
        cap = root / "capture"
        cap.mkdir()
        (cap / "capture.json").write_text(json.dumps({"models": {}}))
        (cap / "release_manifest.json").write_text(
            json.dumps({"model_parent": {"path": "parent"}})
        )
        f, p, s, t = ResultsTests().fixture()
        f["market"] = "Rushing Attempts"
        f["week"] = 9
        f["projection_status"] = "complete"
        f.to_parquet(cap / "forecasts.parquet", index=False)
        source = root / "sources"
        source.mkdir()
        (source / "sources.json").write_text("{}")
        pointer = root / "research_active_inference.json"
        pointer.write_text(json.dumps({"release_id": "previous"}))
        release = root / "research_inference_releases" / "weekly-test"
        release.mkdir(parents=True)
        (release / "manifest.json").write_text(
            json.dumps(
                {
                    "release_id": "weekly-test",
                    "certification": {
                        "status": "passed",
                        "checks": {"exact_replay": True},
                    },
                }
            )
        )
        original_publish = store.publish

        def publication(kind, *args, **kwargs):
            if fail_readiness and kind == "readiness":
                raise ValueError("Synthetic readiness storage failure")
            return original_publish(kind, *args, **kwargs)

        with (
            patch("weekly_learning.cli.ROOT", root),
            patch("weekly_learning.cli.capture", return_value=cap),
            patch("weekly_learning.cli.freeze_prepared"),
            patch("weekly_learning.cli.load_results", return_value=(p, s, t)),
            patch(
                "weekly_learning.cli.retained_decision",
                return_value={"accepted": False},
            ),
            patch("weekly_learning.forecast.prepare_next", return_value=release),
            patch.object(store, "publish", side_effect=publication),
        ):
            operational(store, 9, 10, "test", source)
        return json.loads(pointer.read_text())

    def test_readiness_write_failure_preserves_previous_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(
                self.run_cycle(temp, fail_readiness=True), {"release_id": "previous"}
            )

    def test_certified_candidate_requires_separate_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.run_cycle(temp)["release_id"], "previous")


class SourceIntegrityTests(unittest.TestCase):
    def test_changed_source_is_rejected_before_materialisation(self):
        from weekly_learning.sources import verify_snapshot

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "players.parquet"
            raw.write_bytes(b"synthetic-source")
            record = {
                "players": {
                    "url": "https://github.com/nflverse/nflverse-data/releases/download/players/players.parquet",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "sha256": sha(raw),
                }
            }
            (root / "sources.json").write_text(json.dumps(record))
            self.assertEqual(verify_snapshot(root), record)
            with self.assertRaisesRegex(ValueError, "stale"):
                verify_snapshot(root, max_age_hours=48)
            raw.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "integrity"):
                verify_snapshot(root)

    def test_unapproved_source_or_future_timestamp_is_rejected(self):
        from weekly_learning.sources import verify_snapshot

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "players.parquet"
            raw.write_bytes(b"synthetic-source")
            record = {
                "players": {
                    "url": "https://invalid.example/players",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "sha256": sha(raw),
                }
            }
            (root / "sources.json").write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                verify_snapshot(root)
            record["players"]["url"] = (
                "https://github.com/nflverse/nflverse-data/releases/download/players/players.parquet"
            )
            record["players"]["retrieved_at"] = "2099-01-01T00:00:00+00:00"
            (root / "sources.json").write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                verify_snapshot(root)
