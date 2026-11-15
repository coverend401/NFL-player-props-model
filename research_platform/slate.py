"""Bounded slate capture and private short-lived cache; no new infrastructure."""

import hashlib
import json
import math
import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from sgo_research.client import Client, redact_events
from sgo_research.contracts import Unavailable, team_key, utc
from sgo_research.diagnostics import safe_diagnostic
from sgo_research.market import US_BOOKS

MAX_NEW_WINDOWS = 3  # two SGO calls/window; no waits, retries or automatic pagination
WINDOW_LIMIT = 16
ROOT = Path(__file__).resolve().parents[1]


def cached_snapshots(now, path=None):
    """No network or quota-state access. Reuse only the existing private cache."""
    raw = Path(
        path
        or os.environ.get("SGO_RESEARCH_STORE")
        or (Path(tempfile.gettempdir()) / "nfl-research-odds-cache.sqlite")
    ).expanduser()
    try:
        if not raw.exists() or raw.is_symlink():
            return []
        resolved = raw.resolve()
        if ROOT == resolved or ROOT in resolved.parents:
            return []
        info = resolved.stat()
    except OSError:
        return []
    if info.st_mode & (stat.S_IRWXG | stat.S_IRWXO) or info.st_uid != os.getuid():
        return []
    result = []
    try:
        with (
            closing(sqlite3.connect(str(resolved), timeout=5)) as connection,
            connection,
        ):
            # Cache cleanup only: never alter calls, reservations, controls or papers.
            connection.execute(
                "DELETE FROM cache WHERE at<?",
                ((now - timedelta(hours=24)).isoformat(),),
            )
            records = connection.execute(
                "SELECT body FROM cache WHERE at>=? AND at<=? ORDER BY at DESC LIMIT 12",
                ((now - timedelta(seconds=600)).isoformat(), now.isoformat()),
            ).fetchall()
        for (body,) in records:
            try:
                snapshot = json.loads(body)
                age = (now - utc(snapshot["retrieved_at"])).total_seconds()
                if (
                    snapshot.get("authenticated_response") is not True
                    or snapshot.get("account_tier") != "Amateur"
                    or not 0 <= age < 600
                ):
                    continue
                scope = snapshot.get("request_scope", {})
                if (
                    scope.get("leagueID") != "NFL"
                    or scope.get("includeAltLines") != "false"
                ):
                    continue
                events = redact_events(snapshot["events"], now)
                result.append({**snapshot, "events": events, "cache_hit": True})
            except (KeyError, TypeError, ValueError, Unavailable):
                continue
    except (OSError, sqlite3.Error):
        return []
    return result


def scope_for(kickoff, books):
    k = utc(kickoff)
    return {
        "leagueID": "NFL",
        "startsAfter": (k - timedelta(seconds=30)).isoformat(),
        "startsBefore": (k + timedelta(seconds=30)).isoformat(),
        "started": "false",
        "ended": "false",
        "live": "false",
        "oddsAvailable": "true",
        "bookmakerID": ",".join(sorted(books)),
        "includeAltLines": "false",
        "includeOpenCloseOdds": "false",
        "includeOpposingOdds": "true",
        "limit": WINDOW_LIMIT,
    }


def scope_key(scope):
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()


def merge_snapshots(existing, incoming, now):
    selected = {}
    expired = []
    for snapshot in [*existing, *incoming]:
        try:
            age = (now - utc(snapshot["retrieved_at"])).total_seconds()
            if not 0 <= age <= 900:
                expired.append(snapshot["retrieved_at"])
                continue
            key = scope_key(snapshot.get("request_scope", {}))
            if key not in selected or utc(snapshot["retrieved_at"]) > utc(
                selected[key]["retrieved_at"]
            ):
                selected[key] = snapshot
        except (KeyError, TypeError, ValueError):
            continue
    kept = sorted(selected.values(), key=lambda s: utc(s["retrieved_at"]))[-6:]
    current = []
    for snapshot in kept:
        events = []
        for event in snapshot.get("events", []):
            superseded = set()
            for newer in kept:
                if utc(newer["retrieved_at"]) <= utc(snapshot["retrieved_at"]):
                    continue
                scope = newer.get("request_scope", {})
                try:
                    if scope.get("leagueID") == "NFL" and utc(
                        scope["startsAfter"]
                    ) <= utc(event["status"]["startsAt"]) <= utc(scope["startsBefore"]):
                        superseded.update(scope.get("bookmakerID", "").split(","))
                except (KeyError, ValueError, TypeError):
                    continue
            if superseded:
                # Pure in-memory subset. Never rewrite captured source data or times.
                event = {
                    **event,
                    "odds": {
                        key: {
                            **odd,
                            "byBookmaker": {
                                book: q
                                for book, q in odd.get("byBookmaker", {}).items()
                                if book not in superseded
                            },
                        }
                        for key, odd in event.get("odds", {}).items()
                    },
                }
            events.append(event)
        current.append({**snapshot, "events": events})
    return current, sorted(set(expired))


