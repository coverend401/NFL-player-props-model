"""Read-only, header-authenticated, free-only API access. No background polling."""

import hashlib
import json
from datetime import UTC, datetime

import requests

from .contracts import FREE_BOOKS, Unavailable, account_limits, utc

BASE = "https://api.sportsgameodds.com/v2"


def redact_events(events, now):
    clean = []
    for event in events:
        if not isinstance(event, dict) or any(
            not isinstance(event.get(k, {}), dict)
            for k in ["status", "info", "players", "teams", "odds"]
        ):
            raise Unavailable("Unexpected event schema")
        if any(not isinstance(p, dict) for p in event.get("players", {}).values()):
            raise Unavailable("Unexpected player schema")
        if any(
            not isinstance(t, dict) or not isinstance(t.get("names", {}), dict)
            for t in event.get("teams", {}).values()
        ):
            raise Unavailable("Unexpected team schema")
        status = event.get("status", {})
        if (
            event.get("leagueID") != "NFL"
            or status.get("started") is not False
            or status.get("ended") is not False
            or status.get("delayed") is True
            or status.get("cancelled") is True
            or status.get("live") is True
            or utc(status.get("startsAt")) <= now
        ):
            raise Unavailable("Response includes non-pregame NFL event; discarded")
        if event.get("results"):
            raise Unavailable("Unexpected result payload; discarded without analysis")
        item = {k: event.get(k) for k in ["eventID", "leagueID", "sportID"]}
        item["info"] = {"seasonWeek": event.get("info", {}).get("seasonWeek")}
        item["players"] = {
            pid: {
                k: p.get(k)
                for k in ["playerID", "name", "firstName", "lastName", "teamID"]
            }
            for pid, p in event.get("players", {}).items()
        }
        item["status"] = {
            k: status.get(k)
            for k in ["startsAt", "started", "ended", "live", "cancelled", "delayed"]
        }
        item["teams"] = {
            side: {
                k: v
                for k, v in event.get("teams", {}).get(side, {}).items()
                if k in ["teamID", "names"]
            }
            for side in ["home", "away"]
        }
        item["odds"] = {}
        for odd_id, odd in event.get("odds", {}).items():
            if (
                not isinstance(odd, dict)
                or not isinstance(odd.get("byBookmaker", {}), dict)
                or any(
                    not isinstance(q, dict) for q in odd.get("byBookmaker", {}).values()
                )
            ):
                raise Unavailable("Unexpected bookmaker odds schema")
            item["odds"][odd_id] = {
                k: odd.get(k)
                for k in [
                    "oddID",
                    "statID",
                    "statEntityID",
                    "playerID",
                    "periodID",
                    "betTypeID",
                    "sideID",
                    "started",
                    "ended",
                ]
            }
            item["odds"][odd_id]["byBookmaker"] = {
                book: {
                    k: q.get(k)
                    for k in [
                        "bookmakerID",
                        "odds",
                        "overUnder",
                        "available",
                        "isMainLine",
                        "lastUpdatedAt",
                    ]
                }
                for book, q in odd.get("byBookmaker", {}).items()
            }
        clean.append(item)
    return clean


class Client:
    def __init__(
        self, key, store, *, terms_ack=False, get=None, clock=None, object_cap=2000
    ):
        self.key = key
        self.store = store
        self.terms_ack = terms_ack
        self.get = get or requests.get
        if type(object_cap) is not int or not 1 <= object_cap <= 2000:
            raise Unavailable("Object cap must be an integer from 1 to 2000")
        self.object_cap = object_cap
        self.clock = clock or (lambda: datetime.now(UTC))

    def _request(self, path, params=None):
        if (
            not isinstance(self.key, str)
            or len(self.key.strip()) < 12
            or not all(33 <= ord(c) <= 126 for c in self.key.strip())
        ):
            raise Unavailable("Research API key missing/invalid; no request made")
        if not self.terms_ack:
            raise Unavailable("Private research data-use/cache terms not acknowledged")
        self.store.http_slot(self.clock())
        try:
            r = self.get(
                BASE + path,
                headers={"x-api-key": self.key.strip(), "Accept": "application/json"},
                params=params,
                timeout=(5, 25),
                allow_redirects=False,
            )
        except (requests.RequestException, ValueError, UnicodeError):
            raise Unavailable("Provider network request failed; no retries") from None
        received = self.clock()
        if r.status_code != 200:
            if r.status_code in [401, 403, 429]:
                self.store.halt("authentication_entitlement_or_quota")
            raise Unavailable(
                f"Provider HTTP {r.status_code}; no retry or paid fallback"
            )
        if len(r.content) > 8 * 1024 * 1024 or self.key.strip().encode() in r.content:
            self.store.halt("unsafe_response")
            raise Unavailable("Unsafe response size/content discarded")
        try:
            body = json.loads(r.content)
        except (ValueError, UnicodeError):
            raise Unavailable("Invalid provider JSON") from None
        if not isinstance(body, dict) or body.get("success") is False:
            raise Unavailable("Unexpected provider envelope")
        return body, received, hashlib.sha256(r.content).hexdigest()

    def fetch(
        self, starts_after, starts_before, *, books=("williamhill", "unibet"), limit=16
    ):
        after, before = utc(starts_after), utc(starts_before)
        now = self.clock()
        if (
            after < now
            or before <= after
            or (before - after).total_seconds() > 8 * 86400
            or type(limit) is not int
            or not 1 <= limit <= 16
        ):
            raise Unavailable("Only a bounded upcoming NFL window is allowed")
        if not books or not set(books) <= set(FREE_BOOKS):
            raise Unavailable("Bookmaker not on documented Amateur whitelist")
        params = {
            "leagueID": "NFL",
            "startsAfter": after.isoformat(),
            "startsBefore": before.isoformat(),
            "started": "false",
            "ended": "false",
            "live": "false",
            "oddsAvailable": "true",
            "bookmakerID": ",".join(sorted(books)),
            "includeAltLines": "false",
            "includeOpenCloseOdds": "false",
            "includeOpposingOdds": "true",
            "limit": limit,
        }
        cache_key = hashlib.sha256(
            json.dumps(params, sort_keys=True).encode()
        ).hexdigest()
        cached = self.store.cached(cache_key, now)
        if cached is not None:
            return {**cached, "cache_hit": True}
        usage, _, _ = self._request("/account/usage")
        limits = account_limits(usage)
        self.store.reserve(limits, limit, now, cap=self.object_cap)
        body, received, raw_hash = self._request("/events", params)
        events = body.get("data")
        if not isinstance(events, list) or len(events) > limit:
            self.store.halt("response_exceeded_reserved_limit")
            raise Unavailable("Response exceeded reserved event-object limit")
        clean = redact_events(events, received)
        for event in clean:
            if not after <= utc(event["status"]["startsAt"]) <= before:
                raise Unavailable(
                    "Provider returned an event outside the requested window"
                )
        result = {
            "events": clean,
            "retrieved_at": received.isoformat(),
            "request_scope": params,
            "raw_sha256": raw_hash,
            "cache_hit": False,
            "truncated": bool(body.get("nextCursor")),
            "provider_notice_present": bool(body.get("notice")),
            "provider_notice": body.get("notice")
            if isinstance(body.get("notice"), str)
            else "",
            "account_tier": "Amateur",
            "usage": limits,
            "authenticated_response": True,
            "live_uk_coverage_verified": False,
        }
        # Only the sanitised pregame subset is retained privately, not result,
        # account or entire raw-provider dumps. No automatic pagination.
        self.store.save_cache(cache_key, result, received)
        return result
