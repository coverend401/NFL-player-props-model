"""Per-fixture provenance and bounded full-slate event collection. No outcomes."""

import json
import os
import sqlite3
import stat
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from research_platform.engine import evaluate
from research_platform.slate import collection_plan, scope_key
from sgo_research.analysis import comparisons, normalise
from sgo_research.contracts import Unavailable, name_key, team_key, utc
from sgo_research.diagnostics import safe_diagnostic

MAX_PAGES = 2
MAX_FIXTURES = 16


def private_records(path, table, now, ttl=86400):
    p = Path(path)
    if (
        not p.exists()
        or p.is_symlink()
        or p.resolve().is_relative_to(Path(__file__).resolve().parents[1])
    ):
        return []
    try:
        info = p.stat()
    except OSError:
        return []
    if info.st_mode & (stat.S_IRWXG | stat.S_IRWXO) or info.st_uid != os.getuid():
        return []
    if table not in ["r8_catalog", "r8_audit"]:
        return []
    try:
        with closing(sqlite3.connect(str(p), timeout=5)) as c, c:
            c.execute(
                f"DELETE FROM {table} WHERE at<?",
                ((now - timedelta(hours=24)).isoformat(),),
            )
            rows = c.execute(
                f"SELECT body FROM {table} WHERE at>=? AND at<=? ORDER BY at DESC LIMIT 16",
                ((now - timedelta(seconds=ttl)).isoformat(), now.isoformat()),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]
    except (OSError, sqlite3.Error, ValueError):
        return []


def match_event(event, release, eligible):
    try:
        teams = event["teams"]
        away = team_key(teams["away"]["names"]["short"])
        home = team_key(teams["home"]["names"]["short"])
        matches = [
            g
            for g in eligible
            if g.split("_")[-2:] == [away, home]
            and abs(
                (
                    utc(release["game_kickoffs"][g]) - utc(event["status"]["startsAt"])
                ).total_seconds()
            )
            <= 60
        ]
        return matches[0] if len(matches) == 1 else None
    except (KeyError, TypeError, ValueError, Unavailable):
        return None


def price_merge(snapshots, now):
    """Newest event/book request supersedes old quotes; discovery never does."""
    candidates = []
    for snapshot in snapshots:
        try:
            if (
                isinstance(snapshot, dict)
                and snapshot.get("purpose") != "catalogue"
                and isinstance(snapshot.get("request_scope", {}), dict)
                and isinstance(snapshot.get("events", []), list)
                and 0 <= (now - utc(snapshot["retrieved_at"])).total_seconds() <= 900
            ):
                candidates.append(snapshot)
        except (Unavailable, KeyError, TypeError, ValueError):
            continue
    selected = {}
    for s in candidates:
        key = scope_key(s.get("request_scope", {}))
        if key not in selected or utc(s["retrieved_at"]) > utc(
            selected[key]["retrieved_at"]
        ):
            selected[key] = s
    kept = sorted(selected.values(), key=lambda s: utc(s["retrieved_at"]))[-12:]
    result = []
    for s in kept:
        events = []
        for event in s.get("events", []):
            removed = set()
            for n in kept:
                if utc(n["retrieved_at"]) <= utc(s["retrieved_at"]):
                    continue
                scope = n.get("request_scope", {})
                ids = set(
                    filter(
                        None,
                        (scope.get("eventIDs") or scope.get("eventID") or "").split(
                            ","
                        ),
                    )
                )
                if ids:
                    # IDs can migrate: a new response/catalogue may know an old
                    # alias that the older cached quote could not yet know.
                    for requested, aliases in n.get(
                        "requested_event_aliases", {}
                    ).items():
                        if requested in ids:
                            ids.update(aliases)
                    for newer_event in n.get("events", []):
                        names = {newer_event["eventID"]} | set(
                            newer_event.get("aliases", [])
                        )
                        if names & ids:
                            ids.update(names)
                    applies = bool(
                        ({event["eventID"]} | set(event.get("aliases", []))) & ids
                    )
                else:
                    try:
                        applies = (
                            utc(scope["startsAfter"])
                            <= utc(event["status"]["startsAt"])
                            <= utc(scope["startsBefore"])
                        )
                    except (KeyError, ValueError, Unavailable):
                        applies = False
                if applies:
                    removed.update(scope.get("bookmakerID", "").split(","))
            if removed:
                event = {
                    **event,
                    "odds": {
                        k: {
                            **o,
                            "byBookmaker": {
                                b: q
                                for b, q in o.get("byBookmaker", {}).items()
                                if b not in removed
                            },
                        }
                        for k, o in event.get("odds", {}).items()
                    },
                }
            events.append(event)
        result.append({**s, "events": events})
    return result