def collection_plan(slate, release, now, books=US_BOOKS):
    if not books or not set(books) <= set(US_BOOKS):
        raise Unavailable("Bookmaker not on documented Amateur whitelist")
    complete = set(slate.loc[slate.projection_status.eq("complete"), "game_id"])
    known = set(slate.game_id)
    groups = {}
    excluded = {}
    for gid, kickoff in release["game_kickoffs"].items():
        if gid not in known:
            continue
        k = utc(kickoff)
        if k <= now + timedelta(minutes=60):
            excluded[gid] = "T−60 window closed"
            continue
        if k > now + timedelta(days=8):
            excluded[gid] = "Beyond bounded 8-day horizon"
            continue
        if gid not in complete:
            excluded[gid] = "No complete Stage 1A forecast"
            continue
        groups.setdefault(k.isoformat(), []).append(gid)
    windows = [
        {"kickoff": k, "games": sorted(gids), "scope": scope_for(k, books)}
        for k, gids in groups.items()
    ]
    windows.sort(key=lambda w: w["kickoff"])
    # Earliest deadline first, then largest fixture coverage, then chronological.
    if windows:
        windows = [windows[0]] + sorted(
            windows[1:], key=lambda w: (-len(w["games"]), w["kickoff"])
        )
    bound = min(MAX_NEW_WINDOWS, len(windows))
    return {
        "windows": windows,
        "eligible_games": sorted(g for w in windows for g in w["games"]),
        "excluded": excluded,
        "max_new_windows": bound,
        "max_reserved_objects": bound * WINDOW_LIMIT,
        "max_provider_http_calls": bound * 2,
        "books": list(books),
    }


def execute_plan(plan, client, now, cache=()):
    """One explicit action; bounded attempts, stop new requests after any failure."""
    if (
        len(plan["windows"]) > 32
        or plan["max_new_windows"] != min(MAX_NEW_WINDOWS, len(plan["windows"]))
        or plan["max_provider_http_calls"]
        != 2 * min(MAX_NEW_WINDOWS, len(plan["windows"]))
        or not plan["books"]
        or not set(plan["books"]) <= set(US_BOOKS)
        or plan["max_reserved_objects"]
        != min(MAX_NEW_WINDOWS, len(plan["windows"])) * WINDOW_LIMIT
    ):
        raise Unavailable("Invalid lifetime quota request")
    snapshots = []
    statuses = []
    attempts = 0
    blocked = False
    for window in plan["windows"]:
        # Revalidate cutoff during collection; never use the click-time clock alone.
        current = client.clock()
        if utc(window["kickoff"]) <= current + timedelta(minutes=60):
            statuses.append({"games": window["games"], "status": "cutoff_closed"})
            continue
        scope = window["scope"]
        if scope != scope_for(window["kickoff"], plan["books"]):
            raise Unavailable("Invalid lifetime quota request")
        found = next(
            (
                s
                for s in cache
                if s.get("request_scope") == scope
                and 0 <= (current - utc(s["retrieved_at"])).total_seconds() < 600
            ),
            None,
        )
        if found:
            snapshots.append(found)
            statuses.append({"games": window["games"], "status": "cached"})
            continue
        if blocked or attempts >= min(MAX_NEW_WINDOWS, len(plan["windows"])):
            statuses.append(
                {"games": window["games"], "status": "not_requested_bounded_partial"}
            )
            continue
        attempts += 1
        try:
            snap = client.fetch(
                scope["startsAfter"],
                scope["startsBefore"],
                books=plan["books"],
                limit=WINDOW_LIMIT,
            )
            snapshots.append(snap)
            statuses.append(
                {
                    "games": window["games"],
                    "status": "cached" if snap.get("cache_hit") else "retrieved",
                    "continuation": bool(snap.get("truncated")),
                }
            )
        except (
            Unavailable,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            sqlite3.Error,
        ) as error:
            code, message = (
                (
                    "CACHE_STORAGE",
                    "Private research cache failed; reservations are not refunded. No automatic retry; forecasts remain available.",
                )
                if isinstance(error, sqlite3.Error)
                else safe_diagnostic(error)
            )
            statuses.append(
                {
                    "games": window["games"],
                    "status": "blocked",
                    "code": code,
                    "message": message,
                }
            )
            blocked = True
    return {
        "snapshots": snapshots,
        "statuses": statuses,
        "max_objects_exposed": attempts * WINDOW_LIMIT,
        "new_attempts": attempts,
    }


