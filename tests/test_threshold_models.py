"""New models use past statistics and held-out calibration, never future outcomes."""

import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from performance_research.threshold_benchmark import (
    current_reference_comparison,
    policy_cutoff,
    select_rows,
    split_fold,
    unit_balanced_difference,
    validated_members,
)
from performance_research.threshold_models import (
    NEW,
    ThresholdModels,
    features,
    proposals,
    thresholds,
)


def data(n, seed):
    rng = np.random.default_rng(seed)
    latent = rng.uniform(1, 7, n)
    opp = rng.poisson(latent * 1.5)
    opp[::10] = 0
    y = rng.binomial(opp, 0.6)
    return pd.DataFrame(
        {
            "game_id": [f"g{seed}-{i}" for i in range(n)],
            "player_id": [f"p{i % 30}" for i in range(n)],
            "market": "receptions",
            "position": "WR",
            "lag_anchor": latent,
            "known_scale": 2.0,
            "baseline": latent + 3,
            "champion_sigma": 4.0,
            "receptions_last3": latent + 1,
            "receptions_last5": latent,
            "receptions_career": latent - 1,
            "receptions_sd5": 2.0,
            "targets_last3": latent * 1.5,
            "targets_last5": latent * 1.4,
            "history_n": 10,
            "offense_pct_last3": 0.7,
            "role_snap_change": 0.05,
            "observed_opportunity": opp,
            "y": y,
        }
    )


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(
            (
                Path(__file__).parents[1]
                / "performance_research/threshold_protocol.json"
            ).read_text()
        )
        cls.small = {**cls.policy, "boost_iterations": 10, "forest_trees": 8}
        cls.train = data(360, 1)
        cls.cal = data(180, 2)
        cls.test = data(70, 3)
        cls.cal["prediction_at"] = pd.Timestamp("2024-09-01T17:00Z")
        cls.model = ThresholdModels("receptions", cls.small).fit(cls.train, cls.cal)

    def test_no_future_outcome_opportunity_or_inherited_market_input(self):
        a = proposals(self.test, self.model.offsets)
        changed = self.test.assign(
            y=999.0, observed_opportunity=999.0, baseline=999.0, champion_sigma=999.0
        )
        b = proposals(changed, self.model.offsets)
        np.testing.assert_array_equal(a.research_line, b.research_line)
        before = self.model.predict(a)
        after = self.model.predict(b)
        for method in NEW[:-1]:
            np.testing.assert_allclose(before[method], after[method])
        self.assertFalse(
            set(features(self.train, "receptions"))
            & {"y", "observed_opportunity", "baseline", "champion_sigma"}
        )

    def test_every_predicted_exceedance_curve_is_monotone(self):
        f = pd.concat([self.test.iloc[:1]] * 20, ignore_index=True)
        f["research_line"] = np.arange(20) + 0.5
        result = self.model.predict(f)
        for method, p in result.items():
            with self.subTest(method=method):
                self.assertTrue(np.isfinite(p).all())
                self.assertTrue(((p > 0) & (p < 1)).all())
                self.assertTrue((np.diff(p) <= 1e-10).all())
        q = self.model.interval(self.test)
        self.assertTrue((np.diff(q, axis=1) >= 0).all())

    def test_distribution_forest_retains_genuine_zero_mass(self):
        f = pd.concat([self.test.iloc[:1]] * 2, ignore_index=True)
        f["research_line"] = [-0.5, 0.5]
        raw = self.model.raw_scores(f)["distribution_forest"]
        self.assertAlmostEqual(raw[0], 1.0)
        self.assertLess(raw[1], 1.0)
        self.assertGreaterEqual(raw[1], 0.0)

    def test_thresholds_are_train_only_and_half_integer_research_lines(self):
        offsets = thresholds(self.train)
        f = proposals(self.test, offsets)
        self.assertTrue(np.allclose(f.research_line % 1, 0.5))
        self.assertFalse(
            f.duplicated(["game_id", "player_id", "market", "research_line"]).any()
        )
        np.testing.assert_allclose(thresholds(self.train), offsets)