def plan8(slate, release, now, books):
    old = collection_plan(slate, release, now, books)
    gids = sorted(old["eligible_games"], key=lambda g: release["game_kickoffs"][g])[
        :MAX_FIXTURES
    ]
    return {
        "games": gids,
        "excluded": old["excluded"],
        "books": list(books),
        "max_pages": MAX_PAGES,
        "max_price_events": len(gids),
        "max_reserved_objects": 16 * MAX_PAGES + len(gids),
        "max_provider_http_calls": 2 * (MAX_PAGES + len(gids)),
        "max_foreground_wait_seconds": 360,
    }


def identity_players(event, slate, gid):
    rows = slate[slate.game_id.eq(gid) & slate.projection_status.eq("complete")][
        ["player_id", "player", "team"]
    ].drop_duplicates()
    ids = []
    for _, row in rows.iterrows():
        found = []
        for pid, p in event.get("players", {}).items():
            team = next(
                (
                    team_key(t.get("names", {}).get("short"))
                    for t in event["teams"].values()
                    if t.get("teamID") == p.get("teamID")
                ),
                None,
            )
            name = p.get("name") or " ".join(
                filter(None, [p.get("firstName"), p.get("lastName")])
            )
            if team == row.team and name_key(name).replace(" ", "") == name_key(
                row.player
            ).replace(" ", ""):
                found.append(pid)
        if len(found) != 1:
            return []  # no partial roster filter that silently loses players
        ids.extend(found)
    return list(dict.fromkeys(ids))


def explain_error(error, client):
    t = getattr(client, "transport", {})
    if t.get("credential_echo"):
        return (
            "CREDENTIAL_ECHO",
            "Response contained the supplied API credential; collector halted. No credential content is shown.",
        )
    if t.get("size_exceeded"):
        return (
            "RESPONSE_SIZE_LIMIT",
            f"Response exceeded unchanged 8 MiB guard ({t['response_bytes']} bytes); collector halted.",
        )
    if str(error) == "Foreground pacing budget exhausted":
        return (
            "PACING_LIMIT",
            "Bounded foreground rate-wait limit reached; no automatic retry.",
        )
    return safe_diagnostic(error)


def record_price(snapshot, gid, slate, release, now):
    events = [e for e in snapshot["events"] if match_event(e, release, [gid]) == gid]
    if not events:
        return {
            "stage": "price_event_not_returned",
            "category": "B",
            "detail": "Event discovered, but no event returned in the price response.",
        }
    local = {**snapshot, "events": events}
    quotes, _issues = normalise(local)
    if not quotes:
        return {
            "stage": "no_supported_markets",
            "category": "C",
            "detail": "Accepted event response has no available supported player-prop prices for requested books/players.",
            "supported_sides": 0,
        }
    compared, _ = comparisons(local, slate, release, now)
    rows, _ = evaluate([local], slate, release, now)
    if rows:
        return {
            "stage": "fresh_bookmaker",
            "category": "available",
            "supported_sides": len(quotes),
            "eligible_sides": len(rows),
            "detail": "Fresh paired bookmaker research available.",
        }
    matching = [
        r
        for r in compared
        if r.get("matching_confidence") not in [None, "unmatched"]
        and r.get("player_id") is not None
    ]
    if not matching:
        return {
            "stage": "matching_failed",
            "category": "D",
            "supported_sides": len(quotes),
            "detail": "Supported prices returned but fixture/player/forecast matching failed.",
            "reasons": sorted({r["comparison_status"] for r in compared})[:8],
        }
    stale = any(
        "stale" in r["comparison_status"] or "cutoff" in r["comparison_status"]
        for r in compared
    )
    return {
        "stage": "expired" if stale else "eligibility_excluded",
        "category": "E",
        "supported_sides": len(quotes),
        "detail": "Prices stale/expired or outside cutoff."
        if stale
        else "Matched prices excluded by pairing, primary-line, forecast or settlement guards.",
        "reasons": sorted({r["comparison_status"] for r in compared})[:8],
    }


