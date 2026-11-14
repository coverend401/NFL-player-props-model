"""Deterministic fixture/player matching and EXACT existing Stage 1A pricing."""

import hashlib
import json
import math
from datetime import timedelta

from scipy.stats import norm

from .contracts import (
    FREE_BOOKS,
    STAT_MARKETS,
    Unavailable,
    name_key,
    odds_formats,
    team_key,
    utc,
)


def normalise(snapshot):
    quotes, issues = [], []
    for e in snapshot.get("events", []):
        for odd_id, o in e.get("odds", {}).items():
            if o.get("statID") not in STAT_MARKETS:
                continue
            identity = {"event_id": e.get("eventID"), "odd_id": odd_id}
            if (
                o.get("started") is True
                or o.get("ended") is True
                or o.get("periodID") != "game"
                or o.get("betTypeID") != "ou"
                or o.get("sideID") not in ["over", "under"]
                or not (o.get("playerID") or o.get("statEntityID"))
            ):
                issues.append(
                    {**identity, "reason": "unsupported_or_incomplete_market_identity"}
                )
                continue
            pid = o.get("playerID") or o.get("statEntityID")
            player = e.get("players", {}).get(pid, {})
            for book, b in o.get("byBookmaker", {}).items():
                try:
                    if book not in FREE_BOOKS:
                        raise Unavailable("bookmaker_not_on_free_whitelist")
                    if b.get("available") is not True:
                        raise Unavailable("bookmaker_quote_unavailable")
                    price, fraction = odds_formats(b.get("odds"))
                    line = float(b.get("overUnder"))
                    if not math.isfinite(line):
                        raise Unavailable("invalid_line")
                except (Unavailable, ValueError, TypeError) as error:
                    issues.append(
                        {
                            **identity,
                            "bookmaker": book,
                            "reason": str(error)
                            if isinstance(error, Unavailable)
                            else "invalid_line",
                        }
                    )
                    continue
                quotes.append(
                    {
                        **identity,
                        "bookmaker": book,
                        "provider_player_id": pid,
                        "player_name": player.get("name")
                        or " ".join(
                            filter(
                                None, [player.get("firstName"), player.get("lastName")]
                            )
                        ),
                        "provider_player_team_id": player.get("teamID"),
                        "canonical_stat": o["statID"],
                        "model_market": STAT_MARKETS[o["statID"]],
                        "side": o["sideID"].title(),
                        "line": line,
                        "raw_line": b.get("overUnder"),
                        "raw_odds": b.get("odds"),
                        "decimal_odds": price,
                        "fractional_odds": fraction,
                        "provider_updated_at": b.get("lastUpdatedAt"),
                        "retrieved_at": snapshot.get("retrieved_at"),
                        "main_line": b.get("isMainLine"),
                        "kickoff_at": e["status"]["startsAt"],
                        "provider_teams": e.get("teams", {}),
                        "raw_sha256": snapshot.get("raw_sha256"),
                        "authenticated_response": snapshot.get(
                            "authenticated_response", False
                        ),
                    }
                )
    # Ambiguous duplicates are rejected, never pick the best apparent price.
    keys = {}
    for q in quotes:
        key = tuple(
            q[k]
            for k in [
                "event_id",
                "bookmaker",
                "provider_player_id",
                "model_market",
                "side",
                "line",
            ]
        )
        keys[key] = keys.get(key, 0) + 1
    clean = []
    for q in quotes:
        key = tuple(
            q[k]
            for k in [
                "event_id",
                "bookmaker",
                "provider_player_id",
                "model_market",
                "side",
                "line",
            ]
        )
        if keys[key] > 1:
            issues.append(
                {"event_id": q["event_id"], "reason": "ambiguous_duplicate_quote"}
            )
        else:
            clean.append(q)
    return clean, issues


