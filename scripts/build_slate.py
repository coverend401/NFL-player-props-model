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
from datetime import datetime

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
    """The next week that has at least one game not yet played."""
    schedule = schedule.copy()
    schedule["gameday"] = pd.to_datetime(schedule["gameday"])
    reg = schedule[schedule["game_type"] == "REG"]
    upcoming = reg[reg["gameday"] >= as_of]
    if upcoming.empty:
        raise ValueError("No upcoming regular-season games found in the schedule.")
    week = int(upcoming["week"].min())
    return week, reg[reg["week"] == week]


def build_opponent_map(week_games: pd.DataFrame) -> dict:
    """team -> opponent, for every team playing in the target week."""
    opp_map = {}
    for _, row in week_games.iterrows():
        opp_map[row["home_team"]] = row["away_team"]
        opp_map[row["away_team"]] = row["home_team"]
    return opp_map


def latest_team_defense(features: pd.DataFrame) -> pd.DataFrame:
    """Each team's most recent (i.e. current, entering the next game) defensive
    allowed-average numbers, reusing the same opp_*_allowed_season_avg columns
    already computed per-game in build_features.py."""
    opp_cols = [c for c in features.columns if c.startswith("opp_") and c.endswith("_allowed_season_avg")]
    team_rows = (
        features[["opponent_team", "season", "week"] + opp_cols]
        .rename(columns={"opponent_team": "team"})
        .sort_values(["team", "season", "week"])
        .groupby("team")
        .tail(1)
        .set_index("team")
    )
    return team_rows[opp_cols]


def build_slate(features: pd.DataFrame, schedule: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    week, week_games = get_upcoming_week(schedule, as_of)
    schedule_current_season = week_games["season"].iloc[0]
    opp_map = build_opponent_map(week_games)
    team_defense = latest_team_defense(features)

    latest_per_player = (
        features.sort_values(["player_id", "season", "week"])
        .groupby("player_id")
        .tail(1)
    )
    # Only players active in the current season - otherwise a retired player
    # whose last known team happens to be playing this week would wrongly
    # show up (their team is real, but they aren't on it anymore).
    current_season = int(schedule_current_season)
    latest_per_player = latest_per_player[latest_per_player["season"] == current_season]

    # Only players whose most recent known team is actually playing this week
    active = latest_per_player[latest_per_player["team"].isin(opp_map.keys())].copy()
    active["upcoming_opponent"] = active["team"].map(opp_map)

    rows = []
    for market_key, market_label in MARKETS.items():
        try:
            bundle = joblib.load(f"data/model_{market_key}.joblib")
        except FileNotFoundError:
            continue
        model, feature_cols, resid_std, positions = (
            bundle["model"], bundle["features"], bundle["resid_std"], bundle["positions"]
        )
        eligible = active[active["position"].isin(positions)].copy()
        if eligible.empty:
            continue

        # Swap in the UPCOMING opponent's current defensive numbers, replacing
        # whatever opponent-allowed value was attached to their last game.
        opp_feature_cols = [c for c in feature_cols if c.startswith("opp_")]
        for col in opp_feature_cols:
            eligible[col] = eligible["upcoming_opponent"].map(team_defense[col])

        eligible = eligible.dropna(subset=feature_cols)
        if eligible.empty:
            continue

        X = eligible[feature_cols]
        preds = model.predict(X)

        for i, (_, r) in enumerate(eligible.iterrows()):
            rows.append({
                "market": market_label,
                "player": r["player_display_name"],
                "team": r["team"],
                "opponent": r["upcoming_opponent"],
                "position": r["position"],
                "projection": round(preds[i], 1),
                "season_avg": round(r[feature_cols[0]], 1),
                "games_played_prior": int(r["games_played_prior"]),
                "week": week,
            })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    import nflreadpy as nfl
    current_year = datetime.now().year
    schedule = nfl.load_schedules(seasons=[current_year]).to_pandas()
    features = pd.read_parquet("data/player_features.parquet")

    slate = build_slate(features, schedule, pd.Timestamp(datetime.now().date()))
    print(f"Slate built: {len(slate)} player-market rows for week {slate['week'].iloc[0] if len(slate) else '?'}")
    print(slate.sort_values(["market", "projection"], ascending=[True, False]).head(30).to_string(index=False))
    slate.to_parquet("data/slate.parquet", index=False)