"""Real research entrypoint + real approved release; cold and warm Cloud imports."""

import os
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from release_utils import resolve_release as resolve_training_release

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Real approved release requires Python 3.14"
)
class ResearchStartupTests(unittest.TestCase):
    def test_real_entrypoint_with_cloud_secrets_and_warm_r5_signature(self):
        from streamlit.testing.v1 import AppTest

        import research_platform.r7 as dashboard
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
            patch.object(dashboard, "render_fixture", warm_r5_collection),
            patch("sgo_research.market_ui.datetime") as collection_clock,
            patch(
                "research_platform.inference_release.resolve_research_release",
                side_effect=resolve_training_release,
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
            patch("sgo_research.market_ui.quota_store") as quota,
        ):
            # Fixed eligible time keeps the startup regression valid after this slate ends.
            collection_clock.now.return_value = datetime(2026, 11, 15, 8, tzinfo=UTC)
            app = AppTest.from_string(
                (ROOT / "odds_value_research.py")
                .read_text()
                .replace("research_platform.r8", "research_platform.r7")
                .replace(
                    "root = Path(__file__).resolve().parent",
                    f"root = Path({str(ROOT)!r})",
                ),
                default_timeout=60,
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
                    e.label == "Refresh prices — slate-wide collection"
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
            # Archived cold-start component test, not current selection admission.
            patch(
                "research_platform.selection_integrity.block_reason", return_value=None
            ),
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic_cold_startup_only",
                    "SPORTSGAMEODDS_API_KEY": "synthetic_key_never_sent",
                },
            ),
            patch("research_platform.r8.datetime") as collection_clock,
            patch(
                "research_platform.inference_release.resolve_research_release",
                side_effect=resolve_training_release,
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            # Fixed eligible time keeps the startup regression valid after this slate ends.
            collection_clock.now.return_value = datetime(2026, 11, 15, 8, tzinfo=UTC)
            app = AppTest.from_file(
                str(ROOT / "odds_value_research.py"), default_timeout=60
            ).run()
            app.text_input(key="research_password").input("synthetic_cold_startup_only")
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any(
                    b.label == "Discover & collect missing eligible fixtures"
                    for b in app.button
                )
            )
            for section in [
                "Top 2 by Game",
                "Parlay Research",
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
