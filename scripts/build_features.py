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

# Auxiliary stats from expected-opportunity, snap-share, and QB tracking data.
# These are just as much "outcomes of a game already played" as the STAT_COLS
# above, so they get the same shift(1)+rolling treatment before use - using a
# game's own aux stats to predict that same game would be leakage.
# Two Next Gen Stats columns (avg_separation, rush_yards_over_expected_per_att)
# were tested and deliberately excluded: only ~29% coverage (NGS only tracks
# "qualified" high-volume players), so requiring them would silently drop 70%
# of training rows - a worse trade than the accuracy they might add.
AUX_STAT_COLS = [
    "receptions_exp", "rec_yards_gained_exp", "pass_completions_exp", "pass_yards_gained_exp",
    "rush_yards_gained_exp", "offense_pct",
    "completion_pct_above_expectation", "avg_time_to_throw",
    "target_share", "air_yards_share", "wopr",
    "passing_epa", "rushing_epa", "receiving_epa",
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


def build_aux_data(seasons: list) -> pd.DataFrame:
    """
    Expected-opportunity, snap-share, and QB tracking data - process-based
    signals that separate real opportunity/skill from box-score luck.
    """
    ff = nfl.load_ff_opportunity(seasons=seasons).to_pandas()
    ff = ff.rename(columns={"player_id": "gsis_id"})
    ff = ff.dropna(subset=["gsis_id"])
    ff = ff[["gsis_id", "season", "week", "receptions_exp", "rec_yards_gained_exp",
             "pass_completions_exp", "pass_yards_gained_exp", "rush_yards_gained_exp"]].copy()
    ff["season"] = ff["season"].astype(int)
    ff["week"] = ff["week"].astype(int)

    players = nfl.load_players().to_pandas()[["gsis_id", "pfr_id"]].dropna()
    snaps = nfl.load_snap_counts(seasons=seasons).to_pandas()
    snaps = snaps.merge(players, left_on="pfr_player_id", right_on="pfr_id", how="inner")
    snaps = snaps.dropna(subset=["gsis_id"])
    snaps = snaps[["gsis_id", "season", "week", "offense_pct"]].copy()
    snaps = snaps.drop_duplicates(subset=["gsis_id", "season", "week"], keep="first")
    snaps["season"] = snaps["season"].astype(int)
    snaps["week"] = snaps["week"].astype(int)

    ngs_pass = nfl.load_nextgen_stats(seasons=seasons, stat_type="passing").to_pandas()
    ngs_pass = ngs_pass[ngs_pass["week"] > 0].dropna(subset=["player_gsis_id"])
    ngs_pass = ngs_pass[
        ["player_gsis_id", "season", "week", "completion_percentage_above_expectation", "avg_time_to_throw"]
    ].rename(columns={"player_gsis_id": "gsis_id",
                       "completion_percentage_above_expectation": "completion_pct_above_expectation"})
    ngs_pass["season"] = ngs_pass["season"].astype(int)
    ngs_pass["week"] = ngs_pass["week"].astype(int)

    aux = ff.merge(snaps, on=["gsis_id", "season", "week"], how="outer")
    aux = aux.merge(ngs_pass, on=["gsis_id", "season", "week"], how="outer")
    return aux.rename(columns={"gsis_id": "player_id"})


def build_player_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Treat regular season only for now (playoffs have different dynamics/sample size)
    df = df[df["season_type"] == "REG"].copy()

    # Drop rows with no player ID (unmatched/footnote entries from the source
    # data) BEFORE anything else touches them. These can't be tracked
    # per-player for rolling stats anyway, and left in, they'd silently fan
    # out against each other during merges - pandas treats missing IDs as
    # matching each other by default, which is not what we want here.
    before = len(df)
    df = df.dropna(subset=["player_id"]).copy()
    dropped = before - len(df)
    if dropped:
        print(f"Dropped {dropped} rows with no player_id (unmatched source data).")

    # Occasionally the source data itself has a literal duplicate row for the
    # same player/game (a data entry error upstream, not something we caused).
    # Left in, it would double-count that game in every rolling average for
    # the rest of that player's season - drop it here, before anything else.
    before = len(df)
    df = df.drop_duplicates(subset=["player_id", "season", "week"], keep="first")
    dupe_dropped = before - len(df)
    if dupe_dropped:
        print(f"Dropped {dupe_dropped} duplicate player/game rows found in the source data.")

    # Merge in auxiliary data before the rolling-feature loop, so it goes
    # through the exact same leakage-safe treatment as the core stats.
    seasons_for_aux = sorted(df["season"].unique().tolist())
    aux = build_aux_data(seasons_for_aux)
    df = df.merge(aux, on=["player_id", "season", "week"], how="left")

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

    # Auxiliary stats get season_avg and last3_avg only (not last5/trend) -
    # keeps the feature count from exploding while still capturing both a
    # stable long-run level and recent role/usage changes.
    for stat in AUX_STAT_COLS:
        shifted = grouped[stat].shift(1)
        df[f"{stat}_season_avg"] = (
            shifted.groupby(df["player_id"]).expanding().mean().reset_index(level=0, drop=True)
        )
        df[f"{stat}_last3_avg"] = (
            shifted.groupby(df["player_id"]).rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
        )

    # How many prior regular-season games this player has on record - critical
    # for the "flag small sample sizes" requirement later in the project.
    df["games_played_prior"] = grouped.cumcount()

    # --- Opponent defensive factor ---
    # For each team-week, what did they allow at each stat, using only PRIOR weeks.
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

    # --- Game context: implied team total, home/away, indoor - all known pre-kickoff ---
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
    print(f"Game context coverage: {features['team_implied_total'].notna().mean()*100:.1f}% of rows have betting-line data")
    features.to_parquet("data/player_features.parquet", index=False)