def comparisons(
    snapshot, slate, release, now, *, player_map=None, book_evidence=None, max_age=900
):
    player_map = player_map or {}
    book_evidence = book_evidence or {}
    quotes, issues = normalise(snapshot)
    rows = []
    kickoffs = release.get("game_kickoffs", {}) if release else {}
    for q in quotes:
        row = {
            **q,
            "comparison_status": "unmatched",
            "eligible": False,
            "matching_confidence": "unmatched",
            "projection": None,
            "model_probability": None,
            "implied_probability": 1 / q["decimal_odds"],
            "ev_pct": None,
            "release_id": release.get("release_id") if release else None,
        }
        reasons = []
        try:
            kickoff, retrieved = utc(q["kickoff_at"]), utc(q["retrieved_at"])
            if retrieved > now or kickoff <= now:
                raise Unavailable("started_or_future_capture")
            updated = utc(q["provider_updated_at"])
            age = (now - updated).total_seconds()
            row["age_seconds"] = age
            if updated > retrieved:
                reasons.append("future_provider_timestamp")
            if age < 0 or age > max_age or (now - retrieved).total_seconds() > max_age:
                reasons.append("stale_odds")
        except Unavailable as error:
            row["comparison_status"] = str(error)
            rows.append(row)
            continue
        teams = q["provider_teams"]
        away = team_key(teams.get("away", {}).get("names", {}).get("short"))
        home = team_key(teams.get("home", {}).get("names", {}).get("short"))
        game_ids = []
        for gid, time in kickoffs.items():
            parts = gid.split("_")
            if (
                len(parts) == 4
                and parts[-2:] == [away, home]
                and abs((utc(time) - kickoff).total_seconds()) <= 60
            ):
                game_ids.append(gid)
        if len(game_ids) != 1:
            row["comparison_status"] = "fixture_unmatched"
            rows.append(row)
            continue
        gid = game_ids[0]
        row["game_id"] = gid
        candidates = slate[slate.game_id.eq(gid)].copy()
        team_by_id = {
            v.get("teamID"): team_key(v.get("names", {}).get("short"))
            for v in teams.values()
        }
        tm = team_by_id.get(q["provider_player_team_id"])
        if tm not in [home, away]:
            row["comparison_status"] = "player_team_unverified"
            rows.append(row)
            continue
        candidates = candidates[candidates.team.eq(tm)]
        mapped = player_map.get(q["provider_player_id"])
        if mapped:
            candidates = candidates[candidates.player_id.eq(mapped)]
            confidence = "verified_id_mapping"
        else:
            candidates = candidates[
                candidates.player.map(name_key).eq(name_key(q["player_name"]))
            ]
            confidence = "exact_unique_name_team_fixture"
        market = q["model_market"]
        if market in ["Rushing Yards", "Rushing Attempts"]:
            positions = set(candidates.position)
            if positions == {"QB"}:
                market = "QB " + market
        candidates = candidates[candidates.market.eq(market)]
        if len(candidates) != 1:
            row["comparison_status"] = "player_or_market_ambiguous_or_unmatched"
            rows.append(row)
            continue
        f = candidates.iloc[0]
        row.update(
            player=f.player,
            player_id=f.player_id,
            team=tm,
            model_market=market,
            matching_confidence=confidence,
        )
        try:
            prediction = utc(f.prediction_at)
            if f.get("release_id") != row["release_id"]:
                raise Unavailable("forecast_release_mismatch")
            if prediction > now or (retrieved and prediction > retrieved):
                raise Unavailable("forecast_not_available_at_quote_time")
            if f.get("projection_status") != "complete":
                raise Unavailable("forecast_scenario_only")
            mu, sigma = float(f.projection), float(f.resid_std)
            if not math.isfinite(mu) or not math.isfinite(sigma) or sigma <= 0:
                raise Unavailable("invalid_forecast_scale")
            p_over = float(1 - norm.cdf(q["line"], mu, sigma))
            probability = p_over if q["side"] == "Over" else 1 - p_over
            row.update(
                projection=mu,
                resid_std=sigma,
                model_probability=probability,
                forecast_at=f.prediction_at,
                fair_decimal_odds=(1 / probability if probability > 0 else None),
                pricing_method="stage1a_unchanged_normal_cdf_at_actual_line",
            )
            halfline = (
                abs(q["line"] * 2 - round(q["line"] * 2)) < 1e-9
                and abs(q["line"] - round(q["line"])) > 1e-9
            )
            if (
                q["canonical_stat"]
                in [
                    "passing_attempts",
                    "passing_completions",
                    "rushing_attempts",
                    "receiving_receptions",
                ]
                and q["line"] < 0
            ):
                halfline = False
            if not halfline:
                reasons.append("integer_or_quarter_line_push_unsupported")
            else:
                row["ev_pct"] = 100 * (probability * q["decimal_odds"] - 1)
        except (Unavailable, ValueError, TypeError) as error:
            reasons.append(
                str(error) if isinstance(error, Unavailable) else "invalid_forecast"
            )
        pair = [
            r
            for r in quotes
            if all(
                r[k] == q[k]
                for k in [
                    "event_id",
                    "bookmaker",
                    "provider_player_id",
                    "model_market",
                    "line",
                ]
            )
            and r["side"] != q["side"]
        ]
        if len(pair) != 1:
            reasons.append("missing_same_line_opposite_side")
        else:
            other = pair[0]
            row["over_odds"] = (
                q["decimal_odds"] if q["side"] == "Over" else other["decimal_odds"]
            )
            row["under_odds"] = (
                q["decimal_odds"] if q["side"] == "Under" else other["decimal_odds"]
            )
            try:
                t = utc(other["provider_updated_at"])
                if (now - t).total_seconds() > max_age or t > utc(
                    other["retrieved_at"]
                ):
                    reasons.append("opposite_side_stale_or_invalid")
            except Unavailable:
                reasons.append("opposite_side_timestamp_missing")
        if q["main_line"] is not True:
            reasons.append("main_line_unverified")
        evidence = book_evidence.get(q["bookmaker"], {})
        if evidence.get("jurisdiction") != "UK" or not evidence.get("evidence_ref"):
            reasons.append("UK_bookmaker_variant_unverified")
        if not evidence.get("rules_ref"):
            reasons.append("settlement_rules_unverified")
        if not q["authenticated_response"]:
            reasons.append("no_authenticated_quote_evidence")
        if now > kickoff - timedelta(minutes=60):
            reasons.append("after_T60_decision_cutoff")
        row["comparison_status"] = (
            "; ".join(dict.fromkeys(reasons))
            if reasons
            else "valid_research_comparison"
        )
        row["eligible"] = not reasons
        rows.append(row)
    return rows, issues


