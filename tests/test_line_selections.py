"""Synthetic quote/settlement tests: no real odds, outcomes, network or seal access."""

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from selection_learning import engine as e
from selection_learning.settlement import (
    freeze,
    performance,
    reconcile_cycle,
    settle_records,
)
from selection_learning.store import (
    GitHubJournal,
    StorageError,
    append,
    initial,
    validate,
)

AT = "2026-11-22T15:00Z"


def panel():
    return pd.DataFrame(
        [
            {
                "game_id": "2026_11_A_B",
                "player_id": "p1",
                "market": "receptions",
                "kickoff_at": "2026-11-22T18:00Z",
                "selection_built_at": "2026-11-21T20:00Z",
                "player": "Synthetic player",
                "team": "A",
                "opponent": "B",
                "enhanced_projection": 5.0,
                "baseline": 4.0,
                "probability_mode": "research_empirical",
                "probability_supported": True,
                "calibration_gap": 0.03,
                "diagnostic_n": 300,
                "history_n": 8,
                "recent_opportunities": 7.0,
                "relative_width": 1.5,
                "role_variability": 0.1,
                "why_pick": "Synthetic workload evidence only.",
                "principal_risk": "Synthetic uncertainty.",
                "optional_missing": float("nan"),
            }
        ]
    )


def quote(**changes):
    return {
        "game_id": "2026_11_A_B",
        "player_id": "p1",
        "market": "receptions",
        "side": "over",
        "line": 4.5,
        "decimal_odds": 1.8,
        "bookmaker": "SYNTHETIC",
        "source": "unit test only",
        "quoted_at": "2026-11-22T14:59Z",
        "settlement_rule": "offensive_participation_full_refund_push",
        **changes,
    }


def price(row, line, odds, side, refund):
    probability = 0.7 if side == "over" else 0.3
    return {
        "over": 0.7,
        "under": 0.3,
        "push": 0.0,
        "expected_profit_per_unit": probability * odds - 1,
    }


def record(**changes):
    return e.evaluate(
        quote(**changes),
        panel(),
        now=AT,
        pricing=price,
        evidence=lambda *args: {"supported": True, "scope": "synthetic test evidence"},
    )


def policy():
    return {
        "operational_settlement_approved": True,
        "operational_scope": {
            "season": 2026,
            "first_week": 11,
            "last_week": 18,
            "not_before": "2026-11-24T12:00Z",
        },
    }


class PropositionTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(
            e,
            "band_evidence",
            return_value={"supported": True, "scope": "synthetic test evidence"},
        )
        guard.start()
        self.addCleanup(guard.stop)

    def test_actual_line_and_price_used_and_ev_separate_from_hit_rank(self):
        pricing = Mock(side_effect=price)
        r = e.evaluate(
            quote(line=6.5, decimal_odds=2.2), panel(), now=AT, pricing=pricing
        )
        self.assertEqual(pricing.call_args.args[1:4], (6.5, 2.2, "over"))
        self.assertAlmostEqual(r["expected_profit_per_unit"], 0.54)
        low_ev = {
            **r,
            "quote_id": "low-ev",
            "expected_profit_per_unit": -0.2,
            "hit_probability": 0.8,
        }
        high_ev = {
            **r,
            "player_id": "p2",
            "quote_id": "high-ev",
            "hit_probability": 0.6,
            "expected_profit_per_unit": 1.0,
        }
        self.assertEqual(
            e.rankings([high_ev, low_ev], now=AT)[0][0]["quote_id"], "low-ev"
        )

    def test_reject_stale_future_cutoff_integer_and_ambiguous(self):
        for changes in [
            {"quoted_at": "2026-11-22T14:00Z"},
            {"quoted_at": "2026-11-22T15:01Z"},
            {"line": 4},
            {"line": float("nan")},
            {"decimal_odds": float("inf")},
            {"side": "x"},
            {"player_id": "absent"},
            {"settlement_rule": "anything"},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                e.evaluate(quote(**changes), panel(), now=AT, pricing=price)
        with self.assertRaises(ValueError):
            e.evaluate(
                quote(quoted_at="2026-11-22T17:00Z"),
                panel(),
                now="2026-11-22T17:00Z",
                pricing=price,
            )
        with self.assertRaises(ValueError):
            e.evaluate(quote(), pd.concat([panel(), panel()]), now=AT, pricing=price)

    def test_uncalibrated_normal_or_missing_opportunity_never_ranked(self):
        for k, v in [
            ("probability_mode", "original_normal"),
            ("probability_supported", False),
            ("recent_opportunities", float("nan")),
            ("role_variability", float("nan")),
            ("diagnostic_n", 10),
        ]:
            f = panel()
            f.loc[0, k] = v
            r = e.evaluate(quote(), f, now=AT, pricing=price)
            self.assertEqual(e.rankings([r], now=AT), ([], {}))

    def test_expiry_withdrawal_and_unique_player_slots(self):
        r = record()
        self.assertEqual(len(e.rankings([r], now=AT)[0]), 1)
        self.assertEqual(e.rankings([r], now="2026-11-22T15:30Z"), ([], {}))
        withdrawn = {**r, "status": "withdrawn", "retrieved_at": "2026-11-22T15:01Z"}
        self.assertEqual(e.rankings([r, withdrawn], now="2026-11-22T15:02Z"), ([], {}))
        _, games = e.rankings(
            [r, {**r, "bookmaker": "OTHER", "quote_id": "other"}], now=AT
        )
        self.assertEqual(len(games[r["game_id"]]), 1)
        better = {
            **r,
            "bookmaker": "BETTER SYNTHETIC",
            "quote_id": "better",
            "decimal_odds": 2.0,
        }
        self.assertEqual(e.rankings([r, better], now=AT)[0][0]["quote_id"], "better")

    def test_ticket_withholds_unsupported_joint_ev_and_marks_dependence(self):
        r = record()
        other = {**r, "quote_id": "other", "player_id": "p2", "hit_probability": 0.6}
        t = e.ticket([r, other], 3.0)
        self.assertAlmostEqual(t["probability_lower_bound"], 0.3)
        self.assertEqual(t["probability_upper_bound"], 0.6)
        self.assertIsNone(t["joint_probability"])
        self.assertIsNone(t["expected_value"])
        self.assertIn("Same offence", t["dependencies"][0])
        self.assertIn("scenario", str(e.season_scenario(0.1, 18)))


class FreezeSettlementTests(unittest.TestCase):
    def setUp(self):
        self.r = record()
        self.state = freeze(
            initial(),
            [self.r],
            now=AT,
            release_id="synthetic",
            forecast_manifest_sha256="test-only",
        )

    def test_immutable_capture_and_duplicate_prevention(self):
        original = copy.deepcopy(self.state)
        validate(self.state)
        with self.assertRaises(ValueError):
            freeze(
                self.state,
                [self.r],
                now=AT,
                release_id="synthetic",
                forecast_manifest_sha256="test-only",
            )
        with self.assertRaises(ValueError):
            freeze(
                initial(),
                [self.r],
                now="2026-11-22T17:01Z",
                release_id="synthetic",
                forecast_manifest_sha256="test-only",
            )
        broken = copy.deepcopy(self.state)
        broken["events"][0]["payload"]["records"][0]["line"] = 999
        with self.assertRaises(StorageError):
            validate(broken)
        self.assertEqual(self.state, original)

    def test_zero_settled_missing_not_zero_and_metrics_idempotent(self):
        actual = pd.DataFrame(
            [
                {
                    "game_id": self.r["game_id"],
                    "player_id": "p1",
                    "market": "receptions",
                    "status": "scored",
                    "actual": 0.0,
                    "completed_at": "2026-11-22T22:00Z",
                }
            ]
        )
        out = settle_records(
            self.state,
            actual,
            now="2026-11-24T12:01Z",
            policy=policy(),
            receipt_id="synthetic",
        )
        self.assertEqual(out["events"][-1]["payload"]["status"], "loss")
        self.assertEqual(out["events"][-1]["payload"]["outcome"], 0.0)
        self.assertEqual(performance(out)["top_picks"]["hit_rate_excluding_push"], 0.0)
        self.assertEqual(performance(out)["top_picks"]["hypothetical_paper_roi"], -1.0)
        self.assertIsNone(performance(out)["top_picks"]["actual_roi"])
        self.assertEqual(
            settle_records(
                out,
                actual,
                now="2026-11-24T12:02Z",
                policy=policy(),
                receipt_id="synthetic",
            ),
            out,
        )
        invalid = actual.assign(actual=2.5)
        with self.assertRaisesRegex(ValueError, "Invalid count"):
            settle_records(
                self.state,
                invalid,
                now="2026-11-24T12:01Z",
                policy=policy(),
                receipt_id="synthetic",
            )
        actual.loc[0, "status"] = "missing_stat"
        self.assertEqual(
            settle_records(
                self.state,
                actual,
                now="2026-11-24T12:01Z",
                policy=policy(),
                receipt_id="synthetic",
            ),
            self.state,
        )

    def test_closed_gate_prevents_all_result_reads(self):
        journal = Mock()
        journal.read.return_value = self.state, "sha"
        with (
            patch("selection_learning.settlement.pd.read_parquet") as reader,
            self.assertRaisesRegex(ValueError, "Settlement window closed"),
        ):
            reconcile_cycle(journal, "nonexistent", now="2026-11-23T15:00Z")
        reader.assert_not_called()
        journal.write.assert_not_called()


class OperationalIntegrationTests(unittest.TestCase):
    def test_admitted_cycle_to_immutable_report_and_idempotent_replay(self):
        from weekly_learning.store import Store, sha

        class MemoryJournal:
            def __init__(self, state):
                self.state = state

            def read(self):
                return self.state, "synthetic-version"

            def write(self, before, after, version):
                self.state = after

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "weekly_learning").mkdir()
            (root / "weekly_learning/policy.json").write_text(json.dumps(policy()))
            source = root / "weekly_learning_state/sources/synthetic"
            source.mkdir(parents=True)
            (source / "sources.json").write_text("{}")
            receipt = source / "operational_admission.json"
            receipt.write_text('{"synthetic_receipt":true}')
            r = record()
            captured = freeze(
                initial(),
                [r],
                now=AT,
                release_id="synthetic",
                forecast_manifest_sha256="synthetic",
            )
            actuals = pd.DataFrame(
                [
                    {
                        "game_id": r["game_id"],
                        "player_id": r["player_id"],
                        "market": r["market"],
                        "status": "scored",
                        "actual": 6.0,
                        "completed_at": "2026-11-22T22:00Z",
                    }
                ]
            )
            store = Store(root / "weekly_learning_state")
            with store.transaction():
                cycle = store.publish(
                    "cycles",
                    "synthetic",
                    frames={"reconciled.parquet": actuals},
                    documents={
                        "report.json": {
                            "mode": "operational",
                            "status": "completed",
                            "admission_sha256": sha(receipt),
                            "sources_sha256": sha(source / "sources.json"),
                        }
                    },
                )
            journal = MemoryJournal(captured)
            with (
                patch("selection_learning.settlement.ROOT", root),
                patch("selection_learning.settlement.validate_receipt") as validator,
            ):
                result = reconcile_cycle(journal, cycle, now="2026-11-24T12:01Z")
                validator.assert_called_once()
                self.assertEqual(
                    result["metrics"]["top_picks"]["hit_rate_excluding_push"], 1.0
                )
                self.assertAlmostEqual(
                    result["metrics"]["top_picks"]["hypothetical_paper_roi"], 0.8
                )
                before = copy.deepcopy(journal.state)
                reconcile_cycle(journal, cycle, now="2026-11-24T12:02Z")
                self.assertEqual(journal.state, before)


