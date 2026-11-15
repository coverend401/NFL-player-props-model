"""Credential-selection and transport regressions; synthetic values only."""

import os
import unittest
from unittest.mock import Mock, patch

import requests

from sgo_research.credentials import credential_status, quota_credential
from sgo_research.diagnostics import CollectionBlocked
from sgo_research.github_quota import GitHubAPI, QuotaBearerAuth

TOKEN = "github_pat_synthetic_not_a_real_token"


class QuotaAuthTests(unittest.TestCase):
    def test_cloud_secret_wins_over_stale_environment(self):
        with (
            patch.dict(os.environ, {"SGO_GITHUB_QUOTA_TOKEN": "ghp_stale_synthetic"}),
            patch(
                "sgo_research.credentials.st.secrets", {"SGO_GITHUB_QUOTA_TOKEN": TOKEN}
            ),
        ):
            self.assertEqual(quota_credential(), (TOKEN, "Streamlit Secrets"))
            self.assertNotIn(TOKEN, credential_status())

    def test_environment_fallback_only_when_cloud_key_absent(self):
        with (
            patch.dict(os.environ, {"SGO_GITHUB_QUOTA_TOKEN": TOKEN}),
            patch("sgo_research.credentials.st.secrets", {}),
        ):
            self.assertEqual(quota_credential(), (TOKEN, "environment"))

    def test_empty_or_malformed_secret_cannot_use_another_credential(self):
        for value in [
            "",
            " ",
            '"' + TOKEN + '"',
            "'" + TOKEN + "'",
            "Bearer " + TOKEN,
            TOKEN + "\nextra",
            TOKEN + " space",
            123,
            {"token": TOKEN},
        ]:
            with (
                patch.dict(os.environ, {"SGO_GITHUB_QUOTA_TOKEN": TOKEN}),
                patch(
                    "sgo_research.credentials.st.secrets",
                    {"SGO_GITHUB_QUOTA_TOKEN": value},
                ),
            ):
                with self.assertRaises(CollectionBlocked):
                    quota_credential()
                self.assertNotIn(TOKEN, credential_status())

    def test_outer_whitespace_only_is_removed(self):
        with patch(
            "sgo_research.credentials.st.secrets",
            {"SGO_GITHUB_QUOTA_TOKEN": " \n" + TOKEN + "\n "},
        ):
            self.assertEqual(quota_credential()[0], TOKEN)

    def test_prepared_request_has_exact_bearer_and_no_netrc_override(self):
        session = requests.Session()
        with patch(
            "requests.sessions.get_netrc_auth", return_value=("another", "credential")
        ) as netrc:
            prepared = session.prepare_request(
                requests.Request(
                    "GET",
                    "https://api.github.com/user",
                    headers={"Authorization": "Bearer " + TOKEN},
                    auth=QuotaBearerAuth(TOKEN),
                )
            )
            self.assertEqual(prepared.headers["Authorization"], "Bearer " + TOKEN)
            netrc.assert_not_called()

    def test_api_transport_passes_exact_auth_without_redirects(self):
        with patch(
            "requests.request",
            return_value=Mock(status_code=200, json=Mock(return_value={})),
        ) as request:
            GitHubAPI(TOKEN)("GET", "repos/example/private")
            kw = request.call_args.kwargs
            self.assertEqual(kw["headers"]["Authorization"], "Bearer " + TOKEN)
            self.assertFalse(kw["allow_redirects"])
            prepared = requests.Request("GET", "https://api.github.com/user").prepare()
            self.assertEqual(
                kw["auth"](prepared).headers["Authorization"], "Bearer " + TOKEN
            )

    def test_valid_format_rejected_by_github_remains_401(self):
        with (
            patch("requests.request", return_value=Mock(status_code=401)),
            self.assertRaises(CollectionBlocked) as ctx,
        ):
            GitHubAPI(TOKEN)("GET", "repos/example/private")
        self.assertEqual(ctx.exception.code, "GITHUB_READ_401")
        self.assertNotIn(TOKEN, str(ctx.exception))

    def test_explicit_empty_token_never_selects_another_identity(self):
        with (
            patch.dict(os.environ, {"SGO_GITHUB_QUOTA_TOKEN": TOKEN}),
            patch("subprocess.run") as gh,
        ):
            with self.assertRaises(CollectionBlocked):
                GitHubAPI("")
            gh.assert_not_called()