class FoldSelectionTests(unittest.TestCase):
    def test_temporal_splits_never_use_later_observations(self):
        rows = []
        for year in [2022, 2023, 2024, 2025]:
            for week in range(1, 19):
                for player in range(8):
                    at = pd.Timestamp(f"{year}-08-01T17:00Z") + pd.Timedelta(weeks=week)
                    rows.append(
                        {
                            "season": year,
                            "week": week,
                            "market": "receptions",
                            "prediction_at": at,
                            "available_at": at + pd.Timedelta(hours=10),
                            "lag_anchor": 4.0,
                            "y": 5.0,
                            "receptions_sd5": 2.0,
                        }
                    )
        train, cal, val, test = split_fold(pd.DataFrame(rows), 2025)
        self.assertLess(train.available_at.max(), cal.prediction_at.min())
        self.assertLess(cal.available_at.max(), val.prediction_at.min())
        self.assertLess(val.available_at.max(), test.prediction_at.min())

    def selection_data(self):
        return pd.DataFrame(
            {
                "game_id": ["a", "b", "b"],
                "player_id": ["p1", "p2", "p3"],
                "market": "receptions",
                "season": 2025,
                "week": 1,
                "prediction_at": pd.to_datetime(
                    ["2025-09-04T17:00Z", "2025-09-07T17:00Z", "2025-09-07T17:00Z"]
                ),
                "weekly_decision_at": pd.Timestamp("2025-09-04T17:00Z"),
                "history_available_at": pd.to_datetime(
                    ["2025-09-03T00:00Z", "2025-09-05T00:00Z", "2025-09-03T00:00Z"]
                ),
                "research_line": 4.5,
                "observed_over": [1, 0, 1],
                "direct_classifier": [0.7, 0.99, 0.8],
            }
        )

    def test_selection_cannot_use_later_history_or_actual_results(self):
        f = self.selection_data()
        chosen = select_rows(f, "direct_classifier", "slate")
        self.assertNotIn("p2", set(chosen.player_id))
        other = select_rows(
            f.assign(observed_over=1 - f.observed_over), "direct_classifier", "slate"
        )
        self.assertEqual(list(chosen.player_id), list(other.player_id))
        # Filtering out the early game must not silently move the weekly decision later.
        self.assertNotIn(
            "p2",
            set(
                select_rows(
                    f[f.game_id.eq("b")], "direct_classifier", "slate"
                ).player_id
            ),
        )

    def test_uncertainty_does_not_overweight_extra_thresholds_for_one_player(self):
        frame = pd.DataFrame(
            {
                "game_id": ["a", "b", "b", "b"],
                "player_id": ["p1", "p2", "p2", "p2"],
                "market": "receptions",
                "season": 2025,
                "week": 1,
                "research_line": [1.5, 1.5, 2.5, 3.5],
            }
        )
        balanced = unit_balanced_difference(frame, pd.Series([1.0, 0.0, 0.0, 0.0]))
        self.assertAlmostEqual(float(balanced.mean()), 0.5)

    def test_weak_prior_validation_must_abstain(self):
        policy = json.loads(
            (
                Path(__file__).parents[1]
                / "performance_research/threshold_protocol.json"
            ).read_text()
        )
        self.assertIsNone(
            policy_cutoff(self.selection_data(), "direct_classifier", policy)
        )

    def test_ensemble_uses_only_validated_components(self):
        n = 200
        f = pd.DataFrame(
            {
                "game_id": [str(i) for i in range(n)],
                "player_id": [str(i) for i in range(n)],
                "market": "receptions",
                "observed_over": [1] * 160 + [0] * 40,
                "champion_normal": 0.5,
            }
        )
        for method in NEW[:-1]:
            f[method] = 0.99
        f["direct_classifier"] = 0.8
        members, _ = validated_members(f)
        self.assertEqual(members, ["direct_classifier"])
        f["direct_classifier"] = 0.99
        self.assertEqual(validated_members(f)[0], [])


class SecondaryReferenceTests(unittest.TestCase):
    def test_gaussian_gain_is_not_mislabeled_as_current_research_gain(self):
        frame = pd.DataFrame(
            {
                "season": 2026,
                "week": [1, 2, 3, 4],
                "game_id": ["a", "b", "c", "d"],
                "player_id": "p",
                "market": "receptions",
                "observed_over": 1,
                "research_line": 1.5,
                "champion_normal": 0.5,
                "existing_research": 0.8,
            }
        )
        metrics, selections, weekly = [], [], []
        for method in ["existing_research", *NEW]:
            frame[method] = 0.8
            metrics.append(
                {
                    "season": 2026,
                    "market": "receptions",
                    "method": method,
                    "log_loss": -np.log(0.8),
                }
            )
            for mode in ["slate", "game"]:
                selections.append(
                    {
                        "season": 2026,
                        "method": method,
                        "kind": "fixed_count",
                        "mode": mode,
                        "selections": 4,
                        "hit_rate": 1.0,
                    }
                )
                weekly.extend(
                    {
                        "season": 2026,
                        "week": w,
                        "method": method,
                        "kind": "fixed_count",
                        "mode": mode,
                        "n": 1,
                        "hit_rate": 1.0,
                    }
                    for w in range(1, 5)
                )
        probability, selected = current_reference_comparison(
            frame, metrics, selections, weekly
        )
        self.assertEqual(len(probability), 6)
        self.assertTrue(all(r["macro_log_loss_gain"] == 0 for r in probability))
        self.assertTrue(
            all(r["hit_rate_gain"] == 0 and r["equal_counts"] for r in selected)
        )


class SourceSchemaTests(unittest.TestCase):
    def test_large_string_season_and_week_are_filtered_before_materialisation(self):
        import tempfile

        import pyarrow as pa
        import pyarrow.parquet as pq

        from weekly_learning.forecast import completed_week_filters

        for week_type in [pa.int16(), pa.large_string()]:
            with (
                self.subTest(week_type=week_type),
                tempfile.TemporaryDirectory() as tmp,
            ):
                years = ["2026", "2026", "2026", "2025"]
                weeks = (
                    [1, 11, 12, 11]
                    if pa.types.is_integer(week_type)
                    else ["1", "11", "12", "11"]
                )
                table = pa.table(
                    {
                        "season": pa.array(years, type=pa.large_string()),
                        "week": pa.array(weeks, type=week_type),
                        "value": [1, 11, 999, 2025],
                    }
                )
                path = Path(tmp) / "data.parquet"
                pq.write_table(table, path)
                result = pd.read_parquet(
                    path, filters=completed_week_filters(table.schema, 2026, 12)
                )
                self.assertEqual(result.value.tolist(), [1, 11])
