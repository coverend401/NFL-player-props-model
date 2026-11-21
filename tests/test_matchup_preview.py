"""Descriptive, sealed-period-safe research only. No models fitted."""

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from matchup_research.build import contact_rates, qb_response, safe_rate
from matchup_research.ui import DEFAULT, load


class MatchupTests(unittest.TestCase):
    def test_player_specific_response_differs_without_adjustment(self):
        high = qb_response({"dropbacks": 100, "scramble_rate": 0.12})
        low = qb_response({"dropbacks": 100, "scramble_rate": 0.01})
        self.assertNotEqual(high["direction"], low["direction"])
        self.assertIn("rushing", high["direction"])
        self.assertIn("short-target", low["direction"])
        self.assertIn("If pressure", low["assumption"])

    def test_missing_history_not_zero_or_ability_claim(self):
        self.assertEqual(
            qb_response({"dropbacks": 0, "scramble_rate": None})["direction"], "unknown"
        )
        self.assertEqual(
            qb_response({"dropbacks": 10, "scramble_rate": 0.2})["direction"], "unknown"
        )
        self.assertIsNone(safe_rate(0, 0))

    def test_contact_is_union_not_double_count(self):
        d = pd.DataFrame(
            {
                "qb_dropback": [1, 1, 1],
                "qb_hit": [1, 1, None],
                "sack": [1, 0, None],
                "air_yards": [0, 10, None],
                "qb_scramble": [0, 1, 0],
            }
        )
        r = contact_rates(d)
        self.assertEqual(r["contact_label_n"], 2)
        self.assertEqual(r["hit_or_sack_rate"], 1)
        self.assertEqual(r["scramble_n"], 1)
        self.assertAlmostEqual(r["scramble_rate"], 1 / 3)

    def test_real_snapshot_is_frozen_before_decisions_and_release_unchanged(self):
        root = Path(__file__).resolve().parents[1]
        release = json.loads((root / "active_release.json").read_text())
        state = load(DEFAULT, release)
        self.assertEqual(len(state["fixtures"]), 12)
        self.assertFalse(state["prediction_adjustments_enabled"])
        self.assertFalse(state["sealed_outcomes_accessed"])
        for fixture in state["fixtures"]:
            self.assertLess(
                datetime.fromisoformat(state["generated_at"]),
                datetime.fromisoformat(fixture["decision_at"]),
            )
            self.assertIn("_10_", fixture["game_id"])
            for a in fixture["assessments"]:
                self.assertTrue(a["missing"])
                for gid in a["history_game_ids"] + a["defense_history_game_ids"]:
                    self.assertLess(int(gid.split("_")[1]), 11)
                for q in a["quarterbacks"]:
                    self.assertTrue(q["interpretation"]["assumption"])
                    self.assertIn("baseline_projections", q)

    def test_tampered_or_mismatched_snapshot_rejected(self):
        state = json.loads(DEFAULT.read_text())
        with self.assertRaises(ValueError):
            load(DEFAULT, {"release_id": "wrong"})
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "s.json"
            p.write_text(json.dumps(state))
            p.with_suffix(".sha256").write_text("wrong")
            with self.assertRaises(ValueError):
                load(p, {"release_id": state["release_id"]})

    def test_research_auth_blocks_before_forecasts(self):
        from streamlit.testing.v1 import AppTest

        with (
            patch.dict(os.environ, {"RESEARCH_PREVIEW_PASSWORD": ""}),
            patch("requests.get") as get,
        ):
            app = AppTest.from_string(
                'from research_access import require_access\nimport streamlit as st\nrequire_access()\nst.write("sensitive research")'
            ).run()
            self.assertTrue(any("locked" in x.value for x in app.warning))
            self.assertFalse(app.exception)
            self.assertFalse(any("sensitive research" in x.value for x in app.markdown))
            get.assert_not_called()

    def test_research_wrong_password_stays_locked(self):
        from streamlit.testing.v1 import AppTest

        with patch.dict(
            os.environ, {"RESEARCH_PREVIEW_PASSWORD": "synthetic_auth_only"}
        ):
            app = AppTest.from_string(
                'from research_access import require_access\nimport streamlit as st\nrequire_access()\nst.write("sensitive research")'
            ).run()
            app.text_input[0].input("wrong")
            app.button[0].click().run()
            self.assertTrue(app.error)
            self.assertFalse(any("sensitive research" in x.value for x in app.markdown))

    def test_password_rotation_locks_old_session(self):
        from streamlit.testing.v1 import AppTest

        with patch.dict(
            os.environ, {"RESEARCH_PREVIEW_PASSWORD": "synthetic_auth_only"}
        ):
            app = AppTest.from_string(
                'from research_access import require_access\nimport streamlit as st\nrequire_access()\nst.write("sensitive research")'
            ).run()
            app.text_input[0].input("synthetic_auth_only")
            app.button[0].click().run()
            self.assertTrue(any("sensitive research" in x.value for x in app.markdown))
        with patch.dict(
            os.environ, {"RESEARCH_PREVIEW_PASSWORD": "rotated_synthetic_only"}
        ):
            app.run()
            self.assertTrue(app.text_input)
            self.assertFalse(any("sensitive research" in x.value for x in app.markdown))

    def test_game_script_mobile_cards_no_network(self):
        from streamlit.testing.v1 import AppTest

        with patch("requests.get") as get:
            app = AppTest.from_string(
                'import json\nfrom pathlib import Path\nfrom matchup_research.ui import render\nrender(json.loads(Path("active_release.json").read_text()))'
            ).run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(app.selectbox)
            self.assertTrue(any("Drake Maye" in v.value for v in app.markdown))
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
