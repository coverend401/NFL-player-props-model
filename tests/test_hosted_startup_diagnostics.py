"""Show the underlying hosted admission failure, without printing exceptions."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_platform import startup_diagnostics as diagnostics


class DiagnosticTests(unittest.TestCase):
    def test_git_origin_authentication_is_never_displayed(self):
        secret = "synthetic-private-token"
        with patch.object(
            diagnostics,
            "git_value",
            side_effect=[
                "a" * 40,
                "sportsgameodds-free-feasibility",
                "https://user:"
                + secret
                + "@github.com/coverend401/NFL-player-props-model.git",
            ],
        ):
            result = diagnostics.deployment()
        self.assertEqual(result["repository"], "coverend401/NFL-player-props-model")
        self.assertNotIn(secret, json.dumps(result))

    def test_production_release_cannot_be_reported_as_research_success(self):
        with patch(
            "research_platform.inference_release.resolve_research_release",
            return_value=(diagnostics.ROOT, {"release_id": "stage1a"}),
        ):
            self.assertEqual(
                diagnostics.preflight(),
                {"status": "FAIL", "code": "WRONG_RESEARCH_RELEASE"},
            )

    def test_runtime_failure_names_only_a_pinned_package(self):
        with patch("importlib.metadata.version", return_value="0.0.0"):
            result = diagnostics.safe_failure(
                ValueError(
                    "Runtime package mismatch: pyarrow: expected 24.0.0, found 0.0.0"
                )
            )
        self.assertEqual(
            result,
            {
                "code": "RUNTIME_PACKAGE_MISMATCH",
                "package": "pyarrow",
                "expected": "24.0.0",
                "installed": "0.0.0",
            },
        )

    def test_arbitrary_secret_paths_and_exception_text_never_escape(self):
        secret = "synthetic_credential_do_not_display"
        for error in [
            ValueError(secret),
            FileNotFoundError(2, secret, "/" + secret),
            ValueError("Runtime package mismatch: " + secret),
            ValueError("Release/code mismatch: " + secret),
        ]:
            self.assertNotIn(secret, json.dumps(diagnostics.safe_failure(error)))

    def test_missing_pointer_and_source_integrity_have_distinct_codes(self):
        self.assertEqual(
            diagnostics.safe_failure(
                ValueError("Requested research inference pointer missing")
            )["code"],
            "RESEARCH_POINTER_MISSING",
        )
        self.assertEqual(
            diagnostics.safe_failure(ValueError("Inference source/code mismatch"))[
                "code"
            ],
            "RESEARCH_SOURCE_HASH_MISMATCH",
        )

    def test_preflight_preserves_failure_and_does_not_fallback(self):
        with patch(
            "research_platform.inference_release.resolve_research_release",
            side_effect=ValueError("Inference pointer/manifest mismatch"),
        ) as resolve:
            self.assertEqual(
                diagnostics.preflight(),
                {"status": "FAIL", "code": "RESEARCH_POINTER_HASH_MISMATCH"},
            )
            resolve.assert_called_once()


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Real certified release requires Python 3.14"
)
class ActualEntrypointTests(unittest.TestCase):
    def test_authenticated_missing_pointer_reproduces_generic_failure_and_diagnoses_it(
        self,
    ):
        from streamlit.testing.v1 import AppTest

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic-hosted-diagnostic",
                    "NFL_RESEARCH_INFERENCE_POINTER": "missing-research-pointer-synthetic.json",
                    "SPORTSGAMEODDS_API_KEY": "",
                    "SGO_GITHUB_QUOTA_TOKEN": "",
                    "SGO_RESEARCH_STORE": str(Path(tmp) / "cache.sqlite"),
                },
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            app = AppTest.from_file(
                str(diagnostics.ROOT / "odds_value_research.py"), default_timeout=120
            ).run()
            self.assertFalse(app.json)
            app.text_input(key="research_password").input("synthetic-hosted-diagnostic")
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any("Approved release unavailable" in e.value for e in app.error)
            )
            app.button(key="research_startup_preflight").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any("RESEARCH_POINTER_MISSING" in j.value for j in app.json)
            )
            self.assertFalse(any("<article" in x.value for x in app.markdown))
            get.assert_not_called()
            request.assert_not_called()
