"""Rebuild pregame features from observations, never use retrospective context."""

import numpy as np
import pandas as pd
from scripts.forecast_features import (
    player_features,
    pregame_eligible,
    observation_status,
)

MARKETS = {
    "passing_yards": ("passing_yards", ["QB"], "attempts", False),
    "passing_attempts": ("attempts", ["QB"], "attempts", True),
    "completions": ("completions", ["QB"], "attempts", True),
    "rushing_yards": ("rushing_yards", ["RB"], "carries", False),
    "rushing_attempts": ("carries", ["RB"], "carries", True),
    "qb_rushing_yards": ("rushing_yards", ["QB"], "carries", False),
    "qb_rushing_attempts": ("carries", ["QB"], "carries", True),
    "receiving_yards": ("receiving_yards", ["WR", "TE", "RB"], "targets", False),
    "receptions": ("receptions", ["WR", "TE", "RB"], "targets", True),
}
STATS = list(
    dict.fromkeys([v[0] for v in MARKETS.values()] + ["attempts", "carries", "targets"])
)


def prepare_panel(source, protocol):
    """Filter the sealed period BEFORE inspecting outcomes or computing history."""
    d = source.copy()
    kickoff = pd.to_datetime(d.kickoff_at, utc=True)
    final = (
        (kickoff >= pd.Timestamp(protocol["final_start"]))
        | (d.season > protocol["final_season"])
        | ((d.season == protocol["final_season"]) & (d.week >= protocol["final_week"]))
    )
    d = d.loc[
        ~final,
        [
            "player_id",
            "player_display_name",
            "position",
            "team",
            "season",
            "week",
            "game_id",
            "kickoff_at",
            "completed_at",
            "offense_pct",
            "stats_observed",
        ]
        + STATS,
    ].copy()
    d.kickoff_at = pd.to_datetime(d.kickoff_at, utc=True)
    d.completed_at = pd.to_datetime(d.completed_at, utc=True)
    if d.duplicated(["player_id", "game_id"]).any():
        raise ValueError("Duplicate player-game observations")
    if (d.completed_at < d.kickoff_at).any():
        raise ValueError("Outcome availability precedes kickoff")
    d = d.sort_values(["player_id", "kickoff_at"]).reset_index(drop=True)
    # Only earlier confirmed participation enters history. The eventual status
    # of the candidate is used for scoring, never eligibility/features.
    last = d.completed_at.where(d.offense_pct.gt(0)).groupby(d.player_id).cummax()
    last = last.groupby(d.player_id).ffill()
    d["history_available_at"] = last.groupby(d.player_id).shift(1)
    prior_kickoff = d.kickoff_at.where(d.offense_pct.gt(0)).groupby(d.player_id).ffill()
    d["prior_kickoff"] = prior_kickoff.groupby(d.player_id).shift(1)
    d = player_features(d, STATS, ["offense_pct"])
    d["prediction_at"] = d.kickoff_at - pd.Timedelta(
        hours=protocol["prediction_lead_hours"]
    )
    unknown_history = (
        (d.offense_pct.gt(0) & d.completed_at.isna()).groupby(d.player_id).cumsum()
    )
    unknown_history = unknown_history.groupby(d.player_id).shift(1).fillna(0)
    d["history_available"] = (
        d.history_available_at.notna()
        & (d.history_available_at < d.prediction_at)
        & unknown_history.eq(0)
    )
    d["returning"] = (
        (d.kickoff_at - d.prior_kickoff).dt.total_seconds().div(86400).gt(21)
    )
    return d


def feature_columns(market):
    target, _, opportunity, _ = MARKETS[market]
    return list(
        dict.fromkeys(
            [
                target + "_season_avg",
                target + "_last3_avg",
                target + "_last5_avg",
                target + "_trend",
                opportunity + "_season_avg",
                opportunity + "_last3_avg",
                "offense_pct_last3_avg",
                "games_played_prior",
            ]
        )
    )


def market_panel(panel, market):
    target, positions, _, count = MARKETS[market]
    d = panel.loc[pregame_eligible(panel, positions)].copy()
    cols = feature_columns(market)
    d["feature_complete"] = d[cols].notna().all(axis=1) & d.history_available
    d["scorable"] = (
        observation_status(d).eq("participated")
        & d.stats_observed.fillna(False).astype(bool)
        & d[target].notna()
        & d.completed_at.notna()
    )
    observed = d.loc[d.scorable, target]
    if (
        not np.isfinite(observed).all()
        or not np.equal(observed, np.floor(observed)).all()
    ):
        raise ValueError("NFL market outcomes must be observed finite integers")
    if count and observed.lt(0).any():
        raise ValueError("Negative count outcome")
    d["y"] = d[target]
    return d


def before(d, cutoff):
    """Outcome labels must be available strictly before a fit/selection cutoff."""
    return d[d.scorable & d.feature_complete & (d.completed_at < cutoff)].copy()


def read_development_snapshot(path, protocol):
    """Parquet predicate pushdown avoids materialising final-period outcomes."""
    cutoff = pd.Timestamp(protocol["final_start"])
    season = protocol["final_season"]
    week = protocol["final_week"]
    return pd.read_parquet(
        path,
        filters=[
            [("kickoff_at", "<", cutoff), ("season", "<", season)],
            [
                ("kickoff_at", "<", cutoff),
                ("season", "==", season),
                ("week", "<", week),
            ],
        ],
    )
