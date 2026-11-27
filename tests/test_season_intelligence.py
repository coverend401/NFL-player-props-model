"""No network, no sealed outcomes, no original models fitted by these tests."""

import itertools
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from season_intelligence.data import STATS, history_features
from season_intelligence.probability import HurdleEmpirical, quoted_value


def observations():
    rows = []
    for i, value in enumerate([10.0, 0.0, 20.0, 40.0]):
        r = {c: value for c in STATS}
        r.update(
            player_id="p",
            game_id=str(i),
            team="CAR",
            opponent_team="ATL",
            position="RB",
            season=2025,
            week=i + 1,
            kickoff_at=pd.Timestamp("2025-09-01T18:00Z") + pd.Timedelta(weeks=i),
            completed_at=pd.Timestamp("2025-09-02T02:00Z") + pd.Timedelta(weeks=i),
            offense_pct=0.5,
            stats_observed=True,
            team_total_attempts=35.0,
            team_total_carries=30.0,
            team_total_targets=33.0,
        )
        rows.append(r)
    return pd.DataFrame(rows)


class HistoryTests(unittest.TestCase):
    def test_true_zero_and_manual_last_three(self):
        d = history_features(observations())
        self.assertEqual(d.iloc[3].carries_last3, 10.0)
        self.assertEqual(d.iloc[3].history_n, 3)
        self.assertAlmostEqual(d.iloc[3].carries_share3, 1 / 3)
        self.assertLess(d.iloc[3].history_available_at, d.iloc[3].prediction_at)

    def test_same_game_and_future_outcomes_cannot_change_features(self):
        s = observations()
        a = history_features(s)
        s.loc[2:, "carries"] = 99999
        b = history_features(s)
        cols = ["carries_last3", "carries_last5", "carries_share3", "offense_pct_last3"]
        pd.testing.assert_frame_equal(a.loc[:2, cols], b.loc[:2, cols])

    def test_missing_box_is_not_zero_and_invalidates_recent_production(self):
        s = observations()
        s.loc[1, "stats_observed"] = False
        d = history_features(s)
        self.assertTrue(np.isnan(d.iloc[3].carries_last3))
        self.assertEqual(d.iloc[3].history_n, 3)

    def test_season_boundary_and_bye_preserve_history(self):
        s = observations()
        s.loc[3, "season"] = 2026
        s.loc[3, "week"] = 1
        s.loc[3, "kickoff_at"] = pd.Timestamp("2026-09-01T18:00Z")
        s.loc[3, "completed_at"] = pd.Timestamp("2026-09-02T02:00Z")
        d = history_features(s)
        self.assertEqual(d.iloc[3].carries_last3, 10)
        self.assertGreater(d.iloc[3].days_rest, 300)
        self.assertTrue(np.isnan(d.iloc[3].carries_season))
        self.assertEqual(d.iloc[3].carries_season_n, 0)
        # A prior-season mean is explicitly paired with its own sample count;
        # no current-season games are invented before the opener.

    def test_stale_history_counts_rebuilt_without_season_reset(self):
        from scripts.build_features import AUX_STAT_COLS, STAT_COLS
        from season_intelligence.data import rebuild_legacy

        s = observations()
        s.loc[3, "season"] = 2026
        s["games_played_prior"] = 0
        s["offense_pct_last3_avg"] = 0
        for col in STAT_COLS + AUX_STAT_COLS:
            if col not in s:
                s[col] = np.nan
        for col in STAT_COLS:
            s["team_total_" + col] = np.nan
        rebuilt = rebuild_legacy(s)
        row = rebuilt[rebuilt.game_id.eq("3")].iloc[0]
        self.assertEqual(row.games_played_prior, 3)
        self.assertEqual(row.carries_last3_avg, 10)
        self.assertEqual(row.offense_pct_last3_avg, 0.5)

    def test_unavailable_history_is_not_used(self):
        s = observations()
        s.loc[0, "completed_at"] = s.loc[1, "kickoff_at"] + pd.Timedelta(days=1)
        d = history_features(s)
        self.assertTrue(pd.isna(d.iloc[1].history_available_at))
        self.assertTrue(np.isnan(d.iloc[1].carries_last3))


