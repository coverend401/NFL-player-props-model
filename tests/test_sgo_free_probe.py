"""Synthetic account responses test probe safety, never real plan/prop coverage."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import requests
from scripts.probe_sgo_free_account import account_only, run, ProbeBlocked, ROOT, URL

KEY = "synthetic_secret_for_unit_tests_only"


def response(data=None, status=200):
    # 1234 is an arbitrary fixture value, not a claim about the provider's quota.
    if data is None:
        data = dict(
            tier="Amateur",
            isActive=True,
            email="private@example.invalid",
            customerID="private-billing-id",
            keyID="private-key-id",
            rateLimits={
                "per-month": {
                    "max-entities": 1234,
                    "current-entities": 5,
                    "max-requests": "unlimited",
                    "current-requests": 2,
                },
                "per-minute": {"max-requests": 10, "current-requests": 1},
            },
        )
    return Mock(
        status_code=status, content=json.dumps(dict(success=True, data=data)).encode()
    )


class Phase1ProbeTests(unittest.TestCase):
    def test_no_key_does_not_make_request(self):
        get = Mock()
        with self.assertRaisesRegex(ProbeBlocked, "no request made"):
            account_only(None, get=get)
        get.assert_not_called()

    def test_header_only_and_no_odds_or_entitlement_claim(self):
        get = Mock(return_value=response())
        r = account_only(KEY, get=get)
        self.assertEqual(get.call_count, 1)
        args, kw = get.call_args
        self.assertEqual(args, (URL,))
        self.assertEqual(kw["headers"]["x-api-key"], KEY)
        self.assertNotIn("params", kw)
        self.assertFalse(kw["allow_redirects"])
        self.assertFalse(r["gate_passed"])
        self.assertEqual(r["odds_requests"], 0)
        self.assertEqual(r["rate_limits"]["per-month"]["max-entities"], 1234)
        raw = json.dumps(r)
        for private in [
            KEY,
            "private@example.invalid",
            "private-billing-id",
            "private-key-id",
        ]:
            self.assertNotIn(private, raw)

    def test_paid_trial_unknown_and_inactive_accounts_stop(self):
        for tier in ["Rookie", "Pro", "AllStar", "free trial", None]:
            with (
                self.subTest(tier=tier),
                self.assertRaisesRegex(ProbeBlocked, "Amateur tier"),
            ):
                account_only(
                    KEY,
                    get=Mock(
                        return_value=response(
                            dict(tier=tier, isActive=True, rateLimits={})
                        )
                    ),
                )
        with self.assertRaisesRegex(ProbeBlocked, "not documented as active"):
            account_only(
                KEY,
                get=Mock(return_value=response(dict(tier="Amateur", isActive=False))),
            )

    def test_unknown_limits_are_not_invented(self):
        r = account_only(
            KEY,
            get=Mock(
                return_value=response(
                    dict(
                        tier="Amateur",
                        isActive=True,
                        rateLimits={"per-minute": {"max-requests": 10}},
                    )
                )
            ),
        )
        self.assertFalse(r["monthly_entity_limit_reported"])
        for v in [True, -1, "1234", 1.5]:
            data = json.loads(response().content)["data"]
            data["rateLimits"]["per-month"]["max-entities"] = v
            with self.assertRaisesRegex(ProbeBlocked, "Unrecognised account limit"):
                account_only(KEY, get=Mock(return_value=response(data)))
        data = json.loads(response().content)["data"]
        data["rateLimits"]["per-month"]["current-entities"] = "unlimited"
        with self.assertRaises(ProbeBlocked):
            account_only(KEY, get=Mock(return_value=response(data)))

    def test_error_and_redirect_bodies_are_never_exposed_or_retried(self):
        for status in [301, 302, 401, 403, 429, 500]:
            get = Mock(return_value=Mock(status_code=status, content=KEY.encode()))
            with self.subTest(status=status), self.assertRaises(ProbeBlocked) as cm:
                account_only(KEY, get=get)
            self.assertNotIn(KEY, str(cm.exception))
            self.assertEqual(get.call_count, 1)
        get = Mock(side_effect=requests.ConnectionError("unsafe error " + KEY))
        with self.assertRaises(ProbeBlocked) as cm:
            account_only(KEY, get=get)
        self.assertNotIn(KEY, str(cm.exception))

    def test_echoed_key_malformed_json_or_oversized_payload_is_rejected(self):
        for body in [
            KEY.encode(),
            b"not JSON",
            b"x" * (128 * 1024 + 1),
            b"[]",
            b'{"data": []}',
            b'{"success": false}',
        ]:
            with self.subTest(size=len(body)), self.assertRaises(ProbeBlocked):
                account_only(
                    KEY, get=Mock(return_value=Mock(status_code=200, content=body))
                )

    def test_private_report_and_existing_path_fail_before_request(self):
        get = Mock(return_value=response())
        with self.assertRaisesRegex(ProbeBlocked, "outside the repository"):
            run(ROOT / "forbidden_account_report.json", api_key=KEY, get=get)
        get.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            result = run(path, api_key=KEY, get=get)
            self.assertFalse(result["gate_passed"])
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertNotIn(KEY, path.read_text())
            get.reset_mock()
            with self.assertRaisesRegex(ProbeBlocked, "exists"):
                run(path, api_key=KEY, get=get)
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
