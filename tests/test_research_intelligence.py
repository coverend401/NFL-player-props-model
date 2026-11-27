"""Synthetic research decisions, public frozen aggregates and mobile UI checks."""

import copy
import os
import unittest
from datetime import timedelta
from unittest.mock import patch

from research_platform.engine import evaluate, player_evidence, retain_snapshots
from research_platform.performance import load as load_performance
from tests.test_market_benchmarks import source
from tests.test_sgo_research import NOW, REL, slate


class IntelligenceEngineTests(unittest.TestCase):
    def decisions(self, s=None, now=NOW):
        return evaluate([s or source()], slate(), REL, now)[0]

    def test_real_quote_formula_and_no_vig_pair(self):
        rows = self.decisions()
        self.assertEqual(len(rows), 28)
        for r in rows:
            self.assertAlmostEqual(
                r["ev_pct"], 100 * (r["model_probability"] * r["decimal_odds"] - 1)
            )
            self.assertAlmostEqual(r["no_vig_probability"], 0.5)
            self.assertAlmostEqual(r["probability_gap"], r["model_probability"] - 0.5)
            self.assertEqual(r["book_count"], 2)
            self.assertEqual(r["recommendation_stake"], 0)
            self.assertNotEqual(r["classification"], "BET")
        self.assertTrue(any(r["classification"] == "WATCH" for r in rows))
        self.assertTrue(any(r["classification"] == "PASS" for r in rows))

    def test_integer_line_cannot_enter_positive_ev_watch(self):
        s = source()
        for o in s["events"][0]["odds"].values():
            for q in o["byBookmaker"].values():
                q["overUnder"] = "20"
        rows = self.decisions(s)
        self.assertTrue(rows)
        self.assertTrue(
            all(
                r["ev_pct"] is None
                and r["model_probability"] is None
                and r["classification"] == "PASS"
                for r in rows
            )
        )

    def test_stale_future_cutoff_scenario_and_unmatched_fail_closed(self):
        for changed, now, forecast in [
            (source(), NOW + timedelta(minutes=16), slate()),
            (source(), NOW - timedelta(seconds=1), slate()),
            (source(), NOW + timedelta(hours=3, seconds=1), slate()),
            (source(), NOW, slate().assign(projection_status="roof_scenario_only")),
            (source(), NOW, slate().assign(player_id="other", player="Other Person")),
        ]:
            self.assertEqual(evaluate([changed], forecast, REL, now)[0], [])

    def test_newest_pair_per_book_prevents_duplicate_or_mixed_lines(self):
        first = source(("fanduel",))
        second = copy.deepcopy(first)
        second["retrieved_at"] = (NOW + timedelta(seconds=10)).isoformat()
        for o in second["events"][0]["odds"].values():
            o["byBookmaker"]["fanduel"]["overUnder"] = "24.5"
        rows, _ = evaluate([first, second], slate(), REL, NOW + timedelta(seconds=11))
        self.assertEqual(len(rows), 14)
        self.assertTrue(
            all(
                r["line"] == 24.5 and r["book_count"] == 1 and r["median_line"] == 24.5
                for r in rows
            )
        )

    def test_separate_fresh_books_combine_without_inventing_quotes(self):
        a = source(("fanduel",))
        b = source(("draftkings",))
        for o in b["events"][0]["odds"].values():
            o["byBookmaker"]["draftkings"]["overUnder"] = "22.5"
        rows, _ = evaluate([a, b], slate(), REL, NOW)
        self.assertEqual(len(rows), 28)
        self.assertTrue(
            all(r["median_line"] == 21.5 and r["book_count"] == 2 for r in rows)
        )
        self.assertTrue(all(r["line"] in [20.5, 22.5] for r in rows))

    def test_residual_sensitivity_is_not_a_confidence_score(self):
        for r in self.decisions():
            self.assertLessEqual(r["stress_ev_min"], r["ev_pct"])
            self.assertGreaterEqual(r["stress_ev_max"], r["ev_pct"])
            self.assertNotIn("confidence_score", r)

    def test_private_snapshot_retention_and_original_timestamps(self):
        s = source()
        s["request_scope"]["startsAfter"] = "window1"
        snapshots = retain_snapshots([], s, NOW)
        self.assertEqual(retain_snapshots(snapshots, s, NOW), [s])
        self.assertEqual(
            retain_snapshots(snapshots, s, NOW + timedelta(minutes=16)), []
        )
        self.assertEqual(retain_snapshots([], s, NOW - timedelta(seconds=1)), [])
        for i in range(8):
            s = copy.deepcopy(s)
            s["request_scope"]["startsAfter"] = str(i)
            snapshots = retain_snapshots(snapshots, s, NOW)
        self.assertEqual(len(snapshots), 6)
        self.assertEqual(snapshots[-1]["retrieved_at"], NOW.isoformat())

    def test_missing_context_is_not_invented_usage(self):
        result = player_evidence(None, "synthetic", "synthetic")
        self.assertEqual(result["facts"], [])
        self.assertTrue(result["missing"])

    def test_no_outcome_no_live_ledger_and_no_additional_markets(self):
        rows = self.decisions()
        self.assertTrue(
            all(r["policy_id"] == "stage1a-research-watch-only-v1" for r in rows)
        )
        self.assertTrue(
            all(
                r["market"] not in ["Passing Touchdowns", "Anytime Touchdown"]
                for r in rows
            )
        )


