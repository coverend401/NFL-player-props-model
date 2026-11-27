"""Historical visibility must never admit historical forecasts to manual pricing."""

import unittest
from unittest.mock import patch

import pandas as pd

from research_platform import enhanced_engine as engine
from research_platform import enhanced_ui as ui


class FrozenSlateVisibilityTests(unittest.TestCase):
    def test_all_ten_games_remain_visible_after_early_kickoffs(self):
        frame = pd.read_parquet(engine.DIRECTORY / "forecasts.parquet")
        fixtures = pd.read_csv(engine.DIRECTORY / "fixtures.csv")
        release = {"release_id": "research-week11-frozen-20261120-r2"}
        with (
            patch.object(ui, "loaded", return_value=(frame, None, None, fixtures, {})),
            patch.object(ui, "datetime") as clock,
        ):
            clock.now.return_value = pd.Timestamp("2026-11-22T18:01Z")
            all_rows, top, two, _, _ = ui.current(release, include_historical=True)
            live, _, _, _, _ = ui.current(release)
        self.assertEqual(
            (len(all_rows), len(top), len(two), two.game_id.nunique()),
            (522, 12, 20, 10),
        )
        self.assertEqual((len(live), live.game_id.nunique()), (211, 4))
        self.assertFalse(live.game_id.eq("2026_11_ARI_KC").any())
        self.assertFalse(two.game_id.eq("2026_11_TEN_DAL").any())

    def test_cutoff_and_historical_labels_are_distinct(self):
        kickoff = "2026-11-22T18:00Z"
        self.assertIn("Before T−60", ui.fixture_status(kickoff, "2026-11-22T16:59Z"))
        self.assertIn("CUTOFF CLOSED", ui.fixture_status(kickoff, "2026-11-22T17:00Z"))
        self.assertIn(
            "HISTORICAL PRE-KICKOFF", ui.fixture_status(kickoff, "2026-11-22T18:00Z")
        )
