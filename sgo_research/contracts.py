"""Small provider contracts, independent from the forecasting engine."""

import math
import re
import unicodedata
from datetime import UTC, datetime
from fractions import Fraction

STAT_MARKETS = {
    "passing_yards": "Passing Yards",
    "passing_attempts": "Passing Attempts",
    "passing_completions": "Completions",
    "rushing_yards": "Rushing Yards",
    "rushing_attempts": "Rushing Attempts",
    "receiving_yards": "Receiving Yards",
    "receiving_receptions": "Receptions",
}
FREE_BOOKS = (
    "fanduel",
    "draftkings",
    "betmgm",
    "caesars",
    "espnbet",
    "bovada",
    "unibet",
    "pointsbet",
    "williamhill",
)
TEAMS = {
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAX",
    "KC",
    "LA",
    "LAC",
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
}
ALIASES = {
    "LAR": "LA",
    "JAC": "JAX",
    "WSH": "WAS",
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LA",
}


class Unavailable(RuntimeError):
    pass


def utc(value):
    try:
        t = datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise Unavailable("Missing/invalid UTC timestamp") from None
    if t.tzinfo is None:
        raise Unavailable("Timestamp has no timezone")
    return t.astimezone(UTC)


def name_key(value):
    s = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", s.casefold()))


def team_key(value):
    key = ALIASES.get(str(value).upper(), str(value).upper())
    return key if key in TEAMS else None


def odds_formats(raw):
    # SGO's documented odds representation is American, never infer a fractional
    # or decimal format from an ambiguous unsigned string.
    try:
        american = float(raw)
    except (ValueError, TypeError):
        raise Unavailable("Invalid American price") from None
    if not math.isfinite(american) or abs(american) < 100:
        raise Unavailable("Invalid American price")
    profit = (
        Fraction(str(american)) / 100
        if american > 0
        else Fraction(100) / abs(Fraction(str(american)))
    )
    return 1 + float(profit), f"{profit.numerator}/{profit.denominator}"


def account_limits(body):
    data = body.get("data", body)
    if (
        not isinstance(data, dict)
        or str(data.get("tier", "")).strip().casefold() != "amateur"
        or data.get("isActive") is not True
    ):
        raise Unavailable(
            "Active Amateur tier is not confirmed; no paid or trial fallback"
        )
    raw = data.get("rateLimits", {})
    if not isinstance(raw, dict):
        raise Unavailable("Invalid account usage schema")
    aliases = {
        "max_entities": ("maxEntitiesPerInterval", "max-entities"),
        "used_entities": ("currentIntervalEntities", "current-entities"),
        "max_requests": ("maxRequestsPerInterval", "max-requests"),
        "used_requests": ("currentIntervalRequests", "current-requests"),
        "end": ("currentIntervalEndTime", "intervalEnd"),
    }
    out = {}
    for interval in ["per-minute", "per-hour", "per-day", "per-month"]:
        entry = raw.get(interval, {})
        if not isinstance(entry, dict):
            raise Unavailable("Invalid account usage schema")
        row = {}
        for key, fields in aliases.items():
            values = [entry[f] for f in fields if f in entry]
            if len(values) == 2 and values[0] != values[1]:
                raise Unavailable("Conflicting account usage schemas")
            v = values[0] if values else None
            if key == "end":
                row[key] = None if v in [None, "n/a"] else utc(v).isoformat()
            elif v in [None, "n/a", "unlimited"] or type(v) is int and v >= 0:
                row[key] = v
            else:
                raise Unavailable("Invalid account usage count")
        out[interval] = row
    month = out["per-month"]
    if (
        type(month["max_entities"]) is not int
        or type(month["used_entities"]) is not int
        or not month["end"]
    ):
        raise Unavailable("Exact monthly usage/reset unavailable; collection stopped")
    return out