class IntelligencePerformanceTests(unittest.TestCase):
    def test_only_pinned_development_aggregate_results_loaded(self):
        data = load_performance()
        self.assertTrue(data["manifest"]["final_period_sealed"])
        for name in ["accuracy.csv", "probability_metrics.csv", "reliability.csv"]:
            self.assertEqual(set(data[name].evaluation_tier), {"development_oos"})
        self.assertEqual(data["accuracy.csv"].market.nunique(), 9)


class IntelligenceUITests(unittest.TestCase):
    def test_all_sections_render_without_network_or_odds(self):
        from streamlit.testing.v1 import AppTest

        with (
            patch("requests.get") as get,
            patch("requests.request") as request,
            patch.dict(os.environ, {"SPORTSGAMEODDS_API_KEY": ""}),
            patch("sgo_research.ui.st.secrets", {}),
        ):
            app = AppTest.from_string(
                "from tests.test_sgo_research import slate, REL\nfrom research_platform.ui import render\nrender(slate(), REL)"
            ).run(timeout=30)
            self.assertFalse(app.exception, app.exception)
            for section in [
                "Player Intelligence",
                "Game Intelligence",
                "Market Intelligence",
                "Model Performance",
                "Data & Safety",
                "Top Picks",
            ]:
                app.selectbox[0].select(section).run(timeout=30)
                self.assertFalse(app.exception, app.exception)
            get.assert_not_called()
            request.assert_not_called()

    def test_integrated_real_quote_path_to_visible_watch_cards(self):
        from streamlit.testing.v1 import AppTest

        with (
            patch("research_platform.ui.datetime") as clock,
            patch("sgo_research.market_ui.datetime") as collection_clock,
            patch("requests.get") as get,
            patch("requests.request") as request,
            patch.dict(
                os.environ, {"SPORTSGAMEODDS_API_KEY": "synthetic_api_key_only"}
            ),
        ):
            clock.now.return_value = NOW
            collection_clock.now.return_value = NOW
            app = AppTest.from_string(
                'import streamlit as st\nfrom tests.test_sgo_research import slate, REL\nfrom tests.test_market_benchmarks import source\nfrom research_platform.ui import render\nst.session_state["market_snapshot"]=source()\nrender(slate(), REL)'
            ).run(timeout=30)
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any(
                    "VALIDATED BETS" in x.value and "<b>0</b>" in x.value
                    for x in app.markdown
                )
            )
            self.assertTrue(
                any(
                    "EXPERIMENTAL" in x.value and "Synthetic Player" in x.value
                    for x in app.markdown
                )
            )
            get.assert_not_called()
            request.assert_not_called()

    def test_provider_text_is_html_escaped(self):
        from research_platform.ui import esc

        self.assertEqual(esc("<script>x</script>"), "&lt;script&gt;x&lt;/script&gt;")
