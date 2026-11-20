"""Focused chronological experiment, integrity and real research entrypoint tests."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from research_platform.sunday_script import OUT, ROOT, apply_adjustment, digest, walk


class ScriptTemporalTests(unittest.TestCase):
    def test_zero_adjustment_preserves_negative_yards(self):
        base = pd.Series([-1.5, 0, 10.2])
        np.testing.assert_array_equal(
            apply_adjustment(base, np.ones(3), 0, False), base
        )
        self.assertEqual(apply_adjustment(base, np.ones(3), 0, True).iloc[0], 0)

    def test_future_results_do_not_change_earlier_forecasts(self):
        rows = []
        rng = np.random.default_rng(123)
        for i in range(240):
            t = pd.Timestamp("2020-01-01T18:00:00Z") + pd.Timedelta(days=7 * i)
            margin = int(rng.integers(-21, 22))
            for team, opp, home in [("ARI", "KC", 1), ("KC", "ARI", -1)]:
                rows.append(
                    {
                        "game_id": f"game{i}",
                        "team": team,
                        "opponent": opp,
                        "season": 2020 + i // 52,
                        "week": i % 18 + 1,
                        "kickoff_at": t,
                        "available_at": t + pd.Timedelta(hours=36),
                        "home": home,
                        "margin": margin * home,
                        "attempts": 30 + i % 7,
                        "carries": 25 - i % 5,
                    }
                )
        games = pd.DataFrame(rows)
        p = {"ridge_alpha": 100, "history_games": 8}
        fixtures = games.iloc[:0][
            ["game_id", "team", "opponent", "season", "week", "kickoff_at", "home"]
        ]
        first = walk(games, fixtures, p)
        changed = games.copy()
        changed.loc[changed.game_id.eq("game239"), "margin"] = 1000
        second = walk(changed, fixtures, p)
        pd.testing.assert_frame_equal(first, second)
        self.assertTrue((first.history_available_at < first.prediction_at).all())
        self.assertTrue(
            np.allclose(first[["p_trailing", "p_close", "p_leading"]].sum(axis=1), 1)
        )
        self.assertTrue(first.win_probability.between(0, 1).all())

    def test_week11_outcomes_rejected(self):
        games = pd.DataFrame([{"season": 2026, "week": 11}])
        with self.assertRaisesRegex(ValueError, "Sealed"):
            walk(games, pd.DataFrame(), {})


@unittest.skipUnless(sys.version_info[:2] == (3, 14), "Runtime-pinned research data")
class ScriptArtifactTests(unittest.TestCase):
    def test_artifacts_and_identical_populations(self):
        m = json.loads((OUT / "manifest.json").read_text())
        self.assertEqual(
            m["code_sha256"], digest(ROOT / "research_platform/sunday_script.py")
        )
        for name, value in m["files"].items():
            self.assertEqual(digest(OUT / name), value)
        for name, value in m["inputs"].items():
            self.assertEqual(digest(ROOT / name), value)
        r = json.loads((OUT / "report.json").read_text())
        self.assertFalse(r["activation"])
        self.assertEqual(len(r["player_metrics"]), 9)
        d = pd.read_parquet(OUT / "player_replay.parquet")
        self.assertTrue(d.season.eq(2026).all())
        self.assertTrue(d.week.le(10).all())
        self.assertTrue(d.week.ge(1).all())
        for metric in r["player_metrics"]:
            g = d[d.market.eq(metric["market"])]
            self.assertEqual(metric["baseline"]["n"], metric["adjusted"]["n"])
            self.assertEqual(len(g), metric["baseline"]["n"])
            if metric["selection_weight"] == 0:
                np.testing.assert_array_equal(g.projection, g.adjusted)
        future = pd.read_parquet(OUT / "sunday_experimental.parquet")
        self.assertEqual(len(future), 568)
        self.assertNotIn("2026_11_TEN_DAL", set(future.game_id))
        hub = future[
            future.player.eq("Chuba Hubbard") & future.market.eq("Rushing Attempts")
        ].iloc[0]
        self.assertEqual(hub.baseline, 17.1)
        self.assertEqual(hub.adjusted, 17.1)

    def test_real_entrypoint_game_intelligence_keeps_baseline(self):
        from streamlit.testing.v1 import AppTest

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic-script-test",
                    "SPORTSGAMEODDS_API_KEY": "",
                    "SGO_RESEARCH_STORE": str(Path(tmp) / "cache.sqlite"),
                },
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            app = AppTest.from_file(
                str(ROOT / "odds_value_research.py"), default_timeout=90
            ).run()
            app.text_input(key="research_password").input("synthetic-script-test")
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            app.selectbox[0].select("Game Intelligence").run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(any("NOT ACTIVATED" in e.value for e in app.warning))
            app.selectbox(key="experimental_script_fixture").select(
                "2026_11_BAL_CAR"
            ).run()
            player = app.selectbox(key="experimental_script_player")
            index = player.options.index("Chuba Hubbard · Rushing Attempts")
            player.select_index(index).run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any(
                    "Certified baseline: 17.1. Experimental projection: 17.1."
                    in e.value
                    for e in app.markdown
                )
            )
            get.assert_not_called()
            request.assert_not_called()
