"""Manual, non-backdated raw odds/rule capture. No production or database writes.

An authorised licensed source and private archive storage are prerequisites.
Captured bytes are UNREVIEWED evidence, not automatically a verified backtest.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.the-odds-api.com/v4"
MARKETS = [
    "player_pass_yds",
    "player_pass_attempts",
    "player_pass_completions",
    "player_rush_yds",
    "player_rush_attempts",
    "player_reception_yds",
    "player_receptions",
]


class CaptureUnavailable(RuntimeError):
    pass


def timestamp(value):
    from datetime import datetime

    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Provider timestamp has no timezone")
    return d.astimezone(timezone.utc)


def output_guard(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Capture IDs are immutable")
    if ROOT in output.parents and ROOT / "experiments" not in output.parents:
        raise ValueError("Capture cannot write production or source directories")
    return output


def store(output, raw, metadata, started):
    observed = datetime.now(timezone.utc)
    if "kickoff_at" in metadata and timestamp(metadata["kickoff_at"]) <= observed:
        raise ValueError("Event started before archive creation; capture refused")
    output = output_guard(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".capture-", dir=output.parent) as tmp:
        tmp = Path(tmp)
        (tmp / "response.bin").write_bytes(raw)
        metadata.update(
            observed_at=observed.isoformat(),
            request_started_at=started.isoformat(),
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
            classification="unreviewed_prospective_capture",
            backtest_ready=False,
            review_required=[
                "licence",
                "event/player mapping",
                "price availability",
                "historical settlement rule",
            ],
        )
        (tmp / "capture.json").write_text(json.dumps(metadata, indent=2) + "\n")
        if output.exists():
            raise ValueError("Capture path changed during request")
        os.rename(tmp, output)
    return metadata


def event_odds(event_id, output, *, regions="us,uk", get=requests.get, api_key=None):
    if not re.fullmatch("[A-Za-z0-9_-]{1,128}", event_id):
        raise ValueError("Invalid provider event ID")
    if not set(regions.split(",")) <= {"us", "uk", "eu", "au", "us2"}:
        raise ValueError("Unsupported region configuration")
    key = api_key if api_key is not None else os.environ.get("RESEARCH_ODDS_API_KEY")
    if not key:
        raise CaptureUnavailable(
            "No licensed research odds credential configured; no genuine quote was collected"
        )
    output_guard(output)
    started = datetime.now(timezone.utc)
    url = API + "/sports/americanfootball_nfl/events/" + event_id + "/odds"
    params = {
        "apiKey": key,
        "regions": regions,
        "markets": ",".join(MARKETS),
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    try:
        r = get(url, params=params, timeout=30, allow_redirects=False)
    except requests.RequestException:
        raise CaptureUnavailable(
            "Provider network request failed; check approved domain and entitlement"
        ) from None
    if r.status_code != 200:
        raise CaptureUnavailable(
            f"Provider HTTP {r.status_code}; response not archived; check access/entitlement"
        )
    raw = r.content
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("Unexpectedly large provider response")
    if key.encode() in raw:
        raise ValueError("Provider body unexpectedly contains request credential")
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise ValueError("Unexpected provider response format")
    if body.get("id") != event_id or body.get("sport_key") != "americanfootball_nfl":
        raise ValueError("Provider event identity differs")
    if any(k in body for k in ["apiKey", "api_key", "authorization", "token"]):
        raise ValueError("Unexpected credential field in provider body")
    now = datetime.now(timezone.utc)
    kickoff = timestamp(body["commence_time"])
    if kickoff <= now:
        raise ValueError("Event already started; pregame capture refused")
    quotes = 0
    for book in body.get("bookmakers", []):
        for market in book.get("markets", []):
            if market.get("key") not in MARKETS:
                continue
            updated = timestamp(market.get("last_update", book.get("last_update")))
            if updated > now:
                raise ValueError("Provider quote timestamp is in the future")
            for outcome in market.get("outcomes", []):
                if outcome.get("name") not in ["Over", "Under"] or not outcome.get(
                    "description"
                ):
                    raise ValueError("Unexpected player-prop outcome")
                price = float(outcome["price"])
                line = float(outcome["point"])
                import math

                if not math.isfinite(price) or price <= 1 or not math.isfinite(line):
                    raise ValueError("Invalid decimal price/line")
                quotes += 1
    if quotes == 0:
        raise CaptureUnavailable(
            "No requested player-prop quotes returned; no empty substitute archive created"
        )
    metadata = {
        "provider": "the_odds_api",
        "source_url": url,
        "vendor_event_id": event_id,
        "sport": "americanfootball_nfl",
        "kickoff_at": kickoff.isoformat(),
        "format": "decimal",
        "markets": MARKETS,
        "regions": regions,
        "quote_count": quotes,
        "http_date": r.headers.get("Date"),
        "etag": r.headers.get("ETag"),
        "availability_basis": "response observed now; quoted price is not proof of stake execution",
        "normalisation_status": "raw only; NFL event/player/position mapping requires separate review",
    }
    # The request query and credential are deliberately never persisted/logged.
    return store(output, raw, metadata, started)


def settlement_rule(url, output, *, approved_hosts, get=requests.get):
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in approved_hosts
        or parsed.query
        or parsed.username
    ):
        raise ValueError(
            "Explicit approved HTTPS rule host required; no credential-bearing URL"
        )
    output_guard(output)
    started = datetime.now(timezone.utc)
    try:
        r = get(url, timeout=30, allow_redirects=False)
    except requests.RequestException:
        raise CaptureUnavailable("Rule source network request failed") from None
    if r.status_code != 200:
        raise CaptureUnavailable(
            f"Rule source HTTP {r.status_code}; redirect/access must be reviewed"
        )
    if not r.content or len(r.content) > 5 * 1024 * 1024:
        raise ValueError("Unexpected rule document size")
    return store(
        output,
        r.content,
        {
            "source_url": url,
            "content_type": r.headers.get("Content-Type"),
            "http_date": r.headers.get("Date"),
            "etag": r.headers.get("ETag"),
            "rule_effective_date": "not inferred; owner review required",
            "quote_count": 0,
        },
        started,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--event-id")
    group.add_argument("--rules-url")
    p.add_argument("--regions", default="us,uk")
    p.add_argument("--approved-rule-host", action="append", default=[])
    a = p.parse_args()
    if a.event_id:
        result = event_odds(a.event_id, a.output, regions=a.regions)
    else:
        result = settlement_rule(
            a.rules_url, a.output, approved_hosts=a.approved_rule_host
        )
    print(json.dumps(result, indent=2))
