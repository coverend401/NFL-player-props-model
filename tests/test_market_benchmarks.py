"""Synthetic evidence only; no historic prices or outcomes."""

import unittest
from datetime import timedelta

from sgo_research.market import benchmarks
from tests.test_sgo_research import NOW, REL, slate, snapshot


def source(books=("fanduel", "draftkings")):
    s = snapshot()
    s["request_scope"] = {"includeAltLines": "false"}
    for o in s["events"][0]["odds"].values():
        base = o["byBookmaker"]["williamhill"]
        base.pop("isMainLine")
        o["byBookmaker"] = {
            b: {**base, "overUnder": str(20.5 + 2 * i)} for i, b in enumerate(books)
        }
    return s


class MarketTests(unittest.TestCase):
    def test_median_counts_books_not_sides(self):
        rows, _ = benchmarks(source(), slate(), REL, NOW)
        self.assertEqual(len(rows), 7)
        self.assertTrue(
            all(r["book_count"] == 2 and r["median_line"] == 21.5 for r in rows)
        )
        self.assertTrue(all(r["projection"] == 22 for r in rows))

    def test_single_book(self):
        rows, _ = benchmarks(source(("fanduel",)), slate(), REL, NOW)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["label"], "single-book benchmark")

    def test_scope_and_explicit_alternate(self):
        for flag in [None, False]:
            s = source()
            if flag is None:
                s.pop("request_scope")
            else:
                for o in s["events"][0]["odds"].values():
                    for b in o["byBookmaker"].values():
                        b["isMainLine"] = False
            self.assertEqual(benchmarks(s, slate(), REL, NOW)[0], [])

    def test_stale_and_post_cutoff(self):
        for t in [NOW + timedelta(minutes=16), NOW + timedelta(hours=3, seconds=1)]:
            self.assertEqual(benchmarks(source(), slate(), REL, t)[0], [])

    def test_missing_opposite_no_consensus(self):
        s = source()
        s["events"][0]["odds"] = {
            k: o for k, o in s["events"][0]["odds"].items() if o["sideID"] == "over"
        }
        self.assertEqual(benchmarks(s, slate(), REL, NOW)[0], [])

    def test_unique_spacing_only_and_ambiguity(self):
        s = source()
        s["events"][0]["players"]["SYNTH_PLAYER_1_NFL"]["name"] = "SyntheticPlayer"
        self.assertEqual(len(benchmarks(s, slate(), REL, NOW)[0]), 7)
        import pandas as pd

        f = slate()
        extra = f.copy()
        extra["player_id"] = "other"
        extra["player"] = "SyntheticPlayer"
        # Compact-name collision without an exact match must remain ambiguous.
        s["events"][0]["players"]["SYNTH_PLAYER_1_NFL"]["name"] = "SyntheticPla yer"
        extra["player"] = "Syntheti cPlayer"
        self.assertEqual(benchmarks(s, pd.concat([f, extra]), REL, NOW)[0], [])

    def test_mobile_card_render_without_network(self):
        import os
        from unittest.mock import Mock, patch

        from streamlit.testing.v1 import AppTest

        with (
            patch.dict(
                os.environ,
                {
                    "SPORTSGAMEODDS_API_KEY": "synthetic_key_not_real",
                    "SGO_PRIVATE_CACHE_TERMS_ACK": "1",
                },
            ),
            patch("sgo_research.market_ui.datetime") as clock,
            patch("sgo_research.market_ui.quota_store", return_value=Mock()),
            patch("sgo_research.market_ui.Client") as client,
            patch("requests.get") as network,
        ):
            clock.now.return_value = NOW
            client.return_value.fetch.return_value = {**source(), "truncated": False}
            app = AppTest.from_string(
                "from tests.test_sgo_research import slate, REL\nfrom sgo_research.market_ui import render\nrender(slate(), REL)"
            ).run()
            next(
                b
                for b in app.button
                if b.label == "Retrieve selected fixture's market lines"
            ).click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any("multi-book median" in str(x.value) for x in app.get("markdown"))
            )
            network.assert_not_called()
