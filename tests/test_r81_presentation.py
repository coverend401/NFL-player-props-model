"""Read-only football wording: numbers from evidence, no invented edge or trend."""

import copy
import sys
import unittest
from unittest.mock import patch

from release_utils import resolve_release as resolve_training_release
from research_platform.cards81 import explanation, model_card
from research_platform.slate import model_candidates
from tests.test_sgo_research import GID, NOW, REL, slate


class FootballCopyTests(unittest.TestCase):
    def row(self):
        return next(
            r
            for r in model_candidates(slate(), REL, NOW)
            if r["market"] == "Receptions"
        )

    def state(self, row):
        return {
            "fixtures": [
                {
                    "game_id": GID,
                    "effective_history_cutoff": NOW.isoformat(),
                    "assessments": [
                        {
                            "offense": "CIN",
                            "opponent_defense": "PIT",
                            "offensive_volume": {
                                "games": 4,
                                "plays_per_game": 62,
                                "dropbacks_per_game": 35,
                            },
                            "opponent_contact_proxy": {
                                "hit_or_sack_rate": 0.2,
                                "contact_label_n": 100,
                            },
                            "quarterbacks": [],
                            "receivers": [
                                {
                                    "player_id": row["player_id"],
                                    "observed_targets": 24,
                                    "observed_games": 4,
                                    "at_or_behind_LOS_targets": 3,
                                    "known_target_air_yards_n": 20,
                                    "direction": "Unquantified short-target hypothesis",
                                }
                            ],
                            "missing": [],
                        }
                    ],
                }
            ]
        }

    def test_supported_numbers_three_sentences_no_trend_or_jargon(self):
        row = self.row()
        state = self.state(row)
        before = copy.deepcopy((row, state))
        text = explanation(row, state)
        self.assertIn("24 targets", text)
        self.assertIn("4 recorded games", text)
        self.assertIn("20.0%", text)
        self.assertIn("100 recorded dropbacks", text)
        self.assertIn("without a verified bookmaker line", text)
        for term in [
            "proxy",
            "residual",
            "calibration",
            "distribution",
            "baseline",
            "feature",
            "model signal",
            "increasing",
            "favourable",
            "injured",
        ]:
            self.assertNotIn(term, text.lower())
        self.assertEqual((row, state), before)
        self.assertLess(len(text.split()), 105)

    def test_recorded_qb_workload_is_used_when_available(self):
        row = {**self.row(), "market": "Passing Yards"}
        state = self.state(row)
        a = state["fixtures"][0]["assessments"][0]
        a["receivers"] = []
        a["quarterbacks"] = [
            {
                "player_id": row["player_id"],
                "historical_games": 4,
                "statistics": {"dropbacks": 140},
            }
        ]
        text = explanation(row, state)
        self.assertIn("140 dropbacks across 4 recorded games", text)
        self.assertNotIn("workload details aren't available", text)

    def test_missing_information_not_filled_with_zero_or_role_claim(self):
        text = explanation(self.row(), None)
        self.assertIn("aren't available", text)
        self.assertNotIn("0 targets", text)
        self.assertNotIn("starter", text)
        self.assertNotIn("positive", text)

    def test_rushing_does_not_repurpose_receiving_targets_as_carries(self):
        row = self.row()
        state = self.state(row)
        row = {**row, "market": "Rushing Attempts"}
        text = explanation(row, state)
        self.assertIn("carry totals", text)
        self.assertNotIn("24 carries", text)
        self.assertIn("run defence", text)

    def test_price_comparison_preserves_pass_and_opposed_direction(self):
        row = {
            **self.row(),
            "bookmaker": "fanduel",
            "side": "Under",
            "line": 10.5,
            "projection": 12.5,
            "classification": "PASS",
        }
        text = explanation(row, None)
        self.assertIn("2.0 above", text)
        self.assertIn("Under runs against", text)
        self.assertIn("PASS means no bet recommendation", text)

    def test_model_technical_terms_only_in_expandable_detail(self):
        row = self.row()
        state = self.state(row)
        with patch("research_platform.cards81.st") as ui:
            model_card(row, REL, state)
        card = ui.markdown.call_args_list[0].args[0]
        self.assertIn("Why this pick?", card)
        self.assertIn("MODEL-ONLY", card)
        self.assertNotIn("Residual", card)
        self.assertTrue(
            ui.expander.call_args.args[0].startswith("Detailed model analysis")
        )
        self.assertTrue(
            any("Residual scale" in c.args[0] for c in ui.caption.call_args_list)
        )


