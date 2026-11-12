"""
Today's Slate: for the upcoming week's games, project every eligible player
across every trained market, using each player's most recent form and the
ACTUAL upcoming opponent's current defensive numbers (not whatever opponent
they happened to face last time).

This does not require bookmaker odds - it's a scan to help you spot
interesting projections worth checking against an actual sportsbook price
in the single-player tool. Edge/EV still needs a real odds input per prop,
which stays a manual step (no free odds API exists for this project).
"""
import pandas as pd
import numpy as np
import joblib
from datetime import datetime, timezone

try:
    from .forecast_features import (completed_history, defense_features, upcoming_player_state,
                                    pregame_eligible, schedule_times, utc_timestamp)
    from .build_features import STAT_COLS, AUX_STAT_COLS
except ImportError:
    from forecast_features import (completed_history, defense_features, upcoming_player_state,
                                   pregame_eligible, schedule_times, utc_timestamp)
    from build_features import STAT_COLS, AUX_STAT_COLS

MARKETS = {
    "passing_yards": "Passing Yards",
    "passing_attempts": "Passing Attempts",
    "completions": "Completions",
    "rushing_yards": "Rushing Yards",
    "rushing_attempts": "Rushing Attempts",
    "qb_rushing_yards": "QB Rushing Yards",
    "qb_rushing_attempts": "QB Rushing Attempts",
    "receiving_yards": "Receiving Yards",
    "receptions": "Receptions",
}


def get_upcoming_week(schedule: pd.DataFrame, as_of: pd.Timestamp):
    """Only not-yet-started games in the next season/week, in kickoff order."""
    schedule = schedule_times(schedule)
    upcoming = schedule[(schedule.game_type == "REG") &
                        (schedule.kickoff_at > utc_timestamp(as_of))]
    if upcoming.empty:
        raise ValueError("No upcoming regular-season games found in the schedule.")
    first = upcoming.sort_values("kickoff_at").iloc[0]
    return int(first.week), upcoming[(upcoming.season == first.season) & (upcoming.week == first.week)].copy()


def build_opponent_map(week_games: pd.DataFrame) -> dict:
    """team -> opponent, for every team playing in the target week."""
    opp_map = {}
    for _, row in week_games.iterrows():
        opp_map[row["home_team"]] = row["away_team"]
        opp_map[row["away_team"]] = row["home_team"]
    return opp_map


def latest_team_defense(features: pd.DataFrame) -> pd.DataFrame:
    """Inclusive defense state from an already cutoff-filtered history."""
    totals = defense_features(features, STAT_COLS, include_current=True)
    cols = [c for c in totals if c.startswith("opp_")]
    return totals.groupby("opponent_team").tail(1).set_index("opponent_team")[cols]


def build_game_context_for_week(week_games: pd.DataFrame) -> pd.DataFrame:
    """Same implied-total / home-away / indoor logic as build_features.py's
    build_game_context, but scoped to just the upcoming week's actual games -
    this is what makes the slate use THIS week's real lines, not last week's."""
    wg = week_games.copy()
    wg["home_implied_total"] = (wg["total_line"] + wg["spread_line"]) / 2
    wg["away_implied_total"] = (wg["total_line"] - wg["spread_line"]) / 2
    wg["indoor"] = wg["roof"].map({"dome": 1, "closed": 1, "outdoors": 0, "open": 0})

    home_rows = wg[["home_team", "home_implied_total", "away_implied_total", "indoor"]].rename(
        columns={"home_team": "team", "home_implied_total": "team_implied_total",
                 "away_implied_total": "opp_implied_total"}
    )
    home_rows["is_home"] = 1

    away_rows = wg[["away_team", "away_implied_total", "home_implied_total", "indoor"]].rename(
        columns={"away_team": "team", "away_implied_total": "team_implied_total",
                 "home_implied_total": "opp_implied_total"}
    )
    away_rows["is_home"] = 0

    return pd.concat([home_rows, away_rows], ignore_index=True).set_index("team")


