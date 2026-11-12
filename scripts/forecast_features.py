"""Shared historical/live feature calculations. Missing outcomes are never filled.

Legacy *_season_avg names intentionally retain their career-expanding semantics
so existing model artifacts remain loadable. Availability timestamps are UTC.
"""

import numpy as np
import pandas as pd

KEYS = ["player_id", "season", "week"]
MIN_PRIOR_GAMES = 3


def utc_timestamp(value):
    value = pd.Timestamp(value)
    if pd.isna(value):
        raise ValueError("A valid prediction/cutoff timestamp is required")
    return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")


def schedule_times(schedule):
    """Prefer explicit completion/availability timestamps when supplied.

    nflverse does not provide final-whistle timestamps. For scored fixtures use
    kickoff + 8h as a conservative availability proxy, not an observed end time.
    Historical replay also requires point-in-time source snapshots (see docs).
    """
    s = schedule.copy()
    if "kickoff_at" in s:
        s["kickoff_at"] = pd.to_datetime(s["kickoff_at"], utc=True)
    else:
        local = pd.to_datetime(
            s["gameday"].astype(str) + " " + s["gametime"].astype(str), errors="raise"
        )
        s["kickoff_at"] = local.dt.tz_localize(
            "America/New_York", ambiguous="raise", nonexistent="raise"
        ).dt.tz_convert("UTC")
    final = s[["home_score", "away_score"]].notna().all(axis=1)
    if "completion_time_basis" not in s:
        s["completion_time_basis"] = (
            "provided_completion_time"
            if "completed_at" in s
            else "kickoff_plus_8h_proxy"
        )
    if "completed_at" in s:
        s["completed_at"] = pd.to_datetime(s["completed_at"], utc=True).where(final)
    else:
        s["completed_at"] = (s["kickoff_at"] + pd.Timedelta(hours=8)).where(final)
    if "stats_available_at" in s:
        available = pd.to_datetime(s["stats_available_at"], utc=True)
        s["completed_at"] = (
            pd.concat([s["completed_at"], available], axis=1)
            .max(axis=1)
            .where(final & available.notna())
        )
    return s


def completed_history(observations, schedule, prediction_at, completed_before=None):
    """Select only scored games available strictly before both UTC cutoffs."""
    prediction_at = utc_timestamp(prediction_at)
    cutoff = (
        prediction_at if completed_before is None else utc_timestamp(completed_before)
    )
    if cutoff > prediction_at:
        raise ValueError("completed_before must not be later than prediction_at")
    s = schedule_times(schedule)
    s = s[(s.game_type == "REG") & (s.completed_at < cutoff)]
    if s.game_id.duplicated().any():
        raise ValueError("Duplicate schedule game IDs")
    h = observations.copy()
    if "season_type" in h:
        h = h[h.season_type == "REG"]
    # Match opponent as well as season/week/team to avoid admitting a postponed
    # or mismatched fixture. Never use precomputed rolling features from the input.
    teams = pd.concat(
        [
            s[
                [
                    "season",
                    "week",
                    "home_team",
                    "away_team",
                    "game_id",
                    "kickoff_at",
                    "completed_at",
                    "completion_time_basis",
                ]
            ].rename(columns={"home_team": "team", "away_team": "opponent_team"}),
            s[
                [
                    "season",
                    "week",
                    "away_team",
                    "home_team",
                    "game_id",
                    "kickoff_at",
                    "completed_at",
                    "completion_time_basis",
                ]
            ].rename(columns={"away_team": "team", "home_team": "opponent_team"}),
        ],
        ignore_index=True,
    )
    h = h.drop(
        columns=["game_id", "kickoff_at", "completed_at", "completion_time_basis"],
        errors="ignore",
    ).merge(
        teams,
        on=["season", "week", "team", "opponent_team"],
        how="inner",
        validate="many_to_one",
    )
    if h.duplicated(KEYS).any():
        raise ValueError("Duplicate player-game observations")
    return h.sort_values(["player_id", "kickoff_at"]).reset_index(drop=True)