class PrivatePersistenceTests(unittest.TestCase):
    def test_no_shared_quota_public_repo_or_missing_token(self):
        for repo, token in [
            ("coverend401/nfl-props-research-quota", "synthetic"),
            ("coverend401/NFL-player-props-model", "synthetic"),
            ("owner/private", None),
            ("owner/private", " quoted "),
        ]:
            with self.assertRaises(StorageError):
                GitHubJournal(repo, token)
        client = GitHubJournal("owner/private", "synthetic")
        with (
            patch.object(
                client,
                "call",
                return_value={"private": False, "full_name": "owner/private"},
            ),
            self.assertRaises(StorageError),
        ):
            client.read()

    def test_cas_preserves_history_readback_and_conflicts_not_retried(self):
        client = GitHubJournal("owner/private", "synthetic")
        before = initial()
        after = append(before, "weekly_report", "test", AT, {"sample_size": 0})
        with (
            patch.object(client, "call") as call,
            patch.object(client, "read", return_value=(after, "new")),
        ):
            client.write(before, after, "old")
            self.assertEqual(call.call_args.args[2]["sha"], "old")
        with (
            patch.object(
                client, "call", side_effect=StorageError("concurrent update")
            ) as call,
            self.assertRaises(StorageError),
        ):
            client.write(before, after, "old")
        self.assertEqual(call.call_count, 1)
        with self.assertRaises(StorageError):
            client.write(after, before, "sha")

    def test_explicit_bearer_no_managed_substitution_or_secret_errors(self):
        response = Mock(status_code=401)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        request = Mock(return_value=response)
        client = GitHubJournal("owner/private", "synthetic-token", request=request)
        with self.assertRaises(StorageError) as error:
            client.call("GET")
        self.assertNotIn("synthetic-token", str(error.exception))
        auth = request.call_args.kwargs["auth"]
        req = Mock(headers={})
        auth(req)
        self.assertEqual(req.headers["Authorization"], "Bearer synthetic-token")


