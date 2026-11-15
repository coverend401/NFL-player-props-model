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

    def test_opaque_header_safe_token_not_rejected_by_guessed_github_format(self):
        for token in [
            "future-provider.format~+/=-opaque",
            "github_pat_synthetic.with-hyphen",
            "unrecognisedButHeaderSafeOpaqueValue",
        ]:
            with patch(
                "sgo_research.credentials.st.secrets", {"SGO_GITHUB_QUOTA_TOKEN": token}
            ):
                self.assertEqual(quota_credential()[0], token)
                self.assertNotIn(token, credential_status())

    def test_local_rejection_reasons_are_specific_and_safe(self):
        cases = [
            (123, "TOKEN_TYPE"),
            ('"' + TOKEN + '"', "TOKEN_QUOTES"),
            ("Bearer " + TOKEN, "TOKEN_SCHEME"),
            (TOKEN + "\ninside", "TOKEN_WHITESPACE"),
            (TOKEN + "\u200b", "TOKEN_HEADER"),
        ]
        for value, code in cases:
            with patch(
                "sgo_research.credentials.st.secrets", {"SGO_GITHUB_QUOTA_TOKEN": value}
            ):
                with self.assertRaises(CollectionBlocked) as ctx:
                    quota_credential()
                self.assertEqual(ctx.exception.code, code)
                self.assertNotIn(TOKEN, credential_status())

    def test_negative_control_success_blocks_before_real_credential_or_quota(self):
        with (
            patch(
                "requests.request",
                return_value=Mock(status_code=200, json=Mock(return_value={"id": 123})),
            ) as http,
            self.assertRaises(CollectionBlocked) as ctx,
        ):
            GitHubAPI(TOKEN).verify_authentication()
        self.assertEqual(ctx.exception.code, "AUTH_SUBSTITUTION")
        self.assertEqual(http.call_count, 1)
        self.assertNotIn(TOKEN, http.call_args.kwargs["headers"]["Authorization"])

    def test_negative_401_then_valid_authentication_is_read_only(self):
        replies = [
            Mock(status_code=401),
            Mock(
                status_code=200,
                json=Mock(
                    return_value={
                        "id": 123,
                        "login": "synthetic_account_never_displayed",
                    }
                ),
            ),
        ]
        with patch("requests.request", side_effect=replies) as http:
            self.assertIsNone(GitHubAPI(TOKEN).verify_authentication())
        self.assertEqual(http.call_count, 2)
        self.assertTrue(
            all(
                c.args[0] == "GET" and c.args[1] == "https://api.github.com/user"
                for c in http.call_args_list
            )
        )
        self.assertEqual(
            http.call_args_list[1].kwargs["headers"]["Authorization"], "Bearer " + TOKEN
        )

    def test_auth_rejection_and_permissions_are_distinct(self):
        for status, code in [(401, "TOKEN_REJECTED"), (403, "AUTH_PERMISSION")]:
            with (
                patch(
                    "requests.request",
                    side_effect=[Mock(status_code=401), Mock(status_code=status)],
                ),
                self.assertRaises(CollectionBlocked) as ctx,
            ):
                GitHubAPI(TOKEN).verify_authentication()
            self.assertEqual(ctx.exception.code, code)

    def test_negative_control_inconclusive_fails_closed(self):
        with (
            patch("requests.request", return_value=Mock(status_code=403)) as http,
            self.assertRaises(CollectionBlocked) as ctx,
        ):
            GitHubAPI(TOKEN).verify_authentication()
        self.assertEqual(ctx.exception.code, "AUTH_CONTROL_INCONCLUSIVE")
        self.assertEqual(http.call_count, 1)

    def test_normal_toml_quotes_are_delimiters_not_credential_content(self):
        import tomllib

        parsed = tomllib.loads('SGO_GITHUB_QUOTA_TOKEN = "' + TOKEN + '"')
        with patch("sgo_research.credentials.st.secrets", parsed):
            self.assertEqual(quota_credential()[0], TOKEN)

    def test_factory_detects_substitution_before_store_access(self):
        from sgo_research.config import quota_store

        with (
            patch("sgo_research.config.secret", return_value="example/private-quota"),
            patch(
                "sgo_research.config.quota_credential",
                return_value=(TOKEN, "Streamlit Secrets"),
            ),
            patch(
                "requests.request",
                return_value=Mock(status_code=200, json=Mock(return_value={"id": 123})),
            ),
            patch("sgo_research.config.GitHubQuotaStore") as store,
        ):
            with self.assertRaises(CollectionBlocked) as ctx:
                quota_store()
            self.assertEqual(ctx.exception.code, "AUTH_SUBSTITUTION")
            store.assert_not_called()
