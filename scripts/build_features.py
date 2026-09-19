"""
Feature engineering for NFL player prop model.

CRITICAL RULE: every feature for a given (player, season, week) row must be
computed using ONLY games strictly BEFORE that week. We achieve this by
sorting chronologically and using .shift(1) before any rolling/expanding
calculation, so the current game's own stats are never included in its
own features.
"""
import pandas as pd
import numpy as np
import nflreadpy as nfl

STAT_COLS = [
    "passing_yards", "passing_tds", "interceptions", "completions", "attempts",
    "carries", "rushing_yards", "rushing_tds",
    "receptions", "targets", "receiving_yards", "receiving_tds",
]


def build_game_context(seasons: list) -> pd.DataFrame:
    """
    Per-team-per-game context from the closing betting lines: how many points
    is this team implied to score, how many is the opponent, are they home,
    is it indoors. These are all known BEFORE kickoff (closing lines are set
    ahead of the game, home/away and roof type are known in advance), so using
    them is not leakage - unlike the final score, which we never touch.

    Deliberately excludes temperature/wind: those aren't reliably known until
    close to kickoff, so a model trained on them couldn't be used to predict
    upcoming games consistently - it would work in training and then fail in
    production the moment weather data isn't available yet.
    """
    sched = nfl.load_schedules(seasons=seasons).to_pandas()
    sched = sched[sched["game_type"] == "REG"].copy()

    sched["home_implied_total"] = (sched["total_line"] + sched["spread_line"]) / 2
    sched["away_implied_total"] = (sched["total_line"] - sched["spread_line"]) / 2
    sched["indoor"] = sched["roof"].isin(["dome", "closed"]).astype(int)

    home_rows = sched[["season", "week", "home_team", "away_team",
                        "home_implied_total", "away_implied_total", "total_line", "indoor"]].rename(
        columns={"home_team": "team", "away_team": "opponent_team",
                 "home_implied_total": "team_implied_total", "away_implied_total": "opp_implied_total"}
    )
    home_rows["is_home"] = 1

    away_rows = sched[["season", "week", "away_team", "home_team",
                        "away_implied_total", "home_implied_total", "total_line", "indoor"]].rename(
        columns={"away_team": "team", "home_team": "opponent_team",
                 "away_implied_total": "team_implied_total", "home_implied_total": "opp_implied_total"}
    )
    away_rows["is_home"] = 0

    return pd.concat([home_rows, away_rows], ignore_index=True)


def build_player_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df[df["season_type"] == "REG"].copy()
    df = df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)

    grouped = df.groupby("player_id", group_keys=False)

    for stat in STAT_COLS:
        shifted = grouped[stat].shift(1)
        df[f"{stat}_season_avg"] = (
            shifted.groupby(df["player_id"]).expanding().mean().reset_index(level=0, drop=True)
        )
        df[f"{stat}_last3_avg"] = (
            shifted.groupby(df["player_id"]).rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
        )
        df[f"{stat}_last5_avg"] = (
            shifted.groupby(df["player_id"]).rolling(5, min_periods=1).mean().reset_index(level=0, drop=True)
        )
        df[f"{stat}_trend"] = df[f"{stat}_last3_avg"] - df[f"{stat}_season_avg"]

    df["games_played_prior"] = grouped.cumcount()

    team_allowed = (
        df.groupby(["opponent_team", "season", "week"])[STAT_COLS]
        .sum()
        .reset_index()
        .rename(columns={"opponent_team": "_opp_team_key"})
    )
    team_allowed = team_allowed.sort_values(["_opp_team_key", "season", "week"])
    for stat in STAT_COLS:
        shifted_allowed = team_allowed.groupby("_opp_team_key")[stat].shift(1)
        team_allowed[f"opp_{stat}_allowed_season_avg"] = (
            shifted_allowed.groupby(team_allowed["_opp_team_key"]).expanding().mean().reset_index(level=0, drop=True)
        )

    opp_cols = ["_opp_team_key", "season", "week"] + [f"opp_{s}_allowed_season_avg" for s in STAT_COLS]
    df = df.merge(
        team_allowed[opp_cols],
        left_on=["opponent_team", "season", "week"],
        right_on=["_opp_team_key", "season", "week"],
        how="left",
    ).drop(columns=["_opp_team_key"])

    seasons = sorted(df["season"].unique().tolist())
    game_context = build_game_context(seasons)
    df = df.merge(
        game_context,
        left_on=["season", "week", "team", "opponent_team"],
        right_on=["season", "week", "team", "opponent_team"],
        how="left",
    )

    return df


def leakage_check(df: pd.DataFrame) -> None:
    sample_player = df["player_id"].iloc[len(df) // 2]
    player_rows = df[df["player_id"] == sample_player].sort_values(["season", "week"]).reset_index(drop=True)
    if len(player_rows) < 4:
        return
    check_idx = 3
    stat = "passing_yards"
    prior_games = player_rows.loc[:check_idx - 1, stat]
    expected_avg = prior_games.mean()
    actual_avg = player_rows.loc[check_idx, f"{stat}_season_avg"]
    assert np.isclose(expected_avg, actual_avg, equal_nan=True), (
        f"LEAKAGE CHECK FAILED: expected {expected_avg}, got {actual_avg}"
    )
    print(f"Leakage check passed for player {sample_player}, game index {check_idx}: "
          f"season_avg={actual_avg:.2f} matches manual calc of prior games only.")


if __name__ == "__main__":
    df = pd.read_parquet("data/weekly_player_data.parquet")
    features = build_player_features(df)
    leakage_check(features)
    print(f"Built features for {len(features)} rows, {features.shape[1]} columns.")
    print(f"Game context coverage: {features['team_implied_total'].notna().mean()*100:.1f}% of rows have betting-line data")
    features.to_parquet("data/player_features.parquet", index=False)