def player_features(frame, stat_cols, aux_cols, include_current=False):
    """Features per participating game, aligned to every candidate row.

    No-snap/unknown-participation rows remain in the observation panel but do
    not become artificial zero games in the player's history. Snap-only games
    DO enter history: their unknown box scores invalidate the recent windows.
    """
    order = ["player_id", "kickoff_at"] if "kickoff_at" in frame else KEYS
    df = frame.sort_values(order).reset_index(drop=True).copy()
    played = df.offense_pct.gt(0)
    history = df.loc[played]
    generated = {}
    for stat in dict.fromkeys(stat_cols + aux_cols):
        values = history[stat]
        groups = values.groupby(history.player_id, sort=False)
        avg = groups.expanding().mean().reset_index(level=0, drop=True)
        generated[f"{stat}_season_avg"] = avg
        last3 = groups.rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
        if stat in stat_cols:
            unknown = values.isna().astype(int)
            missing3 = (
                unknown.groupby(history.player_id, sort=False)
                .rolling(3, min_periods=1)
                .sum()
                .reset_index(level=0, drop=True)
            )
            last3 = last3.mask(missing3.gt(0))
        generated[f"{stat}_last3_avg"] = last3
        if stat in stat_cols:
            missing5 = (
                unknown.groupby(history.player_id, sort=False)
                .rolling(5, min_periods=1)
                .sum()
                .reset_index(level=0, drop=True)
            )
            generated[f"{stat}_last5_avg"] = (
                groups.rolling(5, min_periods=1)
                .mean()
                .reset_index(level=0, drop=True)
                .mask(missing5.gt(0))
            )
            generated[f"{stat}_trend"] = last3 - avg
    generated["games_played_prior"] = (
        history.groupby("player_id", sort=False).cumcount() + 1
    )
    states = pd.DataFrame(generated, index=history.index)
    # The latest participating row strictly before each candidate, including
    # candidates whose eventual participation is zero or unknown.
    state_index = pd.Series(df.index, index=df.index, dtype=float).where(played)
    state_index = state_index.groupby(df.player_id, sort=False).ffill()
    if not include_current:
        state_index = state_index.groupby(df.player_id, sort=False).shift(1)
    aligned = states.reindex(state_index.to_numpy()).set_axis(df.index)
    aligned["games_played_prior"] = aligned.games_played_prior.fillna(0).astype(int)
    return pd.concat(
        [df.drop(columns=list(generated), errors="ignore"), aligned], axis=1
    )


def pregame_eligible(frame, positions):
    return (
        frame.position.isin(positions)
        & frame.games_played_prior.ge(MIN_PRIOR_GAMES)
        & frame.offense_pct_last3_avg.gt(0)
    )


def observation_status(frame):
    """No offensive snaps is NOT proof of inactivity or a sportsbook void."""
    return pd.Series(
        np.select(
            [frame.offense_pct.gt(0), frame.offense_pct.eq(0)],
            ["participated", "no_offensive_snaps"],
            default="unknown_participation",
        ),
        index=frame.index,
    )


def defense_features(history, stat_cols, include_current=False):
    """One observation per defense/game; all-missing totals remain missing."""
    keys = ["opponent_team", "season", "week"]
    if "kickoff_at" in history:
        keys += ["kickoff_at"]
    source_cols = [f"team_total_{c}" for c in stat_cols]
    if all(c in history for c in source_cols):
        # Team-level outcomes are authoritative even when individual box-score
        # rows are missing. Repeated totals must not be summed over players.
        totals = history.groupby(keys)[source_cols].first().reset_index()
        totals = totals.rename(columns=dict(zip(source_cols, stat_cols)))
    else:
        # Compatibility for older snapshots and small fixtures. No all-missing
        # aggregate becomes zero; this fallback cannot prove complete coverage.
        totals = history.groupby(keys)[stat_cols].sum(min_count=1).reset_index()
    order = (
        ["opponent_team", "kickoff_at"]
        if "kickoff_at" in totals
        else ["opponent_team", "season", "week"]
    )
    totals = totals.sort_values(order).reset_index(drop=True)
    for stat in stat_cols:
        values = (
            totals[stat]
            if include_current
            else totals.groupby("opponent_team")[stat].shift(1)
        )
        totals[f"opp_{stat}_allowed_season_avg"] = (
            values.groupby(totals.opponent_team)
            .expanding()
            .mean()
            .reset_index(level=0, drop=True)
        )
    return totals


def upcoming_player_state(history, stat_cols, aux_cols):
    history = history[history.offense_pct.gt(0)]
    state = player_features(history, stat_cols, aux_cols, include_current=True)
    return state.groupby("player_id", sort=False).tail(1).copy()