def get_current_qb_starters(current_year: int, prediction_at=None) -> dict:
    """
    Live depth-chart data (updated daily, not tied to game history) - the
    ONLY reliable free source for "who is actually starting THIS week,"
    since a player returning from injury or a benching can't be inferred
    from past box scores alone. Returns {team: gsis_id} for each team's
    current QB1, using the single most recent snapshot available.
    """
    import nflreadpy as nfl
    dc = nfl.load_depth_charts(seasons=[current_year]).to_pandas()
    qb1 = dc[(dc["pos_abb"] == "QB") & (dc["pos_rank"] == 1)]
    cutoff = utc_timestamp(prediction_at if prediction_at is not None else datetime.now(timezone.utc))
    qb1 = qb1[pd.to_datetime(qb1["dt"], utc=True) <= cutoff]
    qb1_latest = qb1.sort_values("dt").groupby("team").tail(1)
    return dict(zip(qb1_latest["team"], qb1_latest["gsis_id"]))


def get_upcoming_qb_starters(schedule, prediction_at):
    """NFL season follows the fixture, including January of the next year."""
    _, games = get_upcoming_week(schedule, prediction_at)
    return get_current_qb_starters(int(games["season"].iloc[0]), prediction_at)


def build_slate(features: pd.DataFrame, schedule: pd.DataFrame, as_of: pd.Timestamp,
                 current_qb_starters: dict = None, completed_before=None, model_dir="data", allow_unverified_models=False,
                 allow_unverified_context=False, qb_starters_as_of=None) -> pd.DataFrame:
    prediction_at = utc_timestamp(as_of)
    cutoff = prediction_at if completed_before is None else utc_timestamp(completed_before)
    week, week_games = get_upcoming_week(schedule, prediction_at)
    if "context_available_at" not in week_games:
        if not allow_unverified_context:
            raise ValueError("Game context timestamp missing; replay requires an as-of schedule/lines snapshot")
    else:
        available = pd.to_datetime(week_games.context_available_at, utc=True)
        unknown = available.isna() | (available > prediction_at)
        week_games.loc[unknown, ["spread_line", "total_line", "roof"]] = np.nan
    if current_qb_starters is not None:
        if qb_starters_as_of is None or utc_timestamp(qb_starters_as_of) > prediction_at:
            raise ValueError("QB starters require a snapshot timestamp at/before prediction_at")
    history = completed_history(features, schedule, prediction_at, cutoff)
    team_defense = latest_team_defense(history)
    game_context = build_game_context_for_week(week_games)
    opp_map = build_opponent_map(week_games)
    latest_per_player = upcoming_player_state(history, STAT_COLS, AUX_STAT_COLS)
    current_season = int(week_games["season"].iloc[0])
    # A timestamped QB1 snapshot can confirm a returning/traded QB even when
    # his latest participating game belongs to the previous season or team.
    confirmed_qb = pd.Series(False, index=latest_per_player.index)
    if current_qb_starters:
        team_by_qb = {pid: team for team, pid in current_qb_starters.items()}
        confirmed_qb = latest_per_player.player_id.isin(team_by_qb) & latest_per_player.position.eq("QB")
        latest_per_player.loc[confirmed_qb, "team"] = latest_per_player.loc[confirmed_qb, "player_id"].map(team_by_qb)
    allowed_seasons = [current_season, current_season - 1] if week == 1 else [current_season]
    active = latest_per_player[(latest_per_player.season.isin(allowed_seasons) | confirmed_qb) &
                               latest_per_player.team.isin(opp_map)].copy()
    active["upcoming_opponent"] = active.team.map(opp_map)

    # Drop backup/benched QBs: a QB's LAST recorded game doesn't tell you if
    # someone else has since taken over (e.g. the starter returning from
    # injury). Only the live depth chart actually knows who's starting now.
    if current_qb_starters:
        is_qb = active["position"] == "QB"
        is_current_starter = active["player_id"].isin(current_qb_starters.values())
        active = active[~is_qb | is_current_starter]

    for col in ["team_implied_total", "opp_implied_total", "is_home", "indoor"]:
        active[col] = active["team"].map(game_context[col])

    rows = []
    for market_key, market_label in MARKETS.items():
        try:
            bundle = joblib.load(f"{model_dir}/model_{market_key}.joblib")
        except FileNotFoundError:
            continue
        training_cutoff = bundle.get("training_cutoff")
        if training_cutoff is None:
            if not allow_unverified_models:
                raise ValueError(f"{market_key}: model training cutoff missing; retrain before forecasting")
        elif utc_timestamp(training_cutoff) >= cutoff:
            raise ValueError(f"{market_key}: model contains training outcomes at/after completed-game cutoff")
        if bundle.get("feature_timing_version") != "stage1a" and not allow_unverified_models:
            raise ValueError(f"{market_key}: incompatible feature timing; coordinated model refresh required")
        model, feature_cols, resid_std, positions = (
            bundle["model"], bundle["features"], bundle["resid_std"], bundle["positions"]
        )
        eligible = active[pregame_eligible(active, positions)].copy()
        if eligible.empty:
            continue

        opp_feature_cols = [c for c in feature_cols if c.startswith("opp_") and c.endswith("_allowed_season_avg")]
        for col in opp_feature_cols:
            eligible[col] = eligible["upcoming_opponent"].map(team_defense[col])

        # Unknown roof is not an observed outdoor game. Keep complete player
        # forecasts as explicitly hypothetical indoor/outdoor scenarios; these
        # rows are not eligible for pricing or Top Picks until roof is known.
        other_cols = [c for c in feature_cols if c != "indoor"]
        eligible = eligible.dropna(subset=other_cols)
        if eligible.empty:
            continue

        X = eligible[feature_cols].copy()
        unknown_roof = eligible["indoor"].isna() if "indoor" in feature_cols else pd.Series(False, index=eligible.index)
        if "indoor" in feature_cols:
            X.loc[unknown_roof, "indoor"] = 0.0
        outdoor_preds = model.predict(X)
        if unknown_roof.any():
            X.loc[unknown_roof, "indoor"] = 1.0
            indoor_preds = model.predict(X)
        else:
            indoor_preds = outdoor_preds
        preds = np.where(unknown_roof, (outdoor_preds + indoor_preds) / 2, outdoor_preds)

        # feature_cols[0] is always the market's own *_season_avg (career-long) -
        # feature_cols[1] is always *_last3_avg, a much more realistic stand-in
        # for where a real bookmaker line would actually sit (recent form,
        # not a multi-year career average).
        for i, (_, r) in enumerate(eligible.iterrows()):
            rows.append({
                "market": market_label,
                "player": r["player_display_name"],
                "team": r["team"],
                "opponent": r["upcoming_opponent"],
                "position": r["position"],
                "projection": round(preds[i], 1),
                "career_avg": round(r[feature_cols[0]], 1),
                "recent_form": round(r[feature_cols[1]], 1),
                "resid_std": round(resid_std, 2),
                "games_played_prior": int(r["games_played_prior"]),
                "week": week,
                "season": current_season,
                "player_id": r["player_id"],
                "game_id": week_games.loc[(week_games.home_team == r["team"]) | (week_games.away_team == r["team"]), "game_id"].iloc[0],
                "prediction_at": prediction_at.isoformat(),
                "completed_before": cutoff.isoformat(),
                "last_completed_game_at": r["completed_at"].isoformat(),
                "completion_time_basis": r["completion_time_basis"],
                "context_timing_verified": "context_available_at" in week_games,
                "projection_status": "roof_scenarios_only" if bool(unknown_roof.iloc[i]) else "complete",
                "roof_scenario_low": round(min(outdoor_preds[i], indoor_preds[i]), 1),
                "roof_scenario_high": round(max(outdoor_preds[i], indoor_preds[i]), 1),
                "feature_timing_version": "stage1a",
            })

    columns = ["market", "player", "team", "opponent", "position", "projection", "career_avg",
               "recent_form", "resid_std", "games_played_prior", "week", "season", "player_id",
               "game_id", "prediction_at", "completed_before", "last_completed_game_at", "completion_time_basis", "context_timing_verified", "projection_status", "roof_scenario_low", "roof_scenario_high", "feature_timing_version"]
    return pd.DataFrame(rows, columns=columns)