class SlateDateTests(unittest.TestCase):
    def test_last_sunday_is_not_relabelled_current(self):
        from datetime import UTC, datetime

        from research_platform.slate_notice import stale_sunday_notice

        release = {**REL, "game_kickoffs": {GID: "2026-11-15T18:00:00Z"}}
        frame = slate().assign(week=10)
        message = stale_sunday_notice(
            frame, release, datetime(2026, 11, 20, tzinfo=UTC)
        )
        self.assertIn("week 10", message)
        self.assertIn("22 November 2026", message)
        self.assertEqual(release["game_kickoffs"][GID], "2026-11-15T18:00:00Z")

    def test_current_sunday_forecast_has_no_stale_warning(self):
        from datetime import UTC, datetime

        from research_platform.slate_notice import stale_sunday_notice

        release = {**REL, "game_kickoffs": {GID: "2026-11-22T18:00:00Z"}}
        self.assertIsNone(
            stale_sunday_notice(slate(), release, datetime(2026, 11, 20, tzinfo=UTC))
        )

    @unittest.skipUnless(
        sys.version_info[:2] == (3, 14), "Approved release requires Python 3.14"
    )
    def test_real_entrypoint_discloses_stale_slate_without_requests(self):
        import os
        from datetime import UTC, datetime
        from pathlib import Path

        from streamlit.testing.v1 import AppTest

        with (
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic_phase1_only",
                    "SPORTSGAMEODDS_API_KEY": "",
                },
            ),
            patch("research_platform.r8.datetime") as clock,
            patch(
                "research_platform.inference_release.resolve_research_release",
                side_effect=resolve_training_release,
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
            app = AppTest.from_file(
                str(Path(__file__).resolve().parents[1] / "odds_value_research.py"),
                default_timeout=60,
            ).run()
            app.text_input(key="research_password").input("synthetic_phase1_only")
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(any("22 November 2026" in e.value for e in app.warning))
            self.assertFalse(any("<article" in e.value for e in app.markdown))
            get.assert_not_called()
            request.assert_not_called()

    @unittest.skipUnless(
        sys.version_info[:2] == (3, 14), "Approved release requires Python 3.14"
    )
    def test_real_entrypoint_cards_using_frozen_release_at_eligible_test_time(self):
        import os
        from datetime import UTC, datetime
        from pathlib import Path

        from streamlit.testing.v1 import AppTest

        with (
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic_wording_test",
                    "SPORTSGAMEODDS_API_KEY": "",
                },
            ),
            patch("research_platform.r8.datetime") as clock,
            patch("research_platform.r8.cached_snapshots", return_value=[]),
            patch(
                "research_platform.inference_release.resolve_research_release",
                side_effect=resolve_training_release,
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            # Historical rendering check only; this does not load a current-week slate.
            clock.now.return_value = datetime(2026, 11, 15, 8, tzinfo=UTC)
            app = AppTest.from_file(
                str(Path(__file__).resolve().parents[1] / "odds_value_research.py"),
                default_timeout=60,
            ).run()
            app.text_input(key="research_password").input("synthetic_wording_test")
            app.button[0].click().run()
            for section, expected in [("Top Picks", 9), ("Top 2 by Game", 18)]:
                next(w for w in app.selectbox if w.label == "Workspace").select(
                    section
                ).run()
                self.assertFalse(app.exception, app.exception)
                cards = [
                    e.value
                    for e in app.markdown
                    if '<article class="desk-card' in e.value
                ]
                self.assertEqual(len(cards), expected)
                for text in cards:
                    self.assertIn("Why this pick?", text)
                    self.assertIn("NO VERIFIED BOOKMAKER VALUE", text)
                    for term in [
                        "proxy",
                        "residual",
                        "calibration",
                        "baseline deviation",
                        "distribution",
                        "model signal",
                    ]:
                        self.assertNotIn(term, text.lower())
                self.assertEqual(
                    sum(
                        e.label.startswith("Detailed model analysis")
                        for e in app.expander
                    ),
                    expected,
                )
            get.assert_not_called()
            request.assert_not_called()
