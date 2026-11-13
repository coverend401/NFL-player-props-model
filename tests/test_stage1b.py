"""Stage 1B tests use synthetic fixtures, never historical betting evidence."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from scipy.stats import poisson

from stage1b.data import (
    prepare_panel,
    market_panel,
    read_development_snapshot,
    feature_columns,
    STATS,
)
from stage1b.probability import Distribution, Calibration, outcomes, inverse_cdf
from stage1b.betting import economics, no_vig, edge_assessment
from stage1b.backtest import verify_quotes, settle_single, account
from stage1b.runner import fit_fold, evaluate_fold
from stage1b.metrics import week_block_interval, binary_scores

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "stage1b/protocol.json").read_text())


def fixture():
    rows = []
    for season in [2019, 2020, 2021, 2022]:
        for week in range(1, 19):
            for player in range(12):
                kickoff = pd.Timestamp(f"{season}-09-01", tz="UTC") + pd.Timedelta(
                    weeks=week - 1
                )
                y = float((player + week * 3) % 11)
                r = dict(
                    player_id=f"p{player}",
                    player_display_name=f"Player {player}",
                    position="QB",
                    team="A",
                    season=season,
                    week=week,
                    game_id=f"{season}-{week}",
                    kickoff_at=kickoff,
                    completed_at=kickoff + pd.Timedelta(hours=8),
                    offense_pct=50.0,
                    stats_observed=True,
                )
                r.update({s: y for s in STATS})
                rows.append(r)
    return pd.DataFrame(rows)


class TemporalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = fixture()
        cls.panel = prepare_panel(cls.source, PROTOCOL)

    def test_zero_games_byes_and_season_boundary_manual_history(self):
        d = (
            self.source[(self.source.player_id == "p0") & (self.source.season == 2021)]
            .iloc[:4]
            .copy()
        )
        d["attempts"] = [0.0, 4.0, 8.0, 12.0]
        d["week"] = [1, 2, 4, 6]
        p = prepare_panel(d, PROTOCOL)
        self.assertEqual(p.iloc[3].attempts_last3_avg, 4.0)
        self.assertEqual(p.iloc[3].games_played_prior, 3)
        d = pd.concat(
            [
                d,
                self.source[
                    (self.source.player_id == "p0") & (self.source.season == 2022)
                ].iloc[:1],
            ]
        )
        p = prepare_panel(d, PROTOCOL)
        self.assertEqual(p.iloc[-1].games_played_prior, 4)
        self.assertTrue(p.iloc[-1].returning)

    def test_missing_outcome_is_not_zero(self):
        d = (
            self.source[(self.source.player_id == "p0") & (self.source.season == 2021)]
            .iloc[:4]
            .copy()
        )
        d.loc[d.index[1], "attempts"] = np.nan
        p = prepare_panel(d, PROTOCOL)
        self.assertTrue(pd.isna(p.iloc[-1].attempts_last3_avg))
        m = market_panel(p, "passing_attempts")
        self.assertFalse(m.iloc[-1].feature_complete)

    def test_current_outcome_and_snaps_do_not_change_pregame_features(self):
        d = self.source.copy()
        idx = d[(d.player_id == "p0") & (d.season == 2021) & (d.week == 8)].index[0]
        baseline = self.panel.query("player_id=='p0' and season==2021 and week==8")
        d.loc[idx, STATS] = 99999
        d.loc[idx, "offense_pct"] = 0
        changed = prepare_panel(d, PROTOCOL).query(
            "player_id=='p0' and season==2021 and week==8"
        )
        pd.testing.assert_frame_equal(
            baseline[feature_columns("passing_attempts")],
            changed[feature_columns("passing_attempts")],
        )

    def test_final_period_excluded_before_features_and_parquet_materialisation(self):
        extra = self.source.iloc[:1].copy()
        extra["season"] = 2026
        extra["week"] = 11
        extra["kickoff_at"] = pd.Timestamp("2026-11-20T01:15Z")
        extra["completed_at"] = pd.Timestamp("2026-11-20T09:15Z")
        extra[STATS] = 1e9
        source = pd.concat([self.source, extra], ignore_index=True)
        pd.testing.assert_frame_equal(self.panel, prepare_panel(source, PROTOCOL))
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "source.parquet"
            source.to_parquet(path, index=False)
            self.assertEqual(
                len(read_development_snapshot(path, PROTOCOL)), len(self.source)
            )

    def test_delayed_availability_blocks_future_history(self):
        d = self.source.copy()
        idx = d[(d.player_id == "p0") & (d.season == 2021) & (d.week == 3)].index[0]
        d.loc[idx, "completed_at"] = pd.Timestamp("2021-12-31T00:00Z")
        p = prepare_panel(d, PROTOCOL).query(
            "player_id=='p0' and season==2021 and week==8"
        )
        self.assertFalse(p.iloc[0].history_available)

    def test_future_evaluation_labels_cannot_select_model_or_calibration(self):
        d = market_panel(self.panel, "passing_attempts")
        b, info, scores = fit_fold(d, "passing_attempts", 2022, PROTOCOL)
        changed = d.copy()
        changed.loc[changed.season == 2022, "y"] = 99999
        b2, info2, scores2 = fit_fold(changed, "passing_attempts", 2022, PROTOCOL)
        self.assertEqual(info, info2)
        self.assertEqual(scores, scores2)
        self.assertLess(
            pd.Timestamp(info["maximum_selection_outcome"]),
            pd.Timestamp(info["selection_cutoff"]),
        )
        f, p, c, diagnostic = evaluate_fold(b, d, 2022, PROTOCOL)
        self.assertTrue((f.history_available_at < f.prediction_at).all())
        self.assertGreater(c["observed_zero_outcomes"], 0)
        self.assertEqual(
            p.line_kind.unique().tolist(),
            ["hypothetical_pregame_halfline_NOT_BOOKMAKER"],
        )


class DistributionTests(unittest.TestCase):
    def test_empirical_integer_push_hand_calculation(self):
        d = Distribution("empirical", True).fit(
            np.array([2.0, 2.0, 2.0]), np.array([0.0, 2.0, 4.0])
        )
        p = outcomes(d.cdf(np.array([2.0])), np.array([2.0]))
        np.testing.assert_allclose(p, [[1 / 3, 1 / 3, 1 / 3]])

    def test_negative_yardage_and_zero_hurdle(self):
        d = Distribution("hurdle", False).fit(np.ones(3), np.array([-2.0, 0.0, 4.0]))
        p = outcomes(
            d.cdf(np.array([1.0]), zero_probability=np.array([0.4])), np.array([0.0])
        )
        np.testing.assert_allclose(p, [[0.3, 0.3, 0.4]])

    def test_poisson_support_and_halfline_no_push(self):
        d = Distribution("poisson", True).fit(np.ones(10) * 4, np.arange(10))
        c = d.cdf(np.array([4.0, 4.0]))
        p = outcomes(c, np.array([-0.5, 4.5]))
        self.assertEqual(p[0, 1], 0)
        self.assertEqual(p[1, 2], 0)
        self.assertAlmostEqual(p[1, 0], poisson.sf(4, 4))
        np.testing.assert_allclose(p.sum(axis=1), 1)

    def test_negative_binomial_overdispersion_and_finite_tails(self):
        d = Distribution("negative_binomial", True).fit(
            np.ones(6) * 3, np.array([0, 0, 0, 1, 7, 20])
        )
        self.assertGreater(d.alpha, 0)
        p = outcomes(d.cdf(np.ones(3) * 3), np.array([0, 3, 100]))
        self.assertTrue(np.isfinite(p).all())
        np.testing.assert_allclose(p.sum(axis=1), 1)

    def test_monotone_calibration_keeps_push_partition(self):
        for method in ["sigmoid", "isotonic"]:
            cal = Calibration(method).fit(
                np.linspace(0.01, 0.99, 100), np.r_[np.ones(50), np.zeros(50)]
            )
            mapped = cal(np.linspace(0, 1, 101))
            self.assertTrue((np.diff(mapped) >= -1e-10).all())
            self.assertEqual(mapped[0], 0)
            self.assertEqual(mapped[-1], 1)
            d = Distribution("normal_oos", True).fit(
                np.ones(100) * 3, np.arange(100) % 7
            )
            p = outcomes(cal.cdf(d.cdf(np.ones(3) * 3)), np.array([0.0, 2.0, 4.0]))
            np.testing.assert_allclose(p.sum(axis=1), 1)
            self.assertTrue((p >= 0).all())

    def test_quantile_crossing_is_rearranged(self):
        d = Distribution("quantile", True).fit(np.ones(5), np.arange(5))
        c = d.cdf(np.ones(3), quantiles=np.array([[5, 1, 3]] * 3))
        self.assertTrue(np.all(np.diff(c(np.array([0, 2, 6]))) >= 0))
        self.assertTrue(np.isfinite(inverse_cdf(c, 3, 0.5)).all())

    def test_invalid_probability_and_nonmonotone_cdf_rejected(self):
        with self.assertRaises(ValueError):
            binary_scores(np.array([1.1]), np.array([1]))
        with self.assertRaises(ValueError):
            outcomes(lambda x: 1 - x / 10, np.array([2.0]))


class EconomicTests(unittest.TestCase):
    def test_push_ev_fair_odds_and_kelly_hand_calculation(self):
        r = economics(0.5, 0.1, 2.0)
        self.assertAlmostEqual(r["ev_per_unit"], 0.1)
        self.assertAlmostEqual(r["fair_decimal_odds"], 1.8)
        self.assertAlmostEqual(r["kelly_fraction"], 1 / 9)
        self.assertEqual(economics(0, 1, 2.0)["kelly_fraction"], 0)

    def test_margin_and_default_zero_stake(self):
        v = no_vig(1.91, 1.91)
        self.assertAlmostEqual(v["over_conditional_no_push"], 0.5)
        self.assertGreater(v["overround"], 0)
        r = edge_assessment([[0.7, 0.3, 0]], 2.0, n_calibration_games=1000)
        self.assertEqual(r["fractional_kelly_stake"], 0)

    def test_initial_loss_counts_in_drawdown_and_push_void_refunds(self):
        rows = []
        for i, (y, side, action) in enumerate(
            [(1, "Over", "action"), (2, "Over", "action"), (5, "Over", "void")]
        ):
            rows.append(
                dict(
                    quote_id=str(i),
                    decision_at=f"2023-01-0{i + 1}T00:00Z",
                    outcome_available_at=f"2023-01-0{i + 1}T12:00Z",
                    stake=1.0,
                    outcome=y,
                    line=2.0,
                    side=side,
                    odds=2.0,
                    action_status=action,
                    participation_verified=True,
                    positive_offensive_participation=True,
                    official_void_verified=True,
                )
            )
        b, s = account(pd.DataFrame(rows), 100)
        self.assertEqual(s["profit"], -1)
        self.assertEqual(s["maximum_drawdown"], 1)
        self.assertEqual(s["pushes"], 1)
        self.assertEqual(s["voids"], 1)
        self.assertEqual(s["ending_bankroll"], 99)

    def test_unknown_action_not_turned_into_void(self):
        row = dict(
            stake=1,
            decision_at="2023-01-01T00:00Z",
            outcome_available_at="2023-01-02T00:00Z",
            action_status="unknown",
        )
        self.assertEqual(settle_single(row)[0], "unresolved")
        row["action_status"] = "void"
        with self.assertRaises(ValueError):
            settle_single(row)

    def test_concurrent_stakes_reserve_cash(self):
        b = pd.DataFrame(
            [
                dict(
                    quote_id=str(i),
                    decision_at="2023-01-01T00:00Z",
                    outcome_available_at="2023-01-02T00:00Z",
                    stake=60.0,
                    outcome=4,
                    line=2,
                    side="Over",
                    odds=2,
                    action_status="action",
                    participation_verified=True,
                    positive_offensive_participation=True,
                )
                for i in range(2)
            ]
        )
        with self.assertRaisesRegex(ValueError, "unreserved"):
            account(b, 100)

    def test_block_bootstrap_reproducible(self):
        d = pd.DataFrame(
            {"season": [2023] * 8, "week": range(1, 9), "delta": np.arange(8) - 3}
        )
        self.assertEqual(
            week_block_interval(d, "delta", reps=50),
            week_block_interval(d, "delta", reps=50),
        )


class QuoteEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.quote = dict(
            quote_id="q1",
            bookmaker="TEST_ONLY",
            game_id="g",
            player_id="p",
            market="receptions",
            side="Over",
            line=2.5,
            odds=1.91,
            quoted_at="2023-01-01T00:00Z",
            available_at="2023-01-01T00:00Z",
            decision_at="2023-01-01T00:01Z",
            kickoff_at="2023-01-01T01:01Z",
            rule_id="offensive_snap_action_v1",
            evidence_id="e1",
        )
        raw = self.root / "original.json"
        raw.write_text('{"synthetic_test_only": true}')
        extract = self.root / "extract.json"
        extract.write_text(json.dumps({"quotes": [self.quote]}))
        self.evidence = {
            "e1": dict(
                classification="authentic_provider_archive",
                reviewed_by="SYNTHETIC_UNIT_TEST_NOT_AUTHENTIC",
                licence_confirmed=True,
                path="extract.json",
                sha256=hashlib.sha256(extract.read_bytes()).hexdigest(),
                original_path="original.json",
                original_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                provider_host="example.com",
                source_url="https://example.com/archive",
            )
        }

    def test_bound_quote_is_accepted_by_integrity_logic_only(self):
        q = verify_quotes(pd.DataFrame([self.quote]), self.evidence, self.root)
        self.assertEqual(len(q), 1)

    def test_fabricated_price_or_unreviewed_source_rejected(self):
        quote = self.quote.copy()
        quote["odds"] = 2.5
        with self.assertRaisesRegex(ValueError, "differs"):
            verify_quotes(pd.DataFrame([quote]), self.evidence, self.root)
        self.evidence["e1"]["classification"] = "synthetic"
        with self.assertRaisesRegex(ValueError, "Provenance"):
            verify_quotes(pd.DataFrame([self.quote]), self.evidence, self.root)

    def test_postkickoff_and_duplicate_quotes_rejected(self):
        quote = self.quote.copy()
        quote["decision_at"] = "2023-01-01T02:00Z"
        with self.assertRaises(ValueError):
            verify_quotes(pd.DataFrame([quote]), self.evidence, self.root)
        with self.assertRaises(ValueError):
            verify_quotes(pd.DataFrame([self.quote] * 2), self.evidence, self.root)

    def test_modified_original_evidence_rejected(self):
        (self.root / "original.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Original"):
            verify_quotes(pd.DataFrame([self.quote]), self.evidence, self.root)


class ArchiveGuardTests(unittest.TestCase):
    def setUp(self):
        from stage1b.artifacts import digest, sources

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.input = (
            ROOT
            / "release_candidates/stage1a-20261113-py314-arrow24-r2/data/player_features.parquet"
        )
        (self.path / "result.txt").write_text("research artifact")
        self.manifest = {
            "status": "passed",
            "final_period_sealed": True,
            "files": {"result.txt": digest(self.path / "result.txt")},
            "input_relative_path": str(self.input.relative_to(ROOT)),
            "input_sha256": digest(self.input),
            "source_hashes": {
                str(p.relative_to(ROOT)): digest(p) for p in sources(ROOT)
            },
        }
        (self.path / "manifest.json").write_text(json.dumps(self.manifest))

    def test_payload_tampering_rejected(self):
        from stage1b.artifacts import validate

        validate(self.path, ROOT, check_runtime=False)
        (self.path / "result.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "payload"):
            validate(self.path, ROOT, check_runtime=False)

    def test_extra_unmanifested_file_rejected(self):
        from stage1b.artifacts import validate

        (self.path / "unreviewed.txt").write_text("extra")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            validate(self.path, ROOT, check_runtime=False)

    def test_source_provenance_required(self):
        from stage1b.artifacts import validate

        self.manifest["source_hashes"].pop("stage1b/protocol.json")
        (self.path / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "provenance"):
            validate(self.path, ROOT, check_runtime=False)


class FullQuoteBacktestTests(QuoteEvidenceTests):
    def forecast(self):
        return pd.DataFrame(
            [
                dict(
                    game_id="g",
                    player_id="p",
                    market="receptions",
                    line=2.5,
                    decision_at=self.quote["decision_at"],
                    history_available_at="2022-12-31T00:00Z",
                    model_fit_available_at="2022-12-01T00:00Z",
                    p_over=0.7,
                    p_under=0.3,
                    p_push=0.0,
                    outcome=3.0,
                    outcome_available_at="2023-01-01T05:00Z",
                    action_status="action",
                    participation_verified=True,
                    positive_offensive_participation=True,
                )
            ]
        )

    def test_fixed_stake_policy_end_to_end_synthetic_fixture(self):
        from stage1b.backtest import run_verified_backtest

        bets, s = run_verified_backtest(
            pd.DataFrame([self.quote]),
            self.evidence,
            self.root,
            self.forecast(),
            PROTOCOL,
        )
        self.assertEqual(len(bets), 1)
        self.assertAlmostEqual(s["profit"], 0.91)
        self.assertAlmostEqual(s["ending_bankroll"], 1000.91)

    def test_future_model_rejected_before_any_stake(self):
        from stage1b.backtest import run_verified_backtest

        f = self.forecast()
        f["model_fit_available_at"] = "2023-01-01T00:02Z"
        with self.assertRaisesRegex(ValueError, "Model fitted"):
            run_verified_backtest(
                pd.DataFrame([self.quote]), self.evidence, self.root, f, PROTOCOL
            )


if __name__ == "__main__":
    unittest.main()
