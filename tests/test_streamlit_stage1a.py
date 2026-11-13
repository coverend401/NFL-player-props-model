"""Render the app in temporary storage; never write to the checked-out ledger."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

REPO = Path(__file__).resolve().parents[1]


class StreamlitStage1ATests(unittest.TestCase):
    def run_app(self, slate):
        st.cache_resource.clear()
        st.cache_data.clear()
        td = tempfile.TemporaryDirectory(prefix="nfl-app-test-")
        self.addCleanup(td.cleanup)
        data = Path(td.name) / "data"
        data.mkdir()
        (data / "player_features.parquet").symlink_to(
            REPO / "data/player_features.parquet"
        )
        for path in (REPO / "data").glob("model_*.joblib"):
            (data / path.name).symlink_to(path)
        slate.to_parquet(data / "slate.parquet", index=False)
        env = patch.dict(os.environ, {"NFL_APP_ROOT": td.name})
        env.start()
        self.addCleanup(env.stop)
        previous = Path.cwd()
        os.chdir(td.name)
        self.addCleanup(os.chdir, previous)
        self.addCleanup(st.cache_resource.clear)
        from ledger import SQLiteBackend

        connections = []

        def temporary_backend(*args, **kwargs):
            backend = SQLiteBackend(*args, **kwargs)
            connections.append(backend.con)
            return backend

        db_patch = patch("ledger.SQLiteBackend", side_effect=temporary_backend)
        db_patch.start()
        self.addCleanup(db_patch.stop)
        self.addCleanup(lambda: [connection.close() for connection in connections])
        at = AppTest.from_file(str(REPO / "app.py"), default_timeout=60)
        at.secrets.update({"APP_PASSWORD": "", "SUPABASE_URL": "", "SUPABASE_KEY": ""})
        at.run()
        self.assertFalse(at.exception, [e.message for e in at.exception])
        return at

    @staticmethod
    def slate():
        return pd.DataFrame(
            [
                dict(
                    market="Passing Yards",
                    player="Player",
                    team="A",
                    opponent="B",
                    position="QB",
                    projection=321.0,
                    career_avg=250.0,
                    recent_form=300.0,
                    resid_std=70.0,
                    games_played_prior=20,
                    week=10,
                    season=2026,
                    prediction_at="2026-11-12T20:00:00+00:00",
                )
            ]
        )

    def test_lookup_and_engine_use_identical_slate_prediction(self):
        at = self.run_app(self.slate())
        odds = next(w for w in at.text_input if w.label.startswith("Odds (decimal"))
        odds.input("1.91").run()
        self.assertFalse(at.exception, [e.message for e in at.exception])
        metrics = {m.label: m.value for m in at.metric}
        self.assertEqual(metrics["Model projection - Passing Yards"], "321.0")
        old_ev = float(metrics["EV per £1 staked"].replace("£", "")) * 100
        engine_ev = float(metrics["EV"].replace("%", ""))
        self.assertAlmostEqual(
            old_ev, engine_ev, delta=0.51
        )  # different display rounding

    def test_unresolved_roof_scenarios_are_not_shown_as_betting_probabilities(self):
        slate = self.slate()
        slate["projection_status"] = "roof_scenarios_only"
        slate["roof_scenario_low"] = 300.0
        slate["roof_scenario_high"] = 340.0
        at = self.run_app(slate)
        self.assertTrue(any("Roof unresolved" in w.value for w in at.warning))
        self.assertFalse(any(m.label == "Model probability Over" for m in at.metric))

    def test_empty_slate_renders_without_historical_prediction_fallback(self):
        at = self.run_app(self.slate().iloc[:0])
        self.assertFalse(any(m.label.startswith("Model projection") for m in at.metric))
        self.assertEqual(
            len(
                [
                    t
                    for t in at.tabs
                    if t.label
                    in [
                        "Top Picks",
                        "Today's Slate",
                        "Single Prop Lookup",
                        "Price Board",
                        "Parlay Hunter",
                        "My Bets",
                        "Settings",
                    ]
                ]
            ),
            7,
        )


if __name__ == "__main__":
    unittest.main()
