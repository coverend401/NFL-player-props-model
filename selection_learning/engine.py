"""Quote admission and transparent ranking; never derives probabilities from points."""

import hashlib
import json
import math
from datetime import UTC, datetime
from functools import lru_cache

import pandas as pd

from research_platform.enhanced_engine import price
from weekly_learning.admission import utc

VERSION = "line-selections-v1"
MAX_AGE = pd.Timedelta(minutes=30)
REQUIRED = {
    "game_id",
    "player_id",
    "market",
    "side",
    "line",
    "decimal_odds",
    "bookmaker",
    "quoted_at",
    "settlement_rule",
    "source",
}


def digest(value):
    def clean(v):
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [clean(x) for x in v]
        if isinstance(v, float) and not math.isfinite(v):
            return None
        return v

    return hashlib.sha256(
        json.dumps(clean(value), sort_keys=True, allow_nan=False, default=str).encode()
    ).hexdigest()


def finite(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


def quote_identity(row):
    """A real observed quote is not a new proposition just because it was reloaded."""
    keys = [
        "game_id",
        "player_id",
        "market",
        "side",
        "line",
        "decimal_odds",
        "bookmaker",
        "quoted_at",
        "settlement_rule",
    ]
    identity = {k: row[k] for k in keys}
    identity["bookmaker"] = identity["bookmaker"].strip().casefold()
    identity["quoted_at"] = utc(identity["quoted_at"]).isoformat()
    identity["line"], identity["decimal_odds"] = (
        float(identity["line"]),
        float(identity["decimal_odds"]),
    )
    identity["line_type"] = row.get("line_type", "unspecified")
    return digest(identity)


def admit_quote(raw, forecasts, *, now=None):
    now = utc(now or datetime.now(UTC))
    if not REQUIRED.issubset(raw):
        raise ValueError("Missing required quote columns")
    q = {key: raw[key] for key in REQUIRED}
    for key in [
        "original_odds",
        "odds_format",
        "provider_event_id",
        "provider_player_id",
        "provider_market_id",
    ]:
        if key in raw:
            if not isinstance(raw[key], str) or len(raw[key]) > 180:
                raise ValueError("Invalid provider metadata")
            q[key] = raw[key]
    q["line_type"] = raw.get("line_type", "unspecified")
    if q["line_type"] not in {"primary", "alternate", "unspecified"}:
        raise ValueError("Unknown primary/alternate line definition")
    for key in ["game_id", "player_id", "market", "bookmaker", "source"]:
        if not isinstance(q[key], str) or not 1 <= len(q[key]) <= 180:
            raise ValueError("Invalid quote identity or source")
    if (
        q["side"] not in ["over", "under"]
        or q["settlement_rule"] != "offensive_participation_full_refund_push"
    ):
        raise ValueError("Unsupported side or settlement rule")
    if not all(finite(q[k]) for k in ["line", "decimal_odds"]):
        raise ValueError("Non-finite line or price")
    q["line"], q["decimal_odds"] = float(q["line"]), float(q["decimal_odds"])
    if q["line"] < 0.5 or not 1 < q["decimal_odds"] <= 1000:
        raise ValueError("Quote outside supported line/price domain")
    if q["line"].is_integer():
        raise ValueError("Integer push propositions are excluded from selection in v1")
    quoted = utc(q["quoted_at"])
    if quoted > now or now - quoted > MAX_AGE:
        raise ValueError("Quote is future-dated or older than 30 minutes")
    matched = forecasts[
        forecasts.game_id.eq(q["game_id"])
        & forecasts.player_id.eq(q["player_id"])
        & forecasts.market.eq(q["market"])
    ]
    if len(matched) != 1:
        raise ValueError("Quote must match exactly one admitted player/fixture/market")
    row = matched.iloc[0].to_dict()
    kickoff = utc(row["kickoff_at"])
    built = utc(row["selection_built_at"])
    if not built <= quoted <= now < kickoff - pd.Timedelta(minutes=60):
        raise ValueError("Forecast/quote timing failed or T−60 cutoff closed")
    q.update(
        quoted_at=quoted.isoformat(),
        retrieved_at=now.isoformat(),
        kickoff_at=kickoff.isoformat(),
        expires_at=min(
            quoted + MAX_AGE, kickoff - pd.Timedelta(minutes=60)
        ).isoformat(),
    )
    q["quoted_at"] = quoted.isoformat()
    q["quote_identity_version"] = "observed-quote-v2"
    q["quote_id"] = quote_identity(q)
    return q, row


@lru_cache(maxsize=1)
def probability_history():
    from research_platform.enhanced_engine import EXPERIMENT

    # Filter at read time: never materialise any sealed final-period rows.
    return pd.read_parquet(
        EXPERIMENT / "probability_predictions.parquet",
        filters=[("season", "==", 2025), ("method", "==", "research_empirical")],
    )


def band_evidence(row, probability, side, *, data=None):
    if not 0.1 <= probability <= 0.9:
        return {
            "supported": False,
            "reason": "Extreme probability outside v1 supported ranking domain",
        }
    history = probability_history() if data is None else data
    d = history[
        history.market.eq(row["market"])
        & history.position.eq(row.get("position"))
        & history.hypothetical_line.ge(0.5)
        & history.season.eq(2025)
        & history.method.eq("research_empirical")
    ].copy()
    d["probability"] = d.p_over if side == "over" else 1 - d.p_over
    d["outcome"] = d.observed_over if side == "over" else 1 - d.observed_over
    low = int(min(probability, 0.899999) * 10) / 10
    d = d[d.probability.ge(low) & d.probability.lt(low + 0.1 + 1e-12)]
    # Repeated illustrative lines within a player-game are not independent samples.
    units = d.groupby(["game_id", "player_id"]).agg(
        p=("probability", "mean"), y=("outcome", "mean")
    )
    gap = float(abs(units.p.mean() - units.y.mean())) if len(units) else None
    weeks = int(d.week.nunique())
    return {
        "supported": len(units) >= 100
        and weeks >= 8
        and gap is not None
        and gap <= 0.05,
        "player_games": len(units),
        "weeks": weeks,
        "band": [low, low + 0.1],
        "band_gap": gap,
        "scope": "2025 chronological research; hypothetical lines, position-specific, previously inspected; no independent quote-selection validation",
    }


def evaluate(raw, forecasts, *, now=None, pricing=None, evidence=None):
    q, r = admit_quote(raw, forecasts, now=now)
    result = (pricing or price)(r, q["line"], q["decimal_odds"], q["side"], False)
    if result.get("unavailable"):
        return {
            **q,
            "status": "probability_unavailable",
            "reason": result["unavailable"],
        }
    p = float(result[q["side"]])
    if (
        not 0 <= p <= 1
        or not all(finite(result.get(k)) for k in ["over", "under", "push"])
        or abs(sum(result[k] for k in ["over", "under", "push"]) - 1) > 1e-8
    ):
        raise ValueError("Invalid predictive probability mass")
    # Existing research validation is conditional on participation, not injury clearance.
    band = (evidence or band_evidence)(r, p, q["side"])
    validated = (
        band["supported"]
        and p >= 0.5
        and bool(r.get("probability_supported", False))
        and r.get("probability_mode") not in ["unavailable", "original_normal"]
        and finite(r.get("calibration_gap"))
        and float(r["calibration_gap"]) <= 0.05
        and finite(r.get("diagnostic_n"))
        and float(r["diagnostic_n"]) >= 100
    )
    stable = (
        all(
            finite(r.get(k))
            for k in [
                "history_n",
                "recent_opportunities",
                "role_variability",
                "relative_width",
            ]
        )
        and r["history_n"] >= 3
        and r["recent_opportunities"] > 0
    )
    status = "WATCH" if validated and stable else "unranked_research"
    return {
        **q,
        "status": status,
        "reason": "Retrospective chronological research probability; availability unverified; not independent betting validation"
        if status == "WATCH"
        else "Insufficient probability validation or workload evidence",
        "player": r["player"],
        "position": r.get("position"),
        "team": r["team"],
        "opponent": r["opponent"],
        "projection": float(r["enhanced_projection"]),
        "baseline": float(r["baseline"]),
        "hit_probability": p,
        "implied_probability": 1 / q["decimal_odds"],
        "expected_profit_per_unit": float(result["expected_profit_per_unit"]),
        "probability_mode": r["probability_mode"],
        "calibration_gap": float(r["calibration_gap"])
        if finite(r.get("calibration_gap"))
        else None,
        "validation_n": int(r["diagnostic_n"]),
        "probability_band_evidence": band,
        "outcome_interval90": [r.get("q05"), r.get("q95")],
        "relative_width": float(r["relative_width"])
        if finite(r.get("relative_width"))
        else None,
        "role_variability": float(r["role_variability"])
        if finite(r.get("role_variability"))
        else None,
        "why_pick": r["why_pick"],
        "risk": r["principal_risk"],
        "forecast_sha256": digest(r),
        "ranking_version": VERSION,
    }


def dependency(a, b):
    if a["game_id"] != b["game_id"]:
        return "Different fixtures; cross-game independence remains unvalidated."
    if a["player_id"] == b["player_id"]:
        return "Same player: overlapping workload/statistics; material dependence."
    if a.get("team") == b.get("team"):
        return "Same offence: shared passing volume and competing touches/targets; material dependence."
    return (
        "Same game: shared pace, score and opposing game scripts; material dependence."
    )


def eligible_quotes(records, *, now=None):
    now = utc(now or datetime.now(UTC))
    # Latest superseding quote wins, including withdrawal; old valid prices never resurface.
    latest = {}
    for r in records:
        kind = r.get("line_type", "unspecified")
        k = tuple(
            r[k] for k in ["game_id", "player_id", "market", "side", "bookmaker"]
        ) + (kind, r["line"] if kind == "alternate" else None)
        if k not in latest or utc(r["retrieved_at"]) >= utc(latest[k]["retrieved_at"]):
            latest[k] = r
    eligible = [
        r
        for r in latest.values()
        if r["status"] == "WATCH"
        and utc(r["retrieved_at"]) <= now < utc(r["expires_at"])
        and now < utc(r["kickoff_at"]) - pd.Timedelta(minutes=60)
    ]
    ordered = sorted(
        eligible,
        key=lambda r: (
            -r["hit_probability"],
            r["relative_width"],
            r["role_variability"],
            -r["decimal_odds"],
            r["quote_id"],
        ),
    )
    return ordered


def rankings(records, *, now=None):
    ordered = eligible_quotes(records, now=now)
    # Alternative sides/lines/books stay available in records, never fill primary slots.
    primary, seen = [], set()
    for r in ordered:
        k = (r["game_id"], r["player_id"])
        if k not in seen:
            primary.append(r)
            seen.add(k)
    games = {}
    for r in primary:
        group = games.setdefault(r["game_id"], [])
        if len(group) < 2:
            group.append(r)
    return primary[:12], games


def ticket(legs, offered_odds=None, ticket_quote=None):
    if not legs or len({r["quote_id"] for r in legs}) != len(legs):
        raise ValueError("Select distinct frozen legs")
    groups = {}
    for r in legs:
        if not finite(r.get("hit_probability")) or not 0 <= r["hit_probability"] <= 1:
            raise ValueError("Unsupported marginal probability")
        key = (r["game_id"], r["player_id"], r["market"], r.get("forecast_sha256"))
        groups.setdefault(key, []).append(r)
    probabilities = []
    for rs in groups.values():
        overs = [r for r in rs if r["side"] == "over"]
        unders = [r for r in rs if r["side"] == "under"]
        over = max(overs, key=lambda r: r["line"]) if overs else None
        under = min(unders, key=lambda r: r["line"]) if unders else None
        if over and under:
            probabilities.append(
                0.0
                if over["line"] >= under["line"]
                else max(0.0, over["hit_probability"] + under["hit_probability"] - 1)
            )
        else:
            probabilities.append((over or under)["hit_probability"])
    exact = len(groups) == 1 and all(r.get("forecast_sha256") for r in legs)
    joint = probabilities[0] if exact else None
    ev = None
    verified_price = False
    if ticket_quote:
        quoted = utc(ticket_quote["quoted_at"])
        now = utc(datetime.now(UTC))
        books = {r["bookmaker"].strip().casefold() for r in legs}
        if (
            len(books) != 1
            or ticket_quote["bookmaker"].strip().casefold() not in books
            or not ticket_quote.get("source")
            or not ticket_quote.get("confirmed_available")
            or not quoted <= now < quoted + MAX_AGE
            or any(now >= utc(r["expires_at"]) for r in legs)
            or not finite(ticket_quote["decimal_odds"])
            or float(ticket_quote["decimal_odds"]) <= 1
        ):
            raise ValueError(
                "Combined ticket quote is incomplete, expired or cross-book"
            )
        offered_odds = float(ticket_quote["decimal_odds"])
        verified_price = True
        # Integer legs can push and change the settled ticket price/refund.
        # A marginal intersection alone does not identify that payout distribution.
        if exact and all(not float(r["line"]).is_integer() for r in legs):
            ev = joint * offered_odds - 1
    return {
        "legs": len(legs),
        "probability_lower_bound": max(
            0.0, sum(probabilities) - len(probabilities) + 1
        ),
        "probability_upper_bound": min(probabilities),
        "joint_probability": joint,
        "fair_odds": 1 / joint
        if exact and joint and all(not float(r["line"]).is_integer() for r in legs)
        else None,
        "offered_odds": offered_odds,
        "expected_value": ev,
        "combined_price_verified_by_owner": verified_price,
        "push_settlement_supported": all(
            not float(r["line"]).is_integer() for r in legs
        ),
        "dependencies": [
            dependency(a, b) for i, a in enumerate(legs) for b in legs[i + 1 :]
        ],
        "reason": "Exact threshold intersection under one common frozen marginal law"
        if exact
        else "No validated cross-player joint model: joint probability and ticket EV withheld; bounds inherit marginal uncertainty.",
    }


def season_scenario(probability, tickets):
    if (
        not finite(probability)
        or not 0 <= probability <= 1
        or type(tickets) is not int
        or not 1 <= tickets <= 100
    ):
        raise ValueError("Invalid scenario inputs")
    return {
        "independent_identical_ticket_scenario": 1 - (1 - probability) ** tickets,
        "assumption_free_bounds": [probability, min(1.0, tickets * probability)],
        "assumptions": "User-supplied equal ticket probability; independence scenario only, not a forecast or guarantee.",
    }