class ProbabilityTests(unittest.TestCase):
    def law(self):
        y = np.tile(np.array([0, 0, 1, 2, 3, 4, 5, 9]), 40)
        return HurdleEmpirical().fit(np.full(len(y), 3.0), y, np.repeat("RB", len(y)))

    def test_integer_pushes_and_refund_fair_odds(self):
        p = self.law().price(3, "RB", True, 3)
        self.assertAlmostEqual(p["over"] + p["under"] + p["push"], 1)
        self.assertGreater(p["push"], 0)
        self.assertAlmostEqual(
            quoted_value(p, p["fair_over"])["expected_profit_per_unit"], 0
        )
        self.assertAlmostEqual(
            quoted_value(p, 2.0)["expected_profit_per_unit"],
            2 * p["over"] - (1 - p["push"]),
        )

    def test_half_line_has_no_push_and_monotone_probabilities(self):
        ps = [self.law().price(3, "RB", True, line) for line in [0.5, 2.5, 4.5]]
        self.assertTrue(all(p["push"] == 0 for p in ps))
        self.assertTrue(all(a["over"] >= b["over"] for a, b in itertools.pairwise(ps)))

    def test_count_support_and_true_zero_atom(self):
        values, weights = self.law().samples(3, "RB", True)
        self.assertTrue((values >= 0).all())
        self.assertTrue(np.equal(values, np.floor(values)).all())
        self.assertGreater(weights[values == 0].sum(), 0)
        self.assertAlmostEqual(weights.sum(), 1)

    def test_negative_yardage_supported_not_negative_counts(self):
        y = np.tile([-10, 0, 0, 5, 20, 40], 30)
        law = HurdleEmpirical().fit(np.full(len(y), 8), y, np.repeat("QB", len(y)))
        v, _ = law.samples(8, "QB", False)
        self.assertTrue((v < 0).any())
        self.assertGreater(law.price(8, "QB", False, 0)["push"], 0)

    def test_bad_prices_or_settlement_rules_rejected(self):
        for price in [0, 1, np.nan]:
            with self.assertRaises(ValueError):
                quoted_value({"over": 0.5, "under": 0.5, "push": 0}, price)
        with self.assertRaises(ValueError):
            quoted_value({"over": 0.5, "under": 0.5, "push": 0}, 2, push_rule="loss")
        with self.assertRaises(ValueError):
            self.law().price(3, "RB", True, np.nan)


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Frozen research artifacts require Python3.14"
)
class FrozenIntelligenceTests(unittest.TestCase):
    def test_actual_artifact_replay_and_seal(self):
        from season_intelligence.experiment import DEFAULT
        from season_intelligence.validate import validate

        result = validate(DEFAULT, replay=True)
        self.assertEqual(result["sunday_rows"], 522)
        self.assertEqual(result["fixtures"], 10)
        self.assertFalse(result["promoted"])
        frame = pd.read_parquet(DEFAULT / "historical_predictions.parquet")
        self.assertEqual(frame.market.nunique(), 9)
        self.assertEqual(frame[frame.season.eq(2026)].week.max(), 10)
        self.assertEqual(len(frame), 55782)
        forecasts = pd.read_parquet(DEFAULT / "sunday_forecasts.parquet")
        self.assertFalse(forecasts.game_id.eq("2026_11_TEN_DAL").any())
        self.assertTrue(forecasts.candidate_delta.ne(0).any())
        self.assertFalse(forecasts.prices_verified.any())

    def test_real_entrypoint_and_supplied_quote_have_no_http_or_default_fake_odds(self):
        from streamlit.testing.v1 import AppTest

        from tests.archived_week11 import archived_week11
        from weekly_learning.store import ROOT

        with (
            archived_week11(),
            patch("season_intelligence.ui.pd", wraps=pd) as archive_pd,
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic-intelligence-only",
                    "SPORTSGAMEODDS_API_KEY": "",
                    "SGO_GITHUB_QUOTA_TOKEN": "",
                    "SGO_QUOTA_REPOSITORY": "",
                    "SGO_RESEARCH_STORE": str(Path(tmp) / "empty.sqlite"),
                },
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            archive_pd.Timestamp = Mock(wraps=pd.Timestamp)
            archive_pd.Timestamp.now.return_value = pd.Timestamp("2026-11-22T08:00Z")
            app = AppTest.from_file(
                str(ROOT / "odds_value_research.py"), default_timeout=120
            ).run()
            app.text_input(key="research_password").input("synthetic-intelligence-only")
            app.button[0].click().run()
            app.selectbox[0].select("Game Intelligence").run()
            self.assertFalse(app.exception, app.exception)
            self.assertIsNone(app.number_input(key="season_intel_odds").value)
            self.assertTrue(
                any(x.label == "Sunday intelligence fixture" for x in app.selectbox)
            )
            app.number_input(key="season_intel_line").set_value(30.0)
            app.number_input(key="season_intel_odds").set_value(2.0)
            app.run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any("Confirm settlement rules" in x.value for x in app.info)
            )
            app.checkbox(key="season_intel_refund").check().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any(
                    "experimental expected profit per unit" in x.value
                    for x in app.markdown
                )
            )
            get.assert_not_called()
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
