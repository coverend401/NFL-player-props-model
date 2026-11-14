"""Phase 1 account-only verification. Never retrieves odds or passes the gate.

No SDK installation, UI, forecasting integration, scheduler or database writes.
SPORTSGAMEODDS_API_KEY is sent only in the documented x-api-key header.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://api.sportsgameodds.com/v2/account/usage"
INTERVALS = ("per-second", "per-minute", "per-hour", "per-day", "per-month")
LIMIT_FIELDS = ("max-entities", "current-entities", "max-requests", "current-requests")


class ProbeBlocked(RuntimeError):
    pass


def output_guard(output):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ProbeBlocked("Save the private account report outside the repository")
    if output.exists():
        raise ProbeBlocked("Report path exists; choose a new private path")
    return output


def account_only(api_key, *, get=requests.get):
    if not isinstance(api_key, str) or not api_key.strip():
        raise ProbeBlocked("No SPORTSGAMEODDS_API_KEY configured; no request made")
    api_key = api_key.strip()
    if len(api_key) < 12 or any(c in api_key for c in "\r\n"):
        raise ProbeBlocked("Invalid credential format; no request made")
    started = datetime.now(timezone.utc)
    try:
        response = get(
            URL,
            headers={"x-api-key": api_key, "Accept": "application/json"},
            timeout=(5, 20),
            allow_redirects=False,
        )
    except requests.RequestException:
        # Never expose exception URLs, request headers or an echoed credential.
        raise ProbeBlocked(
            "Provider network request failed; no retry or odds request made"
        ) from None
    if response.status_code != 200:
        raise ProbeBlocked(
            f"Account endpoint HTTP {response.status_code}; stopped without retries or odds requests"
        )
    if len(response.content) > 128 * 1024:
        raise ProbeBlocked("Unexpected account response size")
    if api_key.encode() in response.content:
        raise ProbeBlocked("Provider echoed a credential; response discarded")
    try:
        body = json.loads(response.content)
    except (ValueError, UnicodeDecodeError):
        raise ProbeBlocked("Unexpected account JSON; body discarded") from None
    if not isinstance(body, dict) or body.get("success") is False:
        raise ProbeBlocked("Unexpected account envelope")
    data = body.get("data", body)
    if not isinstance(data, dict):
        raise ProbeBlocked("Unexpected account schema")
    tier = data.get("tier")
    if not isinstance(tier, str) or tier.strip().casefold() != "amateur":
        raise ProbeBlocked(
            "Account does not establish the Amateur tier; no paid/trial fallback"
        )
    if data.get("isActive") is not True:
        raise ProbeBlocked("Account is not documented as active")
    limits = data.get("rateLimits")
    if not isinstance(limits, dict):
        raise ProbeBlocked("Account rate limits missing; no allowance can be assumed")
    clean = {}
    for interval in INTERVALS:
        entry = limits.get(interval)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise ProbeBlocked("Malformed account rate limit")
        row = {}
        for field in LIMIT_FIELDS:
            value = entry.get(field)
            if value is None:
                row[field] = None
            elif type(value) is int and value >= 0:
                row[field] = value
            elif field.startswith("max-") and value == "unlimited":
                row[field] = value
            else:
                raise ProbeBlocked("Unrecognised account limit; do not infer a quota")
        clean[interval] = row
    return dict(
        classification="PHASE1_ACCOUNT_ONLY_NOT_FREE_PROP_ENTITLEMENT_PROOF",
        endpoint=URL,
        request_started_at=started.isoformat(),
        response_observed_at=datetime.now(timezone.utc).isoformat(),
        tier="Amateur",
        is_active=True,
        rate_limits=clean,
        monthly_entity_limit_reported=type(
            clean.get("per-month", {}).get("max-entities")
        )
        is int,
        network_requests=1,
        odds_requests=0,
        gate_passed=False,
        remaining_requirements=[
            "current free-plan entitlement and object definition",
            "NFL prop responses",
            "UK bookmaker jurisdiction and seven-market coverage",
            "refresh/reset policy",
            "retention and commercial-use rights",
        ],
    )


def run(output, *, api_key=None, get=requests.get):
    output = output_guard(output)
    report = account_only(
        api_key if api_key is not None else os.environ.get("SPORTSGAMEODDS_API_KEY"),
        get=get,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--account-only", action="store_true", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = run(args.output)
    except ProbeBlocked as error:
        print(str(error))
        raise SystemExit(2) from None
    print(
        "Sanitised Amateur account report saved privately; NFL coverage gate remains unpassed."
    )