def collect8(plan, slate, release, client, existing=(), catalogue=(), progress=None):
    progress = progress or (lambda text: None)
    n = len(plan["games"])
    if (
        n > 16
        or plan["max_reserved_objects"] != 32 + n
        or plan["max_provider_http_calls"] != 2 * (2 + n)
    ):
        raise Unavailable("Invalid lifetime quota request")
    audit = {
        g: {
            "stage": "not_attempted",
            "category": "A",
            "detail": "Not attempted in this collection.",
        }
        for g in plan["games"]
    }
    snapshots = []
    discovery = []
    specs = {}
    objects = 0
    fetches = 0
    blocked = False
    complete = False
    existing = price_merge(existing, client.clock())
    priced, _ = evaluate(existing, slate, release, client.clock())
    covered = {r["game_id"] for r in priced if r.get("bookmaker") in plan["books"]}
    for gid in covered & set(plan["games"]):
        audit[gid] = {
            "stage": "fresh_bookmaker",
            "category": "available",
            "detail": "Permitted fresh cached prices reused.",
        }
    wanted = [g for g in plan["games"] if g not in covered]
    for s in catalogue:
        if not 0 <= (client.clock() - utc(s["retrieved_at"])).total_seconds() < 86400:
            continue
        for e in s.get("events", []):
            gid = match_event(e, release, wanted)
            if gid and gid not in specs:
                specs[gid] = {
                    "game_id": gid,
                    "kickoff": release["game_kickoffs"][gid],
                    "eventID": e["eventID"],
                    "players": e.get("players", {}),
                    "event": e,
                    "catalogue_at": s["retrieved_at"],
                }
    if wanted and any(g not in specs for g in wanted):
        start = min(utc(release["game_kickoffs"][g]) for g in wanted).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = min(
            max(utc(release["game_kickoffs"][g]) for g in wanted) + timedelta(hours=6),
            start + timedelta(days=8),
            client.clock() + timedelta(days=8),
        )
        cursor = None
        seen_cursors = set()
        seen_ids = set()
        for page in range(2):
            try:
                progress(
                    f"Discovering NFL events, page {page + 1}/2 (small moneyline-shaped response)."
                )
                fetches += 1
                objects += (
                    16  # conservative exposure, including failed reservations/responses
                )
                snap = client.discover(
                    start.isoformat(), end.isoformat(), plan["books"], cursor=cursor
                )
                if snap.get("cache_hit"):
                    objects -= 16
                discovery.append(snap)
                previous = len(seen_ids)
                for e in snap["events"]:
                    seen_ids.add(e["eventID"])
                    gid = match_event(e, release, wanted)
                    if gid:
                        specs[gid] = {
                            "game_id": gid,
                            "kickoff": release["game_kickoffs"][gid],
                            "eventID": e["eventID"],
                            "players": e.get("players", {}),
                            "event": e,
                            "catalogue_at": snap["retrieved_at"],
                        }
                if all(g in specs for g in wanted):
                    complete = True
                    break
                cursor = snap.get("next_cursor")
                if not cursor:
                    complete = True
                    break
                if cursor in seen_cursors or len(seen_ids) == previous:
                    break
                seen_cursors.add(cursor)
            except (
                Unavailable,
                OSError,
                ValueError,
                TypeError,
                KeyError,
                sqlite3.Error,
            ) as error:
                code, message = explain_error(error, client)
                blocked = True
                for g in wanted:
                    audit[g] = {
                        "stage": "collection_blocked",
                        "category": "A",
                        "code": code,
                        "detail": message,
                        "transport": getattr(client, "transport", {}),
                    }
                break
    if blocked:
        return {
            "snapshots": snapshots,
            "catalogue": discovery,
            "audit": audit,
            "fetches": fetches,
            "reserved_upper_used": objects,
        }
    for g in wanted:
        if g not in specs:
            audit[g] = {
                "stage": "no_event_returned" if complete else "discovery_limited",
                "category": "B" if complete else "A",
                "detail": "No provider event matched the wider UTC discovery window."
                if complete
                else "Discovery page cap/cursor stopped before this fixture was found; provider absence is unverified.",
            }
    pending = [specs[g] for g in wanted if g in specs]
    for offset in range(0, len(pending), 2):
        batch = []
        for spec in pending[offset : offset + 2]:
            if utc(spec["kickoff"]) > client.clock() + timedelta(minutes=60):
                batch.append(spec)
            else:
                audit[spec["game_id"]] = {
                    "stage": "outside_window",
                    "category": "E",
                    "detail": "Fixture crossed T−60 before its request; not requested.",
                }
        if not batch:
            continue
        ids = []
        for s in batch:
            found = identity_players(s["event"], slate, s["game_id"])
            if not found:
                ids = []
                break
            ids.extend(found)
        try:
            progress(
                "Fetching bounded event-ID player prices: "
                + ", ".join(s["game_id"] for s in batch)
            )
            fetches += 1
            objects += len(batch)
            snap = client.prices(batch, plan["books"], player_ids=ids)
            if snap.get("cache_hit"):
                objects -= len(batch)
            snapshots.append(snap)
            for s in batch:
                audit[s["game_id"]] = {
                    **record_price(snap, s["game_id"], slate, release, client.clock()),
                    "at": snap["retrieved_at"],
                    "response_bytes": snap.get("transport", {}).get("response_bytes"),
                }
        except (
            Unavailable,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            sqlite3.Error,
        ) as error:
            code, message = explain_error(error, client)
            for s in batch:
                audit[s["game_id"]] = {
                    "stage": "response_rejected"
                    if code in ["RESPONSE_SIZE_LIMIT", "CREDENTIAL_ECHO"]
                    else "collection_blocked",
                    "category": "E",
                    "code": code,
                    "detail": message,
                    "transport": getattr(client, "transport", {}),
                }
            for s in pending[offset + 2 :]:
                audit[s["game_id"]] = {
                    "stage": "not_attempted_after_block",
                    "category": "A",
                    "detail": "No new requests after the earlier collection failure.",
                }
            break
    return {
        "snapshots": snapshots,
        "catalogue": discovery,
        "audit": audit,
        "fetches": fetches,
        "reserved_upper_used": objects,
    }


