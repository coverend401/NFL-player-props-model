"""Identity, evidence and temporal boundaries; game time is not publication time."""

import pandas as pd

FINAL = pd.Timestamp("2026-11-19T00:00:00Z")
TEAMS = set(
    "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LA LAC LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split()
)
ALIASES = {"LAR": "LA", "STL": "LA", "OAK": "LV", "SD": "LAC", "WSH": "WAS"}


def team(value):
    key = ALIASES.get(str(value).upper(), str(value).upper())
    if key not in TEAMS:
        raise ValueError("Unknown team identity")
    return key


def utc(value):
    t = pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError("Explicit timezone required")
    return t.tz_convert("UTC")


def development_filters():
    return [
        [("season", "<", 2026), ("season_type", "==", "REG")],
        [("season", "==", 2026), ("week", "<", 11), ("season_type", "==", "REG")],
    ]


def assert_development(d):
    if d[["season", "week"]].isna().any().any():
        raise ValueError("Missing season/week identity")
    if (d.season > 2026).any() or ((d.season == 2026) & (d.week >= 11)).any():
        raise ValueError("Sealed final period")
    if "kickoff_at" in d and (pd.to_datetime(d.kickoff_at, utc=True) >= FINAL).any():
        raise ValueError("Sealed final date")


def availability(row, verified=False, lag_hours=36):
    kickoff = utc(row["kickoff_at"])
    complete = utc(row["completed_at"])
    if complete < kickoff + pd.Timedelta(hours=8):
        raise ValueError("Completion safeguard weakened")
    if row.get("release_policy") == "postseason_only":
        raise ValueError("Postseason-only source excluded from in-season states")
    if verified:
        if row.get("evidence_tier") != "verified_predecision" or not row.get(
            "source_sha256"
        ):
            raise ValueError("Missing verified provenance")
        return max(complete, utc(row["published_at"]), utc(row["captured_at"]))
    if row.get("evidence_tier") != "retrospective":
        raise ValueError("Retrospective proxy must be labelled")
    if lag_hours < 8:
        raise ValueError("Availability proxy below completion minimum")
    return max(complete, kickoff + pd.Timedelta(hours=lag_hours))


def effective_identity(records, player_id, decision):
    """Never infer historical team from a current roster or player name."""
    t = utc(decision)
    d = records[records.player_id.eq(player_id)].copy()
    d = d[
        (pd.to_datetime(d.valid_from, utc=True) <= t)
        & (pd.to_datetime(d.available_at, utc=True) <= t)
        & (
            pd.to_datetime(d.valid_to, utc=True).isna()
            | (pd.to_datetime(d.valid_to, utc=True) > t)
        )
    ]
    if len(d) != 1:
        raise ValueError("Missing or ambiguous as-of player identity")
    return team(d.iloc[0].team)
