"""Real research entrypoint + real approved release; cold and warm Cloud imports."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Real approved release requires Python 3.14"
)
class ResearchStartupTests(unittest.TestCase):
    def test_real_entrypoint_with_cloud_secrets_and_warm_r5_signature(self):
        from streamlit.testing.v1 import AppTest

        import research_platform.ui as dashboard
        from sgo_research.market_ui import render as current_collection

        calls = []

        # The actual r5 callable accepted exactly these two positional arguments.
        # Retain that interface while exercising the complete real collection body.
        def warm_r5_collection(slate, release):
            calls.append((type(slate), type(release), slate.week.dtype))
            return current_collection(slate, release)

        secrets = {
            "RESEARCH_PREVIEW_PASSWORD": "synthetic_cloud_startup_only",
            "SPORTSGAMEODDS_API_KEY": "synthetic_key_never_sent",
            "SGO_QUOTA_REPOSITORY": "example/private-quota",
            "SGO_GITHUB_QUOTA_TOKEN": "github_pat_synthetic_never_sent",
            "SGO_PRIVATE_CACHE_TERMS_ACK": "1",
        }
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("research_access.st.secrets", secrets),
            patch.object(dashboard, "render_collection", warm_r5_collection),
            patch("requests.get") as get,
            patch("requests.request") as request,
            patch("sgo_research.market_ui.quota_store") as quota,
        ):
            app = AppTest.from_file(
                str(ROOT / "odds_value_research.py"), default_timeout=60
            ).run()
            self.assertFalse(app.exception, app.exception)
            app.text_input(key="research_password").input(
                secrets["RESEARCH_PREVIEW_PASSWORD"]
            )
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any(
                    b.label == "Retrieve selected fixture's market lines"
                    for b in app.button
                )
            )
            self.assertTrue(
                any(
                    e.label == "Load / refresh genuine bookmaker prices"
                    for e in app.expander
                )
            )
            self.assertTrue(
                any(
                    e.label == "Collection diagnostics (no credentials shown)"
                    for e in app.expander
                )
            )
            self.assertTrue(calls)
            self.assertIs(calls[0][0], pd.DataFrame)
            self.assertIs(calls[0][1], dict)
            for section in [
                "Player Intelligence",
                "Game Intelligence",
                "Market Intelligence",
                "Model Performance",
                "Data & Safety",
                "Top Picks",
            ]:
                next(w for w in app.selectbox if w.label == "Workspace").select(
                    section
                ).run(timeout=60)
                self.assertFalse(app.exception, app.exception)
            get.assert_not_called()
            request.assert_not_called()
            quota.assert_not_called()

    def test_real_entrypoint_cold_render_with_configured_key(self):
        from streamlit.testing.v1 import AppTest

        with (
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic_cold_startup_only",
                    "SPORTSGAMEODDS_API_KEY": "synthetic_key_never_sent",
                },
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            app = AppTest.from_file(
                str(ROOT / "odds_value_research.py"), default_timeout=60
            ).run()
            app.text_input(key="research_password").input("synthetic_cold_startup_only")
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any(
                    b.label == "Retrieve selected fixture's market lines"
                    for b in app.button
                )
            )
            get.assert_not_called()
            request.assert_not_called()
