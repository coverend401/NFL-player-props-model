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

try:
    from .forecast_features import player_features, defense_features, observation_status, schedule_times, utc_timestamp
except ImportError:  # direct script execution in CI
    from forecast_features import player_features, defense_features, observation_status, schedule_times, utc_timestamp

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
    sched["indoor"] = sched["roof"].map({"dome": 1, "closed": 1, "outdoors": 0, "open": 0})

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


def build_participation_data(seasons: list) -> pd.DataFrame:
    """Historical snap records, including players absent from the stats source."""
    players = nfl.load_players().to_pandas()[["gsis_id", "pfr_id"]].dropna().drop_duplicates()
    snaps = nfl.load_snap_counts(seasons=seasons).to_pandas()
    snaps = snaps[snaps.game_type == "REG"].copy()
    snaps = snaps.merge(players, left_on="pfr_player_id", right_on="pfr_id", how="left", validate="many_to_one")
    print(f"Participation mapping: {int(snaps.gsis_id.isna().sum())} snap records have no GSIS ID; not fabricated.")
    snaps = snaps.dropna(subset=["gsis_id"])
    snaps = snaps.rename(columns={"gsis_id":"player_id", "player":"player_display_name",
                                  "opponent":"opponent_team", "game_type":"season_type"})
    columns = ["player_id", "season", "week", "game_id", "season_type", "player_display_name",
               "position", "team", "opponent_team", "offense_pct"]
    return snaps[columns].drop_duplicates(["player_id", "season", "week"])


def build_aux_data(seasons: list, participation=None) -> pd.DataFrame:
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

    snaps = build_participation_data(seasons) if participation is None else participation.copy()
    snaps = snaps.rename(columns={"player_id":"gsis_id"})

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


def build_player_features(df: pd.DataFrame, aux=None, game_context=None, schedule=None, team_stats=None, data_cutoff=None) -> pd.DataFrame:
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
    aux = build_aux_data(seasons_for_aux) if aux is None else aux
    df["stats_observed"] = True
    # Auxiliary-only players enter the panel only with a recorded snap record.
    # Their box-score outcomes remain NaN; absence is not evidence of zero.
    aux = aux[aux.player_id.isin(df.player_id) | aux.offense_pct.notna()].copy()
    df = df.merge(aux, on=["player_id", "season", "week"], how="outer",
                  suffixes=("", "_participation"), validate="one_to_one")
    for col in ["game_id", "season_type", "player_display_name", "position", "team", "opponent_team", "offense_pct"]:
        other = col + "_participation"
        if other in df:
            df[col] = df[col].combine_first(df.pop(other))
    df["stats_observed"] = df.stats_observed.eq(True)
    df = df[df.season_type.eq("REG")].copy()
    print("Participation-only missing outcomes by position:",
          df.loc[~df.stats_observed].groupby("position").size().to_dict())
    df["observation_status"] = observation_status(df)

    if schedule is not None:
        times = schedule_times(schedule)
        times = times[times.game_type == "REG"]
        df = df.merge(times[["game_id", "kickoff_at", "completed_at"]], on="game_id", how="left", validate="many_to_one")
        # Outcomes with no completed fixture cannot become historical inputs.
        # The Tuesday 09:00 run must not train on Monday observations whose
        # availability proxy is 09:15. Use the same strict boundary as replay.
        cutoff = utc_timestamp(data_cutoff if data_cutoff is not None else pd.Timestamp.now(tz="UTC"))
        unavailable = df.completed_at.isna() | (df.completed_at >= cutoff)
        if unavailable.any():
            print(f"Excluded {int(unavailable.sum())} source rows without a fixture available before the data cutoff.")
        df = df[~unavailable].copy()
        df["prediction_at"] = df.kickoff_at
        # Shift-based historical calculations require nonoverlapping games for
        # each player/defense. Fail instead of leaking an unfinished prior game.
        for key in ["player_id", "opponent_team"]:
            ordered = df.sort_values([key, "kickoff_at"]).drop_duplicates([key, "game_id"])
            previous_available = ordered.groupby(key).completed_at.shift(1)
            if (previous_available >= ordered.kickoff_at).any():
                raise ValueError(f"Overlapping/unavailable prior games for {key}; explicit as-of reconstruction required")

    # The same calculator builds entering-game and upcoming inclusive states.
    df = player_features(df, STAT_COLS, AUX_STAT_COLS)
    if team_stats is not None:
        totals = team_stats.rename(columns={"passing_interceptions":"interceptions"})
        totals = totals[totals.season_type.eq("REG")]
        total_cols = {c: f"team_total_{c}" for c in STAT_COLS}
        df = df.merge(totals[["game_id", "team"] + STAT_COLS].rename(columns=total_cols),
                      on=["game_id", "team"], how="left", validate="many_to_one")
    allowed = defense_features(df, STAT_COLS)
    opp_cols = [c for c in allowed if c.startswith("opp_")]
    df = df.merge(allowed[["opponent_team", "season", "week"] + opp_cols],
                  on=["opponent_team", "season", "week"], how="left", validate="many_to_one")

    # --- Game context: implied team total, home/away, indoor - all known pre-kickoff ---
    seasons = sorted(df["season"].unique().tolist())
    game_context = build_game_context(seasons) if game_context is None else game_context
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
    participants = df[df.offense_pct.gt(0) & df.position.isin(["QB", "RB", "WR", "TE"])]
    counts = participants.groupby("player_id").size()
    ids = counts[counts >= 4].index[:12]
    if len(ids) == 0:
        raise ValueError("Leakage check requires a player with four participating games")
    checks = 0
    for player_id in ids:
        rows = participants[participants.player_id.eq(player_id)].sort_values(["season", "week"])
        for stat in ["passing_yards", "carries", "targets"]:
            prior = rows.iloc[:3][stat]
            current = rows.iloc[3]
            expected_recent = prior.mean() if prior.notna().all() else np.nan
            for suffix, expected in [("season_avg", prior.mean()), ("last3_avg", expected_recent)]:
                actual = current[f"{stat}_{suffix}"]
                assert np.isclose(expected, actual, equal_nan=True), (
                    f"LEAKAGE CHECK FAILED: {player_id} {stat}_{suffix}: expected {expected}, got {actual}")
                checks += 1
    print(f"Leakage check passed: {checks} manual feature comparisons across {len(ids)} players.")


if __name__ == "__main__":
    df = pd.read_parquet("data/weekly_player_data.parquet")
    schedule = nfl.load_schedules(seasons=sorted(df["season"].unique().tolist())).to_pandas()
    team_stats = nfl.load_team_stats(seasons=sorted(df["season"].unique().tolist())).to_pandas()
    features = build_player_features(df, schedule=schedule, team_stats=team_stats)
    leakage_check(features)
    print(f"Built features for {len(features)} rows, {features.shape[1]} columns.")
    print(f"Game context coverage: {features['team_implied_total'].notna().mean()*100:.1f}% of rows have betting-line data")
    features.to_parquet("data/player_features.parquet", index=False)