def coverage(rows, release, plan, snapshots):
    seen = set()
    for s in snapshots:
        for event in s.get("events", []):
            teams = event.get("teams", {})
            away = team_key(teams.get("away", {}).get("names", {}).get("short"))
            home = team_key(teams.get("home", {}).get("names", {}).get("short"))
            for gid in plan["eligible_games"]:
                if (
                    gid.split("_")[-2:] == [away, home]
                    and abs(
                        (
                            utc(release["game_kickoffs"][gid])
                            - utc(event["status"]["startsAt"])
                        ).total_seconds()
                    )
                    <= 60
                ):
                    seen.add(gid)
    priced = {r["game_id"] for r in rows}
    missing = {
        g: (
            "Event returned, but no eligible paired prices / matched complete forecast"
            if g in seen
            else "No event/price captured in current bounded windows"
        )
        for g in plan["eligible_games"]
        if g not in priced
    }
    return {
        "eligible": len(plan["eligible_games"]),
        "priced": len(priced & set(plan["eligible_games"])),
        "missing": missing,
        "seen": seen,
    }


def unique_watch(rows, *, distinct_players=False):
    result = []
    seen = set()
    people = set()
    for row in sorted(
        (r for r in rows if r["classification"] == "WATCH"),
        key=lambda r: r["ev_pct"],
        reverse=True,
    ):
        key = (row["game_id"], row["player_id"], row["market"], row["side"])
        if key in seen or (
            distinct_players and (row["game_id"], row["player_id"]) in people
        ):
            continue
        seen.add(key)
        people.add((row["game_id"], row["player_id"]))
        result.append(row)
    return result


def model_candidates(slate, release, now):
    frame = slate.copy()
    good = []
    for _, r in frame.iterrows():
        try:
            good.append(
                r.projection_status == "complete"
                and r.release_id == release["release_id"]
                and utc(r.prediction_at)
                <= now
                < utc(release["game_kickoffs"][r.game_id]) - timedelta(minutes=60)
                and math.isfinite(float(r.projection))
                and r.projection >= 0
            )
        except (ValueError, KeyError, TypeError):
            good.append(False)
    frame = frame[good].copy()
    if frame.empty:
        return []
    frame["production_rank"] = (
        frame.groupby("market")
        .projection.rank(method="min", ascending=False)
        .astype(int)
    )
    frame["market_population"] = frame.groupby("market").projection.transform("count")
    frame["rank_fraction"] = frame.production_rank / frame.market_population
    frame = frame.sort_values(["rank_fraction", "player", "market"])
    return [
        {
            **r.to_dict(),
            "classification": "MODEL ONLY",
            "model_probability": None,
            "ev_pct": None,
            "decimal_odds": None,
            "side": None,
            "line": None,
            "bookmaker": None,
        }
        for _, r in frame.iterrows()
    ]


