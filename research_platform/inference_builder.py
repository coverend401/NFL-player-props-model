"""Research-only, upstream eligibility adapter over unchanged Stage 1A inference.

A private function namespace injects current identity without modifying module
state, historical observations, model features or the production builder.
"""

from types import FunctionType

import pandas as pd

from scripts import build_slate as production
from scripts.build_features import AUX_STAT_COLS, STAT_COLS
from scripts.forecast_features import (
    completed_history,
    upcoming_player_state,
    utc_timestamp,
)

ELIGIBILITY_SCHEMA = "pregame_eligibility_v1"


def candidate_state(features, schedule, prediction, cutoff, starters):
    history = completed_history(features, schedule, prediction, cutoff)
    state = upcoming_player_state(history, STAT_COLS, AUX_STAT_COLS)
    _, games = production.get_upcoming_week(schedule, prediction)
    season = int(games.season.iloc[0])
    return state[
        state.position.isin(["QB", "RB", "WR", "TE"])
        & (
            state.season.eq(season)
            | (state.position.eq("QB") & state.player_id.isin(starters.values()))
        )
    ].copy()


def eligibility_map(document, prediction):
    prediction = utc_timestamp(prediction)
    if (
        document.get("schema") != ELIGIBILITY_SCHEMA
        or utc_timestamp(document["as_of"]) > prediction
    ):
        raise ValueError("Invalid or future eligibility document")
    records = {}
    for r in document["players"]:
        required = {
            "player_id",
            "team",
            "source",
            "evidence_at",
            "available_at",
            "effective_at",
            "status",
            "reason",
        }
        if not required <= set(r) or r["player_id"] in records:
            raise ValueError("Missing/duplicate eligibility identity")
        if r["status"] not in {"eligible", "ineligible", "unresolved"}:
            raise ValueError("Invalid eligibility status")
        if (
            not r["source"]
            or utc_timestamp(r["available_at"]) > prediction
            or utc_timestamp(r["evidence_at"]) > prediction
        ):
            raise ValueError("Eligibility evidence not available before prediction")
        if (
            r["effective_at"] is not None
            and utc_timestamp(r["effective_at"]) > prediction
        ):
            raise ValueError("Eligibility evidence is not yet effective")
        if r["status"] == "eligible" and (not r["team"] or r["effective_at"] is None):
            raise ValueError("Eligible player lacks effective team evidence")
        if r["status"] != "eligible" and not r["reason"]:
            raise ValueError("Excluded/unresolved eligibility requires a reason")
        records[r["player_id"]] = r
    return records


def build_inference(
    features,
    schedule,
    prediction,
    cutoff,
    starters,
    starters_as_of,
    eligibility,
    model_dir,
):
    records = eligibility_map(eligibility, prediction)
    required = set(
        candidate_state(features, schedule, prediction, cutoff, starters).player_id
    )
    if set(records) != required:
        raise ValueError(
            "Eligibility input must explicitly cover every candidate player"
        )
    for team, pid in starters.items():
        if (
            pid in records
            and records[pid]["status"] == "eligible"
            and records[pid]["team"] != team
        ):
            raise ValueError("QB starter and current-team evidence conflict")

    def current_state(history, stats, aux):
        state = upcoming_player_state(history, stats, aux)
        # Current identity changes only this future-state copy; never old games.
        state = state[state.player_id.isin(records)].copy()
        state["team"] = state.player_id.map({p: r["team"] for p, r in records.items()})
        return state[
            state.player_id.map({p: r["status"] for p, r in records.items()}).eq(
                "eligible"
            )
        ]

    def upcoming(schedule, as_of):
        week, games = production.get_upcoming_week(schedule, as_of)
        games = games[
            games.kickoff_at.gt(utc_timestamp(as_of) + pd.Timedelta(minutes=60))
        ]
        if games.empty:
            raise ValueError("No fixture remains before the T-60 decision cutoff")
        return week, games

    namespace = {
        **production.build_slate.__globals__,
        "upcoming_player_state": current_state,
        "get_upcoming_week": upcoming,
    }
    builder = FunctionType(
        production.build_slate.__code__,
        namespace,
        "research_frozen_inference",
        production.build_slate.__defaults__,
    )
    return builder(
        features,
        schedule,
        prediction,
        current_qb_starters=starters,
        completed_before=cutoff,
        model_dir=model_dir,
        qb_starters_as_of=starters_as_of,
    )


def derive_eligibility(state, roster, schedule, prediction, source):
    """Current-week evidence only; capture time is not an NFL transaction date."""
    prediction = utc_timestamp(prediction)
    available = utc_timestamp(source["retrieved_at"])
    if available > prediction:
        raise ValueError("Roster source is future information")
    week, games = production.get_upcoming_week(schedule, prediction)
    season = int(games.season.iloc[0])
    future = games[games.kickoff_at.gt(prediction + pd.Timedelta(minutes=60))]
    future_teams = set(future.home_team) | set(future.away_team)
    rows = []
    for p in state.sort_values("player_id").itertuples():
        evidence = roster[
            roster.gsis_id.eq(p.player_id)
            & roster.season.eq(season)
            & roster.week.eq(week)
        ][["team", "status"]].drop_duplicates()
        row = {
            "player_id": p.player_id,
            "player": p.player_display_name,
            "historical_team": p.team,
            "team": None,
            "source": source["url"],
            "source_sha256": source["sha256"],
            "evidence_at": available.isoformat(),
            "available_at": available.isoformat(),
            "effective_at": None,
            "effective_time_basis": "snapshot_observed_at_not_transaction_date",
            "status": "unresolved",
            "reason": "No unambiguous current-week roster evidence",
            "roster_status": None,
        }
        if len(evidence) == 1:
            team, status = evidence.iloc[0][["team", "status"]]
            row.update(
                team=team, roster_status=status, effective_at=available.isoformat()
            )
            if status == "ACT" and team in future_teams:
                row.update(
                    status="eligible",
                    reason="Current-week active roster and future fixture; game-day inactives remain unknown",
                )
            elif status == "ACT":
                row.update(
                    status="ineligible",
                    reason="Current club has no remaining pre-decision fixture this week",
                )
            elif status in ["DEV", "CUT"]:
                row.update(
                    status="ineligible",
                    reason="Practice squad at snapshot; later documented elevation may supersede"
                    if status == "DEV"
                    else "Current-week released roster status",
                )
            else:
                row.update(
                    reason="Current-week status does not establish active-roster eligibility"
                )
        rows.append(row)
    return {
        "schema": ELIGIBILITY_SCHEMA,
        "as_of": available.isoformat(),
        "players": rows,
    }
