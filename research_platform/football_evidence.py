"""Read-only football context from the certified, cutoff-filtered inference inputs."""

from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.build_features import AUX_STAT_COLS, STAT_COLS
from scripts.build_slate import latest_team_defense
from scripts.forecast_features import completed_history, upcoming_player_state

MARKETS = {
    "Passing Yards": ("passing_yards", "attempts", "passing"),
    "Passing Attempts": ("attempts", "attempts", "passing"),
    "Completions": ("completions", "attempts", "passing"),
    "Rushing Yards": ("rushing_yards", "carries", "rushing"),
    "QB Rushing Yards": ("rushing_yards", "carries", "rushing"),
    "Rushing Attempts": ("carries", "carries", "rushing"),
    "QB Rushing Attempts": ("carries", "carries", "rushing"),
    "Receiving Yards": ("receiving_yards", "targets", "receiving"),
    "Receptions": ("receptions", "targets", "receiving"),
}


@st.cache_data(show_spinner=False)
def recorded_context(release_id, prediction, cutoff):
    root = Path(__file__).resolve().parents[1]
    # Only the already validated default inference bundle; never open research outcomes.
    import json

    pointer = json.loads((root / "research_active_inference.json").read_text())
    directory = (root / pointer["path"]).resolve()
    directory.relative_to(root / "research_inference_releases")
    manifest = json.loads((directory / "manifest.json").read_text())
    if (
        manifest["release_id"],
        manifest["prediction_at"],
        manifest["feature_data_cutoff"],
    ) != (release_id, prediction, cutoff):
        return {}, {}, {}
    history = completed_history(
        pd.read_parquet(directory / "features.parquet"),
        pd.read_parquet(directory / "schedule.parquet"),
        prediction,
        cutoff,
    )
    players = upcoming_player_state(history, STAT_COLS, AUX_STAT_COLS).set_index(
        "player_id"
    )
    defense = latest_team_defense(history)
    games = (
        history.groupby(["team", "season", "week"], as_index=False)
        .agg(
            attempts=("team_total_attempts", "first"),
            carries=("team_total_carries", "first"),
            completed_at=("completed_at", "max"),
        )
        .sort_values("completed_at")
    )
    teams = (
        games.groupby("team")
        .tail(3)
        .groupby("team")
        .agg(
            attempts=("attempts", "mean"),
            carries=("carries", "mean"),
            games=("week", "size"),
        )
    )
    return players.to_dict("index"), defense.to_dict("index"), teams.to_dict("index")


def attach_context(rows, release):
    if release.get("release_type") != "research_frozen_model_inference_v1":
        return rows
    players, defenses, teams = recorded_context(
        release["release_id"], release["prediction_at"], release["feature_data_cutoff"]
    )

    def opponent(row):
        teams = row["game_id"].split("_")[-2:]
        return (
            next((team for team in teams if team != row.get("team")), None)
            if row.get("team") in teams
            else None
        )

    return [
        {
            **r,
            "football_context": {
                "player": players.get(r["player_id"], {}),
                "opponent": opponent(r),
                "defense": defenses.get(opponent(r), {}),
                "cutoff": release["feature_data_cutoff"],
                "team": teams.get(r.get("team"), {}),
            },
        }
        for r in rows
    ]