def paper_decision(row, now, *, selection="not_selected"):
    if selection not in ["selected", "not_selected"]:
        raise Unavailable("An explicit original paper decision is required")
    for stamp in [row.get("provider_updated_at"), row.get("retrieved_at")]:
        age = (now - utc(stamp)).total_seconds()
        if not 0 <= age <= 900:
            raise Unavailable("Paper decision requires currently fresh original quote")
    if not row.get("eligible") or now > utc(row["kickoff_at"]) - timedelta(minutes=60):
        raise Unavailable("Only eligible, pre-T60 research decisions can be frozen")
    payload = {
        k: row.get(k)
        for k in [
            "event_id",
            "game_id",
            "player_id",
            "player",
            "team",
            "bookmaker",
            "model_market",
            "side",
            "line",
            "raw_line",
            "raw_odds",
            "decimal_odds",
            "model_probability",
            "projection",
            "resid_std",
            "ev_pct",
            "forecast_at",
            "retrieved_at",
            "provider_updated_at",
            "release_id",
            "pricing_method",
            "raw_sha256",
        ]
    }
    payload.update(
        paper=True,
        paper_units=1.0,
        real_stake=0.0,
        created_at=now.isoformat(),
        selection=selection,
        status="unsettled",
        settlement_authorised=False,
    )
    payload["original_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, allow_nan=False).encode()
    ).hexdigest()
    return payload