def top_two(rows, models, release):
    result = {}
    for gid in release["game_kickoffs"]:
        priced = [r for r in rows if r["game_id"] == gid]
        picks = unique_watch(priced, distinct_players=True)[:2]
        if not priced:
            seen = set()
            for r in models:
                if r["game_id"] == gid and r["player_id"] not in seen:
                    picks.append(r)
                    seen.add(r["player_id"])
                    if len(picks) == 2:
                        break
        result[gid] = picks
    return result


def parlay_research(legs, now, allow_same_game=False):
    warnings = [
        "No validated joint probability. Different games do not establish independence.",
        "No bookmaker combined quote supplied: restrictions, SGP repricing and boosts are unknown.",
    ]
    result = {
        "quoted_combined_odds": None,
        "joint_probability": None,
        "ev": None,
        "leg_price_product": None,
        "warnings": warnings,
        "arithmetic_available": False,
    }
    if len(legs) < 2:
        warnings.append("Select at least two legs.")
        return result
    keys = [(r["game_id"], r["player_id"], r["market"], r.get("side")) for r in legs]
    if len(set(keys)) != len(keys):
        warnings.append("Duplicate selection blocked.")
        return result
    for i, a in enumerate(legs):
        for b in legs[i + 1 :]:
            if (a["game_id"], a["player_id"], a["market"]) == (
                b["game_id"],
                b["player_id"],
                b["market"],
            ) and a.get("side") != b.get("side"):
                warnings.append("Opposing sides of the same prop are blocked.")
                return result
    same_game = len({r["game_id"] for r in legs}) < len(legs)
    if same_game:
        warnings.append(
            "Same-game correlation is unmodelled; ordinary leg multiplication is not an offered SGP price."
        )
        if not allow_same_game:
            warnings.append(
                "Enable same-game research explicitly to inspect this combination."
            )
            return result
    if any(
        a["game_id"] == b["game_id"]
        and a.get("team")
        and a.get("team") == b.get("team")
        for i, a in enumerate(legs)
        for b in legs[i + 1 :]
    ):
        warnings.append(
            "Teammate opportunity and efficiency can be linked through shared offensive volume; this dependence is not modelled."
        )
    if len({r["player_id"] for r in legs}) < len(legs):
        warnings.append(
            "Related-player / same-player markets are correlated; no dependence model is validated."
        )
    if len({r.get("bookmaker") for r in legs}) > 1:
        warnings.append(
            "Mixed-book legs cannot be placed as one quoted bookmaker parlay."
        )
    for r in legs:
        try:
            valid = (
                r["classification"] == "WATCH"
                and r.get("model_probability") is not None
                and now < utc(r["valid_until"])
                and utc(r["retrieved_at"]) <= now
                and math.isfinite(r["decimal_odds"])
                and r["decimal_odds"] > 1
            )
        except (KeyError, ValueError, TypeError):
            valid = False
        if not valid:
            warnings.append(
                "An unpriced, unsupported, expired or non-WATCH leg blocks pricing."
            )
            return result
    product = math.prod(r["decimal_odds"] for r in legs)
    if not math.isfinite(product):
        warnings.append(
            "Arithmetic price product is outside the finite range; pricing blocked."
        )
        return result
    result["leg_price_product"] = product
    result["arithmetic_available"] = True
    return result


class LazyCollector:
    """No GitHub/provider access until an uncached window actually needs fetching."""

    def __init__(self, key, clock, cap=2000, terms_ack=False):
        self.key = key
        self.clock = clock
        self.cap = cap
        self.terms_ack = terms_ack
        self.client = None

    def fetch(self, *args, **kwargs):
        from sgo_research.config import quota_store
        from sgo_research.diagnostics import CollectionBlocked

        if not self.key:
            raise CollectionBlocked("KEY")
        if not self.terms_ack:
            raise CollectionBlocked("TERMS")
        if type(self.cap) is not int or not 1 <= self.cap <= 2000:
            raise CollectionBlocked("CONFIG_CAP")
        if self.client is None:
            self.client = Client(
                self.key,
                quota_store(),
                terms_ack=True,
                clock=self.clock,
                object_cap=self.cap,
            )
        return self.client.fetch(*args, **kwargs)
