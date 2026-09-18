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

STAT_COLS = [
    "passing_yards", "passing_tds", "interceptions", "completions", "attempts",
    "carries", "rushing_yards", "rushing_tds",
    "receptions", "targets", "receiving_yards", "receiving_tds",
]

def build_player_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Treat regular season only for now (playoffs have different dynamics/sample size)
    df = df[df["season_type"] == "REG"].copy()

    # Chronological sort is essential - this is what makes shift() safe
    df = df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)

    grouped = df.groupby("player_id", group_keys=False)

    for stat in STAT_COLS:
        # shift(1) first: excludes the current game from its own rolling window
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
        # Simple trend signal: last3 vs season avg (positive = trending up recently)
        df[f"{stat}_trend"] = df[f"{stat}_last3_avg"] - df[f"{stat}_season_avg"]

    # How many prior regular-season games this player has on record - critical
    # for the "flag small sample sizes" requirement later in the project.
    df["games_played_prior"] = grouped.cumcount()

    # --- Opponent defensive factor ---
    # For each team-week, what did they allow at each stat, using only PRIOR weeks.
    team_allowed = (
        df.groupby(["opponent_team", "season", "week"])[STAT_COLS]
        .sum()
        .reset_index()
        .rename(columns={"opponent_team": "team"})
    )
    team_allowed = team_allowed.sort_values(["team", "season", "week"])
    for stat in STAT_COLS:
        shifted_allowed = team_allowed.groupby("team")[stat].shift(1)
        team_allowed[f"opp_{stat}_allowed_season_avg"] = (
            shifted_allowed.groupby(team_allowed["team"]).expanding().mean().reset_index(level=0, drop=True)
        )

    opp_cols = ["team", "season", "week"] + [f"opp_{s}_allowed_season_avg" for s in STAT_COLS]
    df = df.merge(
        team_allowed[opp_cols],
        left_on=["opponent_team", "season", "week"],
        right_on=["team", "season", "week"],
        how="left",
    ).drop(columns=["team"])

    return df


def leakage_check(df: pd.DataFrame) -> None:
    """
    Sanity test: for a handful of players, manually recompute the season_avg
    for one game and confirm it matches ONLY prior games, never the game itself
    or future games.
    """
    sample_player = df["player_id"].iloc[len(df) // 2]
    player_rows = df[df["player_id"] == sample_player].sort_values(["season", "week"]).reset_index(drop=True)
    if len(player_rows) < 4:
        return
    check_idx = 3  # 4th game for this player
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
    features.to_parquet("data/player_features.parquet", index=False)