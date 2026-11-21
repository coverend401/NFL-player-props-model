"""Primary selection screens consume admitted research points, not old rankings."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from research_platform import enhanced_engine as engine


class SelectionMathTests(unittest.TestCase):
    def test_ranking_is_not_projected_yardage_or_delta(self):
        a = {
            "game_id": "g",
            "player_id": "low",
            "player": "A",
            "market": "receiving_yards",
            "enhanced_projection": 20.0,
            "history_n": 8,
            "recent_snap_share": 0.8,
            "recent_opportunities": 5.0,
            "support_tier": 2,
            "calibration_gap": 0.01,
            "role_variability": 0.1,
            "relative_width": 2.0,
        }
        b = {
            **a,
            "player": "B",
            "player_id": "high",
            "enhanced_projection": 100.0,
            "role_variability": 0.9,
        }
        top, two = engine.select(pd.DataFrame([b, a]))
        self.assertEqual(top.iloc[0].player_id, "low")
        self.assertEqual(len(two), 2)

    def test_missing_workload_is_not_zero_and_no_second_player_forced(self):
        a = {
            "game_id": "g",
            "player_id": "one",
            "player": "A",
            "market": "receptions",
            "enhanced_projection": 3.0,
            "history_n": 5,
            "recent_snap_share": 0.6,
            "recent_opportunities": 4.0,
            "support_tier": 2,
            "calibration_gap": 0.02,
            "role_variability": 0.2,
            "relative_width": 3.0,
        }
        b = {**a, "player_id": "missing", "recent_opportunities": np.nan}
        _, two = engine.select(pd.DataFrame([a, b]))
        self.assertEqual(len(two), 1)

    def test_timestamp_cutoff_and_no_backdated_selection(self):
        f = pd.DataFrame(
            [
                {
                    "kickoff_at": "2026-11-22T18:00Z",
                    "selection_built_at": "2026-11-21T21:00Z",
                }
            ]
        )
        self.assertEqual(len(engine.eligible_rows(f, "2026-11-21T22:00Z")), 1)
        self.assertEqual(len(engine.eligible_rows(f, "2026-11-22T17:00Z")), 0)
        self.assertEqual(len(engine.eligible_rows(f, "2026-11-20T22:00Z")), 0)

    def test_baseline_normal_actual_line_and_integer_guard(self):
        r = {"probability_mode": "original_normal", "baseline": 10.0, "resid_std": 2.0}
        p = engine.price(r, 10.5, 2.0)
        from scipy.stats import norm

        self.assertAlmostEqual(p["over"], norm.sf(0.25))
        self.assertAlmostEqual(p["expected_profit_per_unit"], 2 * p["over"] - 1)
        self.assertIn("unavailable", engine.price(r, 10.0, 2.0))
        self.assertIn("unavailable", engine.price(r, -0.5, 2.0))
        self.assertIn(
            "unavailable", engine.price({"probability_mode": "unavailable"}, 10.5, 2.0)
        )

    def test_negative_illustrative_lines_cannot_create_probability_support(self):
        rows = []
        for week in [1, 2]:
            for line in [-0.5, 0.5]:
                for method in ["champion_normal", "research_empirical"]:
                    probability = (
                        (0.999999 if method == "research_empirical" else 0.5)
                        if line < 0
                        else (0.4 if method == "research_empirical" else 0.6)
                    )
                    rows.append(
                        {
                            "market": "receptions",
                            "season": 2026,
                            "week": week,
                            "method": method,
                            "hypothetical_line": line,
                            "p_over": probability,
                            "observed_over": 1.0,
                            "brier": (1 - probability) ** 2,
                            "log_loss": -np.log(probability),
                        }
                    )
        evidence = engine.positive_line_evidence(pd.DataFrame(rows)).iloc[0]
        self.assertEqual(evidence.positive_line_observations, 2)
        self.assertLess(evidence.log_loss_gain, 0)
        self.assertLess(evidence.weekly_log_loss_improvement_low95, 0)

    def test_nonfinite_manual_lines_fail_closed(self):
        r = {"probability_mode": "original_normal", "baseline": 10.0, "resid_std": 2.0}
        for value in [None, float("nan"), float("inf")]:
            with self.assertRaisesRegex(ValueError, "finite numerical"):
                engine.price(r, value, 2.0)

    def test_unknown_variability_does_not_claim_unstable_workload(self):
        r = {
            "market": "rushing_attempts",
            "player": "Player",
            "last3": 10.0,
            "last5": 10.0,
            "recent_opportunities": 10.0,
            "recent_snap_share": 0.5,
            "opponent_carries_allowed": 24.0,
            "team_recent_plays": 60.0,
            "team": "CAR",
            "opponent": "BAL",
            "enhanced_projection": 10.0,
            "baseline": 10.0,
            "point_admitted": False,
            "probability_mode": "original_normal",
            "role_variability": float("nan"),
            "season_mean": 10.0,
        }
        _, risk = engine.explain(r)
        self.assertNotIn("varied substantially", risk)

    def test_explanations_have_real_counts_and_no_injury_or_matchup_invention(self):
        r = {
            "market": "rushing_attempts",
            "player": "Player",
            "last3": 20.0,
            "last5": 15.0,
            "workload5": 15.0,
            "recent_opportunities": 20.0,
            "recent_snap_share": 0.75,
            "opponent_carries_allowed": 24.0,
            "team_recent_plays": 65.0,
            "team": "CAR",
            "opponent": "BAL",
            "enhanced_projection": 18.0,
            "baseline": 17.0,
            "point_admitted": True,
            "probability_mode": "empirical",
            "role_variability": 0.2,
            "season_mean": 16.0,
        }
        text, risk = engine.explain(r)
        for expected in ["20.0", "15.0", "75%", "24.0", "65.0", "18.0", "17.0"]:
            self.assertIn(expected, text)
        for unsupported in [
            "injured",
            "weak against running backs",
            "routes",
            "will lead",
        ]:
            self.assertNotIn(unsupported, text.lower())
        self.assertIn("not established", risk)


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Frozen research models require Python3.14"
)
class FrozenSelectionTests(unittest.TestCase):
    def test_admission_counts_and_unchanged_certified_forecasts(self):
        from weekly_learning.store import sha

        before = sha(engine.CERTIFIED / "slate.parquet")
        frame, top, two, _fixtures, m = engine.load()
        self.assertEqual(len(frame), 522)
        self.assertEqual(len(top), 12)
        self.assertEqual(len(two), 20)
        self.assertEqual(two.game_id.nunique(), 10)
        self.assertTrue((top.projection_change != 0).any())
        self.assertFalse(frame.certified.any())
        expected = pd.read_parquet(engine.EXPERIMENT / "sunday_forecasts.parquet")
        linked = frame.merge(
            expected[["game_id", "player_id", "market", "enhanced_candidate"]],
            on=["game_id", "player_id", "market"],
            suffixes=("", "_frozen"),
            validate="one_to_one",
        )
        admitted = linked.point_admitted
        np.testing.assert_allclose(
            linked.loc[admitted, "enhanced_projection"],
            linked.loc[admitted, "enhanced_candidate_frozen"],
            rtol=0,
            atol=1e-10,
        )
        self.assertFalse(frame[~frame.point_admitted].projection_change.ne(0).any())
        self.assertFalse(two.game_id.eq("2026_11_TEN_DAL").any())
        self.assertEqual(sha(engine.CERTIFIED / "slate.parquet"), before)
        self.assertFalse(m["seal_lifted"])
        self.assertEqual(m["policy"]["week_from_verified_schedule"], 11)

    def test_primary_screens_and_quote_calculator_without_network(self):
        from streamlit.testing.v1 import AppTest

        from tests.archived_week11 import archived_week11
        from weekly_learning.store import ROOT

        m = json.loads((engine.DIRECTORY / "manifest.json").read_text())
        at = pd.Timestamp(m["created_at"]) + pd.Timedelta(seconds=1)
        with (
            archived_week11(),
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic-enhanced-only",
                    "SPORTSGAMEODDS_API_KEY": "",
                    "SGO_GITHUB_QUOTA_TOKEN": "",
                    "SGO_QUOTA_REPOSITORY": "",
                    "SGO_RESEARCH_STORE": str(Path(tmp) / "empty.sqlite"),
                },
            ),
            patch("research_platform.enhanced_ui.datetime") as clock,
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            clock.now.return_value = at.to_pydatetime()
            app = AppTest.from_file(
                str(ROOT / "odds_value_research.py"), default_timeout=120
            ).run()
            app.text_input(key="research_password").input("synthetic-enhanced-only")
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            cards = [
                x.value for x in app.markdown if "enhanced-research-card" in x.value
            ]
            self.assertEqual(len(cards), 12)
            first = pd.read_csv(engine.DIRECTORY / "top_picks.csv").iloc[0]
            self.assertIn(first.player, cards[0])
            self.assertIn(f"{first.enhanced_projection:.1f}", cards[0])
            self.assertIn(f"Original {first.baseline:.1f}", cards[0])
            self.assertTrue(all("Enhanced" not in c or "Original" in c for c in cards))
            self.assertTrue(
                any("Confidence:" in c and "Why this pick?" in c for c in cards)
            )
            self.assertTrue(any("below actual results" in c for c in cards))
            self.assertTrue(
                any("Point-error trade-off" in x.value for x in app.markdown)
            )
            self.assertIsNone(app.number_input(key="enhanced_top_line").value)
            self.assertIsNone(app.number_input(key="enhanced_top_odds").value)
            app.number_input(key="enhanced_top_line").set_value(30.5)
            app.number_input(key="enhanced_top_odds").set_value(2.0)
            app.run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any("Estimated research EV" in x.value for x in app.markdown)
            )
            next(x for x in app.selectbox if x.label == "Workspace").select(
                "Top 2 by Game"
            ).run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(
                sum("enhanced-research-card" in x.value for x in app.markdown), 20
            )
            self.assertTrue(
                any(
                    "not independent" in x.value or "Correlation:" in x.value
                    for x in app.caption
                )
            )
            self.assertTrue(any("roof" in x.value.lower() for x in app.info))
            next(x for x in app.selectbox if x.label == "Workspace").select(
                "Player Intelligence"
            ).run()
            self.assertFalse(app.exception, app.exception)
            self.assertIsNone(app.number_input(key="enhanced_player_line").value)
            get.assert_not_called()
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
