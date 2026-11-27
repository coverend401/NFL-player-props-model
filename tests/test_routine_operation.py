"""Routine scheduling, future isolation and publication gates without real future outcomes."""

import json
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from selection_learning import engine as e
from selection_learning.imports import decimal, normalise
from tests.test_line_selections import AT, panel, record
from weekly_learning.fixture_evidence import metadata_json
from weekly_learning.learning import fit_predict
from weekly_learning.store import Store


class MetadataTests(unittest.TestCase):
    def test_scores_are_skipped_not_json_decoded(self):
        raw = {
            "season": {"year": 2026, "type": 2},
            "week": {"number": 13},
            "events": [
                {
                    "id": "fixture",
                    "date": "2026-12-03T18:00Z",
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "score": "DO_NOT_DECODE",
                                    "team": {
                                        "abbreviation": "KC",
                                        "statistics": {"forbidden": 999},
                                    },
                                },
                                {
                                    "homeAway": "away",
                                    "team": {"abbreviation": "ARI"},
                                    "score": 999,
                                },
                            ]
                        }
                    ],
                    "status": {"forbidden": 999},
                }
            ],
        }
        result = metadata_json(json.dumps(raw).encode())
        self.assertNotIn("score", json.dumps(result))
        self.assertNotIn("999", json.dumps(result))
        self.assertNotIn("forbidden", json.dumps(result))
        self.assertEqual(result["week"]["number"], 13)

    def test_invalid_and_trailing_envelopes_fail(self):
        for raw in [b"{", b"{} garbage", b'{"events":{}}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                metadata_json(raw)


class LearningTests(unittest.TestCase):
    def test_future_outcomes_cannot_fit_correction(self):
        h = pd.DataFrame(
            {
                "market": "receptions",
                "week": [1, 2] * 60,
                "projection": 4.0,
                "actual": 5.0,
                "settled_at": "2026-09-22T12:00Z",
                "career_avg": 4.0,
                "recent_form": 4.0,
                "games_played_prior": 5.0,
            }
        )
        f = pd.DataFrame(
            {
                "market": ["receptions"],
                "projection": [4.0],
                "career_avg": [4.0],
                "recent_form": [4.0],
                "games_played_prior": [6.0],
                "prediction_at": ["2026-09-25T12:00Z"],
            }
        )
        result, _report = fit_predict(h, f)
        self.assertGreater(result.shrunk_market_bias.iloc[0], 4)
        self.assertGreater(result.role_residual_ridge.iloc[0], 4)
        with self.assertRaises(ValueError):
            fit_predict(h.assign(settled_at="2026-09-28T12:00Z"), f)
        other, _ = fit_predict(h, f.assign(actual=99999))
        np.testing.assert_array_equal(
            result.role_residual_ridge, other.role_residual_ridge
        )

    def test_insufficient_data_keeps_champion(self):
        f = pd.DataFrame({"market": ["receptions"], "projection": [4.0]})
        out, report = fit_predict(pd.DataFrame(), f)
        self.assertNotIn("role_residual_ridge", out)
        self.assertEqual(report[0]["status"], "insufficient_prior_prospective_data")


class QuoteTests(unittest.TestCase):
    def test_real_export_names_and_paired_prices_map_without_inventing(self):
        frame = panel()
        frame["player"] = "Synthetic Player"
        frame["position"] = "WR"
        raw = pd.DataFrame(
            [
                {
                    "player": "Synthetic Player",
                    "team": "A",
                    "market": "receptions",
                    "line": 4.5,
                    "over_odds": -110,
                    "under_odds": 100,
                    "odds_format": "american",
                    "bookmaker": "TEST",
                    "quoted_at": "2026-11-22T14:59Z",
                    "source": "synthetic test only",
                    "settlement_rule": "offensive_participation_full_refund_push",
                    "line_type": "alternate",
                }
            ]
        )
        rows = normalise(raw, frame)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["player_id"], "p1")
        self.assertAlmostEqual(rows[0]["decimal_odds"], 1 + 100 / 110)
        self.assertEqual(rows[1]["decimal_odds"], 2)
        with self.assertRaises(ValueError):
            normalise(raw.assign(player="Unknown Player"), frame)
        self.assertAlmostEqual(decimal("10/11", "fractional"), 1 + 10 / 11)

    def test_explicit_alternates_coexist_but_old_primary_does_not_resurface(self):
        r = record()
        a = {**r, "quote_id": "a", "line_type": "alternate", "line": 3.5}
        b = {**r, "quote_id": "b", "line_type": "alternate", "line": 4.5}
        self.assertEqual(len(e.eligible_quotes([a, b], now=AT)), 2)
        a["line_type"] = b["line_type"] = "primary"
        self.assertEqual(len(e.eligible_quotes([a, b], now=AT)), 1)

    def test_nested_same_stat_probability_is_not_multiplied(self):
        r = record()
        a = {**r, "quote_id": "a", "line": 3.5, "hit_probability": 0.8}
        b = {**r, "quote_id": "b", "line": 5.5, "hit_probability": 0.6}
        result = e.ticket([a, b])
        self.assertAlmostEqual(result["joint_probability"], 0.6)
        self.assertIsNone(result["expected_value"])
        opposite = {**b, "side": "under", "line": 2.5}
        self.assertEqual(e.ticket([a, opposite])["joint_probability"], 0)
        other = {**b, "player_id": "different"}
        self.assertIsNone(e.ticket([a, other])["joint_probability"])


