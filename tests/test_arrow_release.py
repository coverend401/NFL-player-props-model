"""Full-cohort regression for the Arrow 24 compatibility rebuild."""

from pathlib import Path
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1] / "release_candidates"
OLD = ROOT / "stage1a-20261113-py314-r3"
NEW = sorted(ROOT.glob("stage1a-20261113-py314-arrow24-r*"))[-1]


class ArrowReleaseRegressionTests(unittest.TestCase):
    def test_every_data_and_forecast_value_is_preserved(self):
        # Only release identity and when the fresh forecast was generated may
        # change. No projection, eligibility, zero or missing value is ignored.
        for name, count in [("weekly_player_data", 139346),
                            ("player_features", 185912),
                            ("slate", 780), ("top_picks", 18)]:
            with self.subTest(table=name):
                old = pd.read_parquet(OLD / "data" / f"{name}.parquet")
                new = pd.read_parquet(NEW / "data" / f"{name}.parquet")
                self.assertEqual(len(new), count)
                self.assertEqual(set(old.columns), set(new.columns))
                ignored = [c for c in ["release_id", "prediction_at", "completed_before"]
                           if c in old.columns]
                pd.testing.assert_frame_equal(
                    old.drop(columns=ignored), new.drop(columns=ignored),
                    check_exact=False, rtol=0, atol=1e-10,
                )

    def test_reference_projections_and_unpriced_scenarios(self):
        slate = pd.read_parquet(NEW / "data/slate.parquet")
        picks = pd.read_parquet(NEW / "data/top_picks.parquet")
        self.assertEqual(slate.projection_status.value_counts().to_dict(),
                         {"complete": 566, "roof_scenarios_only": 214})
        for player, market, expected in [
            ("Aaron Rodgers", "Passing Yards", 237.2),
            ("Ladd McConkey", "Receptions", 3.1),
        ]:
            row = slate[(slate.player == player) & (slate.market == market)]
            self.assertEqual(len(row), 1)
            self.assertAlmostEqual(float(row.iloc[0].projection), expected)
        self.assertTrue(picks.projection_status.eq("complete").all())


if __name__ == "__main__":
    unittest.main()