class BandEvidenceTests(unittest.TestCase):
    def test_unique_player_games_position_and_season_filters(self):
        data = pd.DataFrame(
            [
                {
                    "game_id": str(i),
                    "player_id": str(i),
                    "market": "receptions",
                    "position": "WR",
                    "hypothetical_line": 4.5,
                    "season": 2025,
                    "method": "research_empirical",
                    "p_over": 0.7,
                    "observed_over": int(i < 70),
                    "week": i % 10 + 1,
                }
                for i in range(100)
            ]
        )
        row = {"market": "receptions", "position": "WR"}
        good = e.band_evidence(row, 0.7, "over", data=data)
        self.assertTrue(good["supported"])
        self.assertEqual(good["player_games"], 100)
        duplicate = pd.concat([data.iloc[:1]] * 100)
        self.assertFalse(e.band_evidence(row, 0.7, "over", data=duplicate)["supported"])
        self.assertFalse(
            e.band_evidence({**row, "position": "RB"}, 0.7, "over", data=data)[
                "supported"
            ]
        )
        self.assertFalse(e.band_evidence(row, 0.99, "over", data=data)["supported"])
        future = data.assign(season=2026)
        self.assertFalse(e.band_evidence(row, 0.7, "over", data=future)["supported"])


class PublicLogPrivacyTests(unittest.TestCase):
    def test_cli_never_prints_private_metrics_to_public_actions_logs(self):
        from selection_learning import cli

        output = io.StringIO()
        with (
            patch("sys.argv", ["selection_learning", "--cycle", "synthetic"]),
            patch.object(cli, "GitHubJournal"),
            patch.object(
                cli,
                "reconcile_cycle",
                return_value={
                    "status": "reconciled",
                    "metrics": {"private_account_performance": "must-not-be-public"},
                },
            ),
            patch("sys.stdout", output),
        ):
            cli.main()
        self.assertEqual(
            json.loads(output.getvalue()),
            {"status": "reconciled", "private_report_written": True},
        )
        self.assertNotIn("must-not-be-public", output.getvalue())