class RoutineTests(unittest.TestCase):
    def test_prepare_is_idempotent_without_results_network_or_models(self):
        from weekly_learning.routine import prepare

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            with store.transaction():
                path = store.publish(
                    "routine_plans",
                    "existing",
                    documents={"plan.json": {"status": "prepared"}},
                )
            with patch("weekly_learning.routine.settle") as settle:
                self.assertEqual(prepare(store, "existing"), path)
                settle.assert_not_called()

    def test_early_week12_settlement_does_not_fetch(self):
        from weekly_learning.routine import settle
        from weekly_learning.store import ROOT

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            source = (
                ROOT
                / "weekly_learning_state/captures/weekly-week12-remaining-20261127/capture.json"
            )
            cap = store.root / "captures/week12"
            cap.mkdir(parents=True)
            (cap / "capture.json").write_bytes(source.read_bytes())
            with patch("weekly_learning.routine.fetch") as fetch:
                result = settle(
                    store,
                    "synthetic-no-network",
                    pd.Timestamp("2026-11-27T12:00Z").to_pydatetime(),
                )
            fetch.assert_not_called()
            self.assertTrue(result["waiting_for_authorised_cutoff"])


class PrivateRecoveryTests(unittest.TestCase):
    def test_private_settlement_retries_without_reopening_public_results(self):
        from weekly_learning.routine import settle_private

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            with store.transaction():
                store.publish(
                    "cycles",
                    "completed",
                    documents={
                        "report.json": {
                            "mode": "operational",
                            "status": "completed",
                            "admission_sha256": "admitted",
                            "capture": {
                                "game_kickoffs": {"2026_12_A_B": "2026-11-29T18:00Z"}
                            },
                        }
                    },
                )
            with (
                patch.dict(
                    "os.environ",
                    {
                        "NFL_SELECTION_GITHUB_REPOSITORY": "owner/private-test",
                        "NFL_SELECTION_GITHUB_TOKEN": "synthetic-token",
                    },
                ),
                patch("selection_learning.store.GitHubJournal"),
                patch(
                    "selection_learning.settlement.reconcile_cycle",
                    side_effect=[
                        ValueError("temporary storage outage"),
                        {"status": "reconciled"},
                    ],
                ) as reconcile,
            ):
                self.assertIn("blocked", settle_private(store)[0]["status"])
                self.assertEqual(settle_private(store)[0]["status"], "reconciled")
                self.assertEqual(settle_private(store), [])
                self.assertEqual(reconcile.call_count, 2)


class TicketSettlementTests(unittest.TestCase):
    def test_integer_push_ticket_withholds_ev_even_with_real_price_evidence(self):
        r = {**record(), "line": 4.0}
        proof = {
            "quoted_at": AT,
            "bookmaker": r["bookmaker"],
            "source": "Synthetic available ticket fixture",
            "confirmed_available": True,
            "decimal_odds": 2.0,
        }
        with patch.object(e, "datetime") as clock:
            clock.now.return_value = pd.Timestamp(AT).to_pydatetime()
            result = e.ticket([r], ticket_quote=proof)
        self.assertTrue(result["combined_price_verified_by_owner"])
        self.assertFalse(result["push_settlement_supported"])
        self.assertIsNone(result["expected_value"])
        self.assertIsNone(result["fair_odds"])


class PrivatePartitionTests(unittest.TestCase):
    def test_legacy_history_is_not_relocated_and_week_paths_are_isolated(self):
        from selection_learning.store import FILE, GitHubJournal, initial

        legacy = GitHubJournal("owner/private", "synthetic")
        a = GitHubJournal("owner/private", "synthetic", week="2026-12")
        b = GitHubJournal("owner/private", "synthetic", week="2026-13")
        self.assertEqual(legacy.file, FILE)
        self.assertNotEqual(a.file, b.file)
        state = {
            "schema": 1,
            "events": [
                {"kind": "freeze", "payload": {"records": [{"game_id": "2026_13_A_B"}]}}
            ],
        }
        with self.assertRaisesRegex(ValueError, "another weekly partition"):
            a.check_week(state)
        b.check_week(state)
        with patch.object(
            GitHubJournal, "read", return_value=(initial(), None)
        ) as read:
            a.prior_state()
            self.assertEqual(read.call_count, 4)
        with self.assertRaises(ValueError):
            a.prior_state(5)
