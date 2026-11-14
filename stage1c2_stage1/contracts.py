"""Evidence contracts; source status and missing data never imply a pregame zero."""

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from stage1c.contracts import assert_development, team

COUNT_FIELDS = ["attempts", "carries", "targets"]
ROSTER_COLUMNS = [
    "season",
    "week",
    "game_type",
    "team",
    "position",
    "gsis_id",
    "pfr_id",
    "jersey_number",
    "status",
    "status_description_abbr",
]
SNAP_COLUMNS = [
    "game_id",
    "season",
    "week",
    "game_type",
    "team",
    "position",
    "pfr_player_id",
    "offense_snaps",
    "defense_snaps",
    "st_snaps",
]
INJURY_COLUMNS = [
    "season",
    "week",
    "game_type",
    "team",
    "gsis_id",
    "report_status",
    "date_modified",
]


def filters():
    # Predicate pushdown before materialising even a single sealed-period row.
    return [
        [("season", "<", 2026), ("game_type", "==", "REG")],
        [("season", "==", 2026), ("week", "<", 11), ("game_type", "==", "REG")],
    ]


def canonical(value):
    if pd.isna(value):
        return None
    try:
        return team({"JAC": "JAX"}.get(str(value).upper(), value))
    except ValueError:
        return None


def bounded_read(path, columns):
    available = set(pq.ParquetFile(path).schema_arrow.names)
    missing = set(columns) - available
    if missing - {"date_modified"}:
        raise ValueError("Required source identity/stat field absent")
    d = pd.read_parquet(
        path, columns=[c for c in columns if c in available], filters=filters()
    )
    if "date_modified" in missing:
        # The 2025+ injury schema genuinely lacks this publication-related field.
        # Unknown remains NaT, never an inferred pregame publication time.
        d["date_modified"] = pd.Series(
            pd.NaT, index=d.index, dtype="datetime64[ns, UTC]"
        )
    assert_development(d)
    d["team"] = d.team.map(canonical)
    return d


def classify_count(observed, participation, value, ledger_strict, event_value):
    if observed and pd.notna(value):
        return (
            "observed_zero"
            if value == 0
            else "observed_positive"
            if value > 0
            else "invalid_count"
        )
    if participation and ledger_strict and pd.notna(event_value):
        return (
            "ledger_confirmed_zero"
            if event_value == 0
            else "ledger_recovered_positive"
            if event_value > 0
            else "invalid_count"
        )
    return "missing_unknown"


def predecision_verified(evidence, cutoff):
    """A week label, ACT/INA code or asset creation date is not sufficient."""
    needed = ["published_at", "received_at", "version_archived_at"]
    if not evidence.get("row_content_bound", False) or not evidence.get(
        "official_predecision_status", False
    ):
        return False
    try:
        times = [pd.Timestamp(evidence.get(k)) for k in needed]
        decision = pd.Timestamp(cutoff)
    except (TypeError, ValueError):
        return False
    if pd.isna(decision) or decision.tzinfo is None:
        return False
    return all(pd.notna(t) and t.tzinfo is not None and t < decision for t in times)


def check_count_ledger(d):
    assert_development(d)
    if d.duplicated(["game_id", "team", "player_id", "field"]).any():
        raise ValueError("Ambiguous overlay count identity")
    values = d.value.to_numpy(float)
    if (
        not np.isfinite(values).all()
        or (values < 0).any()
        or not np.allclose(values, np.round(values))
    ):
        raise ValueError("Invalid recovered opportunity count")
    if not d.evidence_tier.eq("retrospective_internal_reconciliation").all():
        raise ValueError(
            "Unverified historical count cannot be promoted to pregame evidence"
        )
    if d.usable_at_verified.notna().any():
        raise ValueError("No archived historical publication evidence in this overlay")