def write_audit(client, result, release_id):
    payload = {
        "at": client.clock().isoformat(),
        "release_id": release_id,
        "audit": result["audit"],
        "fetches": result["fetches"],
    }
    with client.store.cache.connection() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS r8_audit(key TEXT PRIMARY KEY,at TEXT NOT NULL,body TEXT NOT NULL)"
        )
        c.execute(
            "DELETE FROM r8_audit WHERE at<?",
            ((client.clock() - timedelta(hours=24)).isoformat(),),
        )
        c.execute(
            "INSERT OR REPLACE INTO r8_audit VALUES (?,?,?)",
            ("latest", payload["at"], json.dumps(payload)),
        )


def state8(rows, models, snapshots, audit, plan, release, now):
    result = {}
    for gid in plan["games"]:
        r = [r for r in rows if r["game_id"] == gid]
        m = [m for m in models if m["game_id"] == gid]
        previous = audit.get(gid, {})
        if r:
            stage = "fresh_bookmaker"
            label = "Fresh bookmaker-backed research available"
        elif not m:
            stage = "no_forecast"
            label = "No usable complete forecasts"
        else:
            stage = previous.get("stage", "not_attempted")
            label = {
                "no_supported_markets": "No supported player markets in accepted response",
                "no_event_returned": "No provider event returned",
                "matching_failed": "Matching failed — model-only research",
                "expired": "Prices stale or expired",
                "eligibility_excluded": "Price/forecast guards excluded comparisons",
                "response_rejected": "Response rejected by safety guard",
                "collection_blocked": "Quota/authentication/safety blocked collection",
                "not_attempted_after_block": "Quota-limited or not attempted after failure",
                "discovery_limited": "Event discovery partial — provider coverage unverified",
                "price_event_not_returned": "Event discovered; no price event returned",
                "not_attempted": "Quota-limited or not attempted",
                "outside_window": "Fixture outside permitted collection window",
            }.get(stage, "Model-only research available")
            for snapshot in snapshots:
                if any(
                    match_event(e, release, [gid]) == gid
                    for e in snapshot.get("events", [])
                ):
                    # Actual eligibility diagnostics are computed during collection;
                    # view-time provider staleness can be detected without an API call.
                    try:
                        q, _ = normalise(snapshot)
                        if q and any(
                            (now - utc(x["provider_updated_at"])).total_seconds() > 900
                            for x in q
                            if match_event(
                                {
                                    "teams": x["provider_teams"],
                                    "status": {"startsAt": x["kickoff_at"]},
                                },
                                release,
                                [gid],
                            )
                            == gid
                        ):
                            stage = "expired"
                            label = "Prices stale or expired"
                    except (Unavailable, KeyError, ValueError, TypeError):
                        pass
            if previous.get("stage") == "fresh_bookmaker" and not any(
                any(match_event(e, release, [gid]) == gid for e in s.get("events", []))
                for s in snapshots
            ):
                stage = "cache_unavailable"
                label = "Previously matched capture is no longer in permitted cache"
        result[gid] = {
            "stage": stage,
            "label": label,
            "model_only": bool(m) and not bool(r),
            "bookmaker": bool(r),
            "models": len(m),
            "detail": "Fresh paired bookmaker research currently available."
            if r
            else previous.get(
                "detail",
                "No collection evidence for this fixture; provider absence is not established.",
            ),
            "category": "available"
            if r
            else "E"
            if stage == "expired"
            else "F"
            if stage == "cache_unavailable"
            else previous.get("category", "A"),
        }
    return result


def two8(rows, models, release):
    answer = {}
    for gid in release["game_kickoffs"]:
        priced = sorted(
            [r for r in rows if r["game_id"] == gid and r.get("ev_pct") is not None],
            key=lambda r: (r["classification"] == "WATCH", r["ev_pct"]),
            reverse=True,
        )
        picks = []
        seen = set()
        for r in priced:
            if r["player_id"] in seen:
                continue
            picks.append(r)
            seen.add(r["player_id"])
            if len(picks) == 2:
                break
        if not picks:
            for r in models:
                if r["game_id"] == gid and r["player_id"] not in seen:
                    picks.append(r)
                    seen.add(r["player_id"])
                    if len(picks) == 2:
                        break
        answer[gid] = picks
    return answer
