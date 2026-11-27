"""Project ESPN fixture metadata without decoding scores or other outcome values."""

import hashlib
import json
import re
from datetime import UTC, datetime

import pandas as pd
import requests

from .admission import ALIASES, ESPN
from .store import encoded

LEAF = True
FIELDS = {
    "season": {"year": LEAF, "type": LEAF},
    "week": {"number": LEAF},
    "events": [
        {
            "id": LEAF,
            "date": LEAF,
            "competitions": [
                {
                    "date": LEAF,
                    "competitors": [{"homeAway": LEAF, "team": {"abbreviation": LEAF}}],
                }
            ],
        }
    ],
}


def metadata_json(raw, fields=FIELDS):
    """Unrequested JSON subtrees are lexically skipped, never decoded/materialised."""
    s = raw.decode("utf-8")
    decoder = json.JSONDecoder()

    def ws(i):
        while i < len(s) and s[i].isspace():
            i += 1
        return i

    def skip(i):
        i = ws(i)
        if s[i] == '"':
            j = i + 1
            while j < len(s):
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == '"':
                    return j + 1
                j += 1
            raise ValueError("Unterminated JSON string")
        if s[i] in "{[":
            stack = [s[i]]
            j = i + 1
            while stack:
                j = ws(j)
                if j >= len(s):
                    raise ValueError("Truncated JSON")
                c = s[j]
                if c == '"':
                    j = skip(j)
                    continue
                if c in "{[":
                    stack.append(c)
                elif c in "}]" and stack.pop() != ("{" if c == "}" else "["):
                    raise ValueError("Invalid JSON nesting")
                j += 1
            return j
        j = i
        while j < len(s) and s[j] not in ",]} \r\n\t":
            j += 1
        if not re.fullmatch(
            r"(?:true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", s[i:j]
        ):
            raise ValueError("Invalid JSON scalar")
        return j

    def read(i, fields):
        i = ws(i)
        if fields is True:
            value, j = decoder.raw_decode(s, i)
            if isinstance(value, (dict, list)):
                raise ValueError("Unexpected fixture metadata type")
            return value, j
        array = isinstance(fields, list)
        opening, closing = ("[", "]") if array else ("{", "}")
        if s[i] != opening:
            raise ValueError("Unexpected fixture envelope")
        out = [] if array else {}
        i = ws(i + 1)
        if s[i] == closing:
            return out, i + 1
        while True:
            if array:
                value, i = read(i, fields[0])
                out.append(value)
            else:
                key, i = decoder.raw_decode(s, i)
                if not isinstance(key, str) or s[ws(i)] != ":":
                    raise ValueError("Invalid metadata field")
                i = ws(i) + 1
                if key in fields:
                    if key in out:
                        raise ValueError("Duplicate metadata field")
                    out[key], i = read(i, fields[key])
                else:
                    i = skip(i)
            i = ws(i)
            if s[i] == closing:
                return out, i + 1
            if s[i] != ",":
                raise ValueError("Invalid JSON delimiter")
            i = ws(i + 1)

    try:
        out, end = read(0, fields)
    except (IndexError, RecursionError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Invalid fixture metadata") from None
    if ws(end) != len(s):
        raise ValueError("Trailing metadata payload")
    return out


def collect(directory, profile, *, get=None):
    m = json.loads((directory / "manifest.json").read_text())
    scope = m["fixture_slate"]
    params = {
        "dates": str(scope["season"]),
        "seasontype": 2,
        "week": scope["week"],
        "limit": 100,
    }
    with (get or requests.get)(
        ESPN, params=params, stream=True, timeout=(5, 30), allow_redirects=False
    ) as r:
        if r.status_code != 200:
            raise ValueError(
                f"Fixture metadata unavailable (HTTP {r.status_code}); no retry"
            )
        raw = bytearray()
        for chunk in r.iter_content(65536):
            raw.extend(chunk)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("Fixture metadata exceeds bound")
    body = metadata_json(raw)
    if (
        body.get("season", {}).get("year") != scope["season"]
        or body.get("season", {}).get("type") != 2
        or body.get("week", {}).get("number") != scope["week"]
    ):
        raise ValueError("Independent fixture season/week mismatch")
    games = []
    for e in body.get("events", []):
        if len(e.get("competitions", [])) != 1:
            raise ValueError("Ambiguous fixture competition")
        c = e["competitions"][0]
        sides = {
            x["homeAway"]: ALIASES.get(
                x["team"]["abbreviation"], x["team"]["abbreviation"]
            )
            for x in c["competitors"]
        }
        if set(sides) != {"home", "away"} or len(c["competitors"]) != 2:
            raise ValueError("Ambiguous fixture teams")
        games.append(
            {
                "game_id": f"{scope['season']}_{scope['week']:02d}_{sides['away']}_{sides['home']}",
                "kickoff_at": pd.Timestamp(c.get("date", e["date"])).isoformat(),
                "provider_event_id": e["id"],
            }
        )
    expected = m["game_kickoffs"]
    cutoff = pd.Timestamp(m["prediction_at"]) + pd.Timedelta(minutes=60)
    upcoming = {
        g["game_id"]: g for g in games if pd.Timestamp(g["kickoff_at"]) > cutoff
    }
    if (
        len({g["game_id"] for g in games}) != len(games)
        or set(upcoming) != set(expected)
        or any(
            abs(
                (
                    pd.Timestamp(t) - pd.Timestamp(upcoming[g]["kickoff_at"])
                ).total_seconds()
            )
            > 300
            for g, t in expected.items()
        )
    ):
        raise ValueError("Independent upcoming fixture identity/timing mismatch")
    proof = {
        "status": "PASS",
        "season": scope["season"],
        "week": scope["week"],
        "fixtures_verified": games,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "source": ESPN,
        "outcomes_decoded": False,
    }
    path = profile / "fixture_verification.json"
    profile.mkdir(exist_ok=True)
    if path.exists():
        raise ValueError("Fixture evidence is immutable")
    path.write_text(encoded(proof))
    return proof
