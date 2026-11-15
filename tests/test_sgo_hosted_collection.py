"""Hosted path regressions; synthetic credentials, no remote service calls."""

import os
import unittest
from datetime import timedelta
from unittest.mock import Mock, patch

import requests

from sgo_research.config import quota_store
from sgo_research.contracts import Unavailable
from sgo_research.diagnostics import CollectionBlocked, safe_diagnostic
from sgo_research.github_quota import GitHubAPI
from tests.test_market_benchmarks import source
from tests.test_sgo_research import NOW


class HostedCollectionTests(unittest.TestCase):
    def test_root_secrets_read_without_environment_bridge(self):
        from sgo_research.ui import research_key

        secrets = {
            "SGO_QUOTA_REPOSITORY": "example/private-counter",
            "SGO_GITHUB_QUOTA_TOKEN": " synthetic-token ",
            "SPORTSGAMEODDS_API_KEY": "synthetic-key",
        }
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("research_access.st.secrets", secrets),
            patch("sgo_research.config.GitHubQuotaStore") as store,
        ):
            self.assertEqual(research_key(), "synthetic-key")
            quota_store()
            self.assertEqual(store.call_args.args[0], "example/private-counter")
            self.assertEqual(store.call_args.kwargs["api"].token, "synthetic-token")
            self.assertNotIn("SGO_GITHUB_QUOTA_TOKEN", os.environ)

    def test_missing_hosted_token_never_falls_back_to_local_gh(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "research_access.st.secrets",
                {"SGO_QUOTA_REPOSITORY": "example/private-counter"},
            ),
            patch("subprocess.run") as gh,
            patch("requests.request") as http,
        ):
            with self.assertRaises(CollectionBlocked) as ctx:
                quota_store()
            self.assertEqual(ctx.exception.code, "CONFIG_TOKEN")
            gh.assert_not_called()
            http.assert_not_called()

    def test_github_http_codes_do_not_expose_response_or_token(self):
        for method in ["GET", "PUT"]:
            for status in [401, 403, 404, 422, 500]:
                reply = Mock(
                    status_code=status,
                    text="SENSITIVE_BODY",
                    json=Mock(return_value={"secret": "SENSITIVE_BODY"}),
                )
                with (
                    patch("requests.request", return_value=reply),
                    self.assertRaises(CollectionBlocked) as ctx,
                ):
                    GitHubAPI("SENSITIVE_TOKEN")(method, "repos/example/private")
                code, message = safe_diagnostic(ctx.exception)
                self.assertEqual(
                    code,
                    f"GITHUB_{'READ' if method == 'GET' else 'WRITE'}_{status}"
                    if status in [401, 403, 404]
                    else "GITHUB_HTTP",
                )
                self.assertNotIn("SENSITIVE", message)

    def test_conflict_semantics_preserved(self):
        with patch("requests.request", return_value=Mock(status_code=409)):
            self.assertIsNone(GitHubAPI("synthetic")("PUT", "repos/example/private"))

    def test_unknown_exception_cannot_leak_secrets(self):
        for error in [
            ValueError("SENSITIVE_TOKEN"),
            OSError("/private/SENSITIVE_PATH"),
            CollectionBlocked("SENSITIVE_CODE"),
        ]:
            code, message = safe_diagnostic(error)
            self.assertEqual(code, "UNKNOWN")
            self.assertNotIn("SENSITIVE", message)
        self.assertEqual(safe_diagnostic(Unavailable("Collector halted"))[0], "HALTED")
        self.assertEqual(
            safe_diagnostic(
                Unavailable("Conservative six-request/minute limit reached")
            )[0],
            "RATE",
        )

    def test_transport_error_redacted(self):
        with (
            patch(
                "requests.request",
                side_effect=requests.ConnectionError("SENSITIVE_URL_TOKEN"),
            ),
            self.assertRaises(Unavailable) as ctx,
        ):
            GitHubAPI("synthetic")("GET", "repos/example/private")
        self.assertEqual(safe_diagnostic(ctx.exception)[0], "GITHUB_NETWORK")

    def run_preview(self, error=None, received=None):
        from streamlit.testing.v1 import AppTest

        with (
            patch.dict(
                os.environ,
                {
                    "SPORTSGAMEODDS_API_KEY": "synthetic-key-only",
                    "SGO_PRIVATE_CACHE_TERMS_ACK": "1",
                },
            ),
            patch("sgo_research.market_ui.datetime") as clock,
            patch("sgo_research.market_ui.quota_store", return_value=Mock()),
            patch("sgo_research.market_ui.Client") as client,
            patch("requests.get") as network,
        ):
            clock.now.side_effect = [NOW, NOW, NOW, NOW + timedelta(seconds=5)]
            if error:
                client.return_value.fetch.side_effect = error
            else:
                s = {**source(), "retrieved_at": (received or NOW).isoformat()}
                client.return_value.fetch.return_value = s
            app = AppTest.from_string(
                "from tests.test_sgo_research import slate, REL\nfrom sgo_research.market_ui import render\nrender(slate(), REL)"
            ).run()
            app.button[0].click().run()
            network.assert_not_called()
            self.assertFalse(app.exception, app.exception)
            return app

    def test_provider_latency_capture_is_not_rejected_as_future(self):
        app = self.run_preview(received=NOW + timedelta(seconds=3))
        self.assertTrue(
            any("multi-book median" in str(x.value) for x in app.get("markdown"))
        )

    def test_hosted_diagnostic_display_and_log_redaction(self):
        with self.assertLogs("sgo_research.market_ui", level="WARNING") as logs:
            app = self.run_preview(error=CollectionBlocked("GITHUB_WRITE_403"))
        self.assertTrue(any("[GITHUB_WRITE_403]" in x.value for x in app.warning))
        self.assertTrue(any("code=GITHUB_WRITE_403" in x for x in logs.output))
        with self.assertLogs("sgo_research.market_ui", level="WARNING") as logs:
            app = self.run_preview(error=ValueError("SENSITIVE_API_KEY"))
        self.assertNotIn("SENSITIVE", " ".join(logs.output))
        self.assertTrue(any("[UNKNOWN]" in x.value for x in app.warning))
