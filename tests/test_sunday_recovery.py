"""No live API or private ledger writes."""

import copy
import json
import sys
import unittest
from pathlib import Path

from sgo_research.contracts import Unavailable
from sgo_research.github_quota import GitHubQuotaStore
from tests.test_sgo_private_quota import API


class RecoveryTests(unittest.TestCase):
    def setup_store(self):
        api = API()
        api.state["halt"] = "manual_review_required"
        # Eleven records summing to 81, each a valid positive reservation.
        api.state["reservations"] = [
            {"id": str(i), "at": "2026-11-15T10:00:00+00:00", "objects": n}
            for i, n in enumerate([16, 16, 16, 16, 7, 2, 2, 2, 2, 1, 1])
        ]
        api.state["reserved_objects"] = 81
        store = object.__new__(GitHubQuotaStore)
        store.api = api
        store.repository = "example/private"
        return store, api, copy.deepcopy(api.state)

    def test_preserves_every_other_field(self):
        store, api, state = self.setup_store()
        result = store.recover_halt_once(state, "1", credential_rotation_confirmed=True)
        state["halt"] = None
        self.assertEqual(result, state)
        self.assertEqual(api.state, state)

    def test_rotation_required_and_conflict_not_retried(self):
        store, api, state = self.setup_store()
        with self.assertRaises(Unavailable):
            store.recover_halt_once(state, "1")
        self.assertEqual(api.version, 1)
        api.conflict = 1
        with self.assertRaises(Unavailable):
            store.recover_halt_once(state, "1", credential_rotation_confirmed=True)
        self.assertEqual(api.version, 2)
        self.assertEqual(api.state, state)

    def test_readback_change_stops_without_retry(self):
        store, api, state = self.setup_store()

        def changed(method, path, payload=None):
            result = api(method, path, payload)
            if method == "PUT" and result:
                api.state["halt"] = "manual_review_required"
            return result

        store.api = changed
        with self.assertRaises(Unavailable):
            store.recover_halt_once(state, "1", credential_rotation_confirmed=True)
        self.assertEqual(api.version, 2)
        self.assertEqual(api.state, state)

    def test_stale_sha_or_state_blocked(self):
        for changed in ["sha", "state"]:
            store, api, state = self.setup_store()
            if changed == "state":
                state["calls"].append("2026-11-20T10:00:00+00:00")
            with self.assertRaises(Unavailable):
                store.recover_halt_once(
                    state,
                    "old" if changed == "sha" else "1",
                    credential_rotation_confirmed=True,
                )
            self.assertEqual(api.version, 1)


@unittest.skipUnless(sys.version_info[:2] == (3, 14), "Runtime-pinned research bundle")
class CertifiedEvidenceTests(unittest.TestCase):
    def test_real_all_market_cards_have_recorded_context_and_no_mutation(self):
        import pandas as pd

        from research_platform.cards81 import explanation
        from research_platform.football_evidence import attach_context

        root = Path(__file__).resolve().parents[1]
        pointer = json.loads(
            (root / "tests/fixtures/week11_research_pointer.json").read_text()
        )
        directory = root / pointer["path"]
        release = json.loads((directory / "manifest.json").read_text())
        picks = pd.read_parquet(directory / "top_picks.parquet")
        slate = pd.read_parquet(directory / "slate.parquet")
        rows = slate[slate.projection_status.eq("complete")].to_dict("records")
        enriched = attach_context(rows, release)
        count = 0
        for row in enriched:
            text = explanation(row, None)
            if "averaged" in text:
                count += 1
            self.assertNotIn("positive betting value", text)
            self.assertNotIn("qb rushing attempts per team", text.lower())
            self.assertNotIn("qb rushing yards per team", text.lower())
        self.assertEqual(count, len(rows))
        self.assertEqual(len(picks), 22)
        self.assertEqual(len(slate), 618)


@unittest.skipUnless(sys.version_info[:2] == (3, 14), "Runtime-pinned research bundle")
class RealEntrypointTests(unittest.TestCase):
    def test_certified_default_full_workspaces_no_live_requests(self):
        import os
        import tempfile
        from unittest.mock import patch

        from streamlit.testing.v1 import AppTest

        from tests.archived_week11 import archived_week11

        root = Path(__file__).resolve().parents[1]
        with (
            archived_week11(),
            tempfile.TemporaryDirectory() as d,
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic-local-only",
                    "SPORTSGAMEODDS_API_KEY": "",
                    "SGO_RESEARCH_STORE": str(Path(d) / "cache.sqlite"),
                },
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            app = AppTest.from_file(
                str(root / "odds_value_research.py"), default_timeout=90
            ).run()
            app.text_input(key="research_password").input("synthetic-local-only")
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            cards = [
                e.value for e in app.markdown if '<article class="desk-card' in e.value
            ]
            self.assertTrue(cards)
            self.assertTrue(all("averaged" in text for text in cards))
            for section in list(app.selectbox[0].options):
                app.selectbox[0].select(section).run()
                self.assertFalse(app.exception, (section, app.exception))
            get.assert_not_called()
            request.assert_not_called()
