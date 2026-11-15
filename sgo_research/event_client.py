"""Documented event discovery and bounded event-ID prices; original guards retained."""

import hashlib
import json
import logging
import math
import sqlite3
import time
from datetime import timedelta
from urllib.parse import urlencode

from .client import Client, redact_events
from .contracts import FREE_BOOKS, Unavailable, account_limits, team_key, utc

LOG = logging.getLogger(__name__)


class EventClient(Client):
    def __init__(self, *args, sleep=time.sleep, progress=None, **kwargs):
        super().__init__(*args, **kwargs)
        original_get = self.get
        self.transport = {}
        self.waited = 0.0
        self.sleep = sleep
        self.progress = progress or (lambda message: None)

        def observed(*a, **kw):
            response = original_get(*a, **kw)
            self.transport = {
                "response_bytes": len(response.content),
                "size_exceeded": len(response.content) > 8 * 1024 * 1024,
                "credential_echo": bool(
                    self.key and self.key.strip().encode() in response.content
                ),
            }
            if self.transport["size_exceeded"] or self.transport["credential_echo"]:
                code = (
                    "RESPONSE_SIZE_LIMIT"
                    if self.transport["size_exceeded"]
                    else "CREDENTIAL_ECHO"
                )
                LOG.warning(
                    "R8 transport blocked code=%s response_bytes=%d limit_bytes=%d",
                    code,
                    len(response.content),
                    8 * 1024 * 1024,
                )
            return response

        self.get = observed

    def _request(self, path, params=None):
        self.transport = {}
        # Foreground pre-request pacing only. Never retry a failed provider request.
        if not hasattr(self.store, "_read"):
            raise Unavailable("Verified private GitHub quota required")
        while True:
            state, _ = self.store._read()
            if state.get("halt"):
                raise Unavailable("Collector halted; manual review required")
            if state.get("conditional_updates_verified") is not True:
                raise Unavailable("Private conditional-update verification required")
            now = self.clock()
            recent = sorted(
                utc(t) for t in state["calls"] if utc(t) > now - timedelta(seconds=60)
            )
            if any(t > now + timedelta(seconds=5) for t in recent):
                raise Unavailable("Quota clock is ahead; collection stopped")
            if len(recent) < 6:
                break
            wait = max(0.1, (recent[0] + timedelta(seconds=60.2) - now).total_seconds())
            if self.waited + wait > 360:
                raise Unavailable("Foreground pacing budget exhausted")
            self.progress(
                f"Rate pause: up to {math.ceil(wait)} seconds; no provider polling."
            )
            while wait > 0:
                part = min(25, wait)
                self.sleep(part)
                self.waited += part
                wait -= part
        self.transport = {}
        if any(self.clock() >= t for t in getattr(self, "decision_cutoffs", ())):
            raise Unavailable("T60 window closed during pacing; no request made")
        return super()._request(path, params)

    def catalog_cached(self, key, ttl=86400):
        try:
            with self.store.cache.connection() as c:
                c.execute(
                    "CREATE TABLE IF NOT EXISTS r8_catalog(key TEXT PRIMARY KEY,at TEXT NOT NULL,body TEXT NOT NULL)"
                )
                c.execute(
                    "DELETE FROM r8_catalog WHERE at<?",
                    ((self.clock() - timedelta(hours=24)).isoformat(),),
                )
                row = c.execute(
                    "SELECT at,body FROM r8_catalog WHERE key=?", (key,)
                ).fetchone()
            if row and 0 <= (self.clock() - utc(row[0])).total_seconds() < ttl:
                return json.loads(row[1])
        except (sqlite3.Error, ValueError, TypeError):
            return None
        return None

    def _fetch(self, params, *, purpose, expected=None):
        self.transport = {}
        self.decision_cutoffs = tuple(
            utc(s["kickoff"]) - timedelta(minutes=60) for s in (expected or ())
        )
        limit = params["limit"]
        if type(limit) is not int or not 1 <= limit <= 16:
            raise Unavailable("Invalid quota reservation")
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        cached = (
            self.catalog_cached(key)
            if purpose == "catalogue"
            else self.store.cached(key, self.clock())
        )
        if cached is not None:
            return {**cached, "cache_hit": True}
        usage, _, _ = self._request("/account/usage")
        limits = account_limits(usage, require_end=False)
        self.store.reserve(limits, limit, self.clock(), cap=self.object_cap)
        body, received, digest = self._request("/events", params)
        events = body.get("data")
        if not isinstance(events, list) or len(events) > limit:
            self.store.halt("response_exceeded_reserved_limit")
            raise Unavailable("Response exceeded reserved event-object limit")
        clean = redact_events(events, received)
        for raw, event in zip(events, clean, strict=True):
            event["aliases"] = [
                x
                for x in (raw.get("aliases") or [])
                if isinstance(x, str) and len(x) <= 256
            ]
            if expected is None:
                if (
                    not utc(params["startsAfter"])
                    <= utc(event["status"]["startsAt"])
                    <= utc(params["startsBefore"])
                ):
                    raise Unavailable("Discovery event outside requested window")
            else:
                matches = [
                    e
                    for e in expected
                    if e["eventID"] == event["eventID"]
                    or e["eventID"] in event["aliases"]
                ]
                if len(matches) != 1:
                    raise Unavailable("Unexpected event ID; response rejected")
                spec = matches[0]
                away = team_key(event["teams"]["away"]["names"]["short"])
                home = team_key(event["teams"]["home"]["names"]["short"])
                if (
                    spec["game_id"].split("_")[-2:] != [away, home]
                    or abs(
                        (
                            utc(spec["kickoff"]) - utc(event["status"]["startsAt"])
                        ).total_seconds()
                    )
                    > 60
                ):
                    raise Unavailable("Provider event identity/time mismatch")
                if received >= min(
                    utc(spec["kickoff"]), utc(event["status"]["startsAt"])
                ) - timedelta(minutes=60):
                    raise Unavailable("Event crossed T60 during retrieval")
                # Only observed catalogue identity, never statistical/participation zeros.
                for pid, person in spec.get("players", {}).items():
                    if pid not in event["players"] and any(
                        o.get("statEntityID") == pid or o.get("playerID") == pid
                        for o in event["odds"].values()
                    ):
                        event["players"][pid] = person
                        event["identity_catalogue_at"] = spec.get("catalogue_at")
            if purpose == "catalogue":
                event["odds"] = {}  # no discovery prices enter quote cache
        result = {
            "events": clean,
            "retrieved_at": received.isoformat(),
            "request_scope": params,
            "raw_sha256": digest,
            "cache_hit": False,
            "authenticated_response": True,
            "account_tier": "Amateur",
            "usage": limits,
            "purpose": purpose,
            "truncated": bool(body.get("nextCursor")),
            "next_cursor": body.get("nextCursor")
            if isinstance(body.get("nextCursor"), str)
            else None,
            "provider_notice": body.get("notice")
            if isinstance(body.get("notice"), str)
            else "",
            "transport": dict(self.transport),
        }
        if purpose == "catalogue":
            with self.store.cache.connection() as c:
                c.execute(
                    "INSERT OR REPLACE INTO r8_catalog VALUES (?,?,?)",
                    (key, received.isoformat(), json.dumps(result)),
                )
        else:
            self.store.save_cache(key, result, received)
        return result

    def discover(self, after, before, books, cursor=None):
        if not books or not set(books) <= set(FREE_BOOKS):
            raise Unavailable("Bookmaker not on documented Amateur whitelist")
        a, b = utc(after), utc(before)
        now = self.clock()
        if not now - timedelta(days=1) <= a < b <= now + timedelta(
            days=8
        ) or b - a > timedelta(days=8):
            raise Unavailable("Invalid bounded discovery window")
        params = {
            "leagueID": "NFL",
            "startsAfter": a.isoformat(),
            "startsBefore": b.isoformat(),
            "started": "false",
            "ended": "false",
            "live": "false",
            "cancelled": "false",
            "bookmakerID": ",".join(sorted(books)),
            "oddID": "points-home-game-ml-home",
            "includeOpposingOdds": "true",
            "includeAltLines": "false",
            "includeOpenCloseOdds": "false",
            "limit": 16,
        }
        if cursor:
            if not isinstance(cursor, str) or len(cursor) > 4096:
                raise Unavailable("Invalid discovery cursor")
            params["cursor"] = cursor
        return self._fetch(params, purpose="catalogue")

    def prices(self, specs, books, player_ids=()):
        if not books or not set(books) <= set(FREE_BOOKS):
            raise Unavailable("Bookmaker not on documented Amateur whitelist")
        if not 1 <= len(specs) <= 2:
            raise Unavailable("Price batch exceeds two events")
        if any(
            utc(s["kickoff"]) <= self.clock() + timedelta(minutes=60) for s in specs
        ):
            raise Unavailable("T60 window closed")
        params = {
            "leagueID": "NFL",
            "eventIDs": ",".join(s["eventID"] for s in specs),
            "startsAfter": (
                min(utc(s["kickoff"]) for s in specs) - timedelta(seconds=90)
            ).isoformat(),
            "startsBefore": (
                max(utc(s["kickoff"]) for s in specs) + timedelta(seconds=90)
            ).isoformat(),
            "started": "false",
            "ended": "false",
            "live": "false",
            "oddsAvailable": "true",
            "bookmakerID": ",".join(sorted(books)),
            "includeOpposingOdds": "true",
            "includeAltLines": "false",
            "includeOpenCloseOdds": "false",
            "limit": len(specs),
        }
        if player_ids:
            params["playerID"] = ",".join(sorted(set(player_ids)))
            if len(urlencode(params)) > 4096:
                params.pop("playerID")
        return self._fetch(params, purpose="prices", expected=specs)