def compute_top_picks(slate: pd.DataFrame, min_games: int = 8, top_n_per_game: int = 2,
                       side_filter: str = None) -> pd.DataFrame:
    """
    Ranks every projection by model CONVICTION - not confirmed betting value,
    since that needs a real bookmaker price we don't have for the whole slate.

    Uses RECENT FORM (last 3 games) as the stand-in line, not career average -
    real bookmaker lines track current role and recent production, not a
    multi-year history, so this is a much more realistic comparison point.

    Small-sample players are explicitly dampened (capped confidence below
    `min_games` prior appearances) since recent form and residual spread
    behind a 3-game sample are themselves unreliable.

    side_filter: pass "Over" to only surface Over picks (useful since many
    sportsbooks let you shop a lower alternate line for better Over odds,
    an option that doesn't work the same way for Under). Passing this
    narrows the pool to whatever upward conviction exists that week - if the
    model's strongest signals that week are mostly Unders, the remaining
    Over picks will be weaker/fewer than an unfiltered list would show.
    """
    from scipy.stats import norm

    picks = slate.copy()
    if "projection_status" in picks:
        picks = picks[picks.projection_status.eq("complete")].copy()
    if picks.empty:
        return picks.assign(side=pd.Series(dtype=str), model_probability=pd.Series(dtype=float), confidence=pd.Series(dtype=float))
    prob_over = 1 - norm.cdf(picks["recent_form"], picks["projection"], picks["resid_std"])
    picks["side"] = np.where(prob_over >= 0.5, "Over", "Under")
    picks["model_probability"] = np.where(prob_over >= 0.5, prob_over, 1 - prob_over)

    sample_dampener = (picks["games_played_prior"] / min_games).clip(upper=1.0)
    picks["confidence"] = (picks["model_probability"] - 0.5) * 2 * sample_dampener

    if side_filter:
        picks = picks[picks["side"] == side_filter]

    picks["game_key"] = picks.apply(lambda r: tuple(sorted([r["team"], r["opponent"]])), axis=1)

    top_picks = (
        picks.sort_values("confidence", ascending=False)
        .groupby("game_key")
        .head(top_n_per_game)
        .sort_values(["game_key", "confidence"], ascending=[True, False])
    )
    return top_picks.drop(columns=["game_key"])


if __name__ == "__main__":
    import nflreadpy as nfl
    prediction_at = datetime.now(timezone.utc)
    # Previous seasons are required to reconstruct inclusive career history.
    schedule = nfl.load_schedules(seasons=True).to_pandas()
    features = pd.read_parquet("data/player_features.parquet")
    qb_starters = get_upcoming_qb_starters(schedule, prediction_at)
    # This freshly downloaded context is observed now, never retroactively at
    # the start of the week. Historical replays must supply archived timestamps.
    prediction_at = datetime.now(timezone.utc)
    schedule["context_available_at"] = pd.Timestamp(prediction_at)
    slate = build_slate(features, schedule, pd.Timestamp(prediction_at), qb_starters,
                        qb_starters_as_of=prediction_at)
    print(f"Slate built: {len(slate)} player-market rows for week {slate['week'].iloc[0] if len(slate) else '?'}")
    slate.to_parquet("data/slate.parquet", index=False)

    top_picks = compute_top_picks(slate, side_filter="Over")
    print(f"\nTop Over picks: {len(top_picks)} rows")
    top_picks.to_parquet("data/top_picks.parquet", index=False)