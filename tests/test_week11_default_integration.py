"""Current-slate integration only; synthetic quotes never call any provider."""

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

from sgo_research.analysis import comparisons
from tests.test_market_benchmarks import source

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Research bundle is runtime-pinned"
)
class Week11DefaultTests(unittest.TestCase):
    def test_counts_scenarios_and_synthetic_pricing_exclusion(self):
        pointer = json.loads((ROOT / "research_active_inference.json").read_text())
        directory = ROOT / pointer["path"]
        m = json.loads((directory / "manifest.json").read_text())
        slate = pd.read_parquet(directory / "slate.parquet")
        picks = pd.read_parquet(directory / "top_picks.parquet")
        self.assertEqual(len(slate), 618)
        self.assertEqual(int(slate.projection_status.eq("complete").sum()), 568)
        scenarios = slate[slate.projection_status.eq("roof_scenarios_only")]
        self.assertEqual(len(scenarios), 50)
        self.assertEqual(set(scenarios.game_id), {"2026_11_TEN_DAL"})
        self.assertEqual(len(picks), 22)
        self.assertNotIn("2026_11_TEN_DAL", set(picks.game_id))
        self.assertTrue(slate.week.eq(11).all())
        row = scenarios[scenarios.market.eq("Receiving Yards")].iloc[0]
        now = (
            pd.Timestamp(m["prediction_at"]) + pd.Timedelta(minutes=5)
        ).to_pydatetime()
        snap = source(("fanduel",))
        snap["retrieved_at"] = now.isoformat()
        event = snap["events"][0]
        event["status"]["startsAt"] = m["game_kickoffs"][row.game_id]
        event["teams"] = {
            "home": {"teamID": "DAL_NFL", "names": {"short": "DAL"}},
            "away": {"teamID": "TEN_NFL", "names": {"short": "TEN"}},
        }
        event["players"]["SYNTH_PLAYER_1_NFL"] = {
            "name": row.player,
            "teamID": row.team + "_NFL",
        }
        for odd in event["odds"].values():
            odd["byBookmaker"]["fanduel"]["lastUpdatedAt"] = now.isoformat()
        rows, _ = comparisons(snap, slate, m, now)
        self.assertTrue(
            any("forecast_scenario_only" in r["comparison_status"] for r in rows)
        )
        self.assertFalse(any(r["eligible"] for r in rows))
        self.assertFalse(any(r["ev_pct"] is not None for r in rows))

    def test_safety_text_uses_current_cutoff_and_explicit_inference_contract(self):
        from unittest.mock import patch

        from research_platform.ui import operations_view

        pointer = json.loads((ROOT / "research_active_inference.json").read_text())
        m = json.loads((ROOT / pointer["path"] / "manifest.json").read_text())
        with patch("research_platform.ui.st") as ui:
            operations_view(m)
        text = " ".join(str(call.args[0]) for call in ui.write.call_args_list)
        self.assertIn("Sun 22 Nov 17:00", text)
        self.assertNotIn("Munich", text)
        self.assertTrue(
            any(
                "not a new training release" in call.args[0]
                for call in ui.caption.call_args_list
            )
        )
