"""Freeze small development-only team-game inputs, with original-source hashes.

No participation/coverage charts, injuries, betting lines, EPA/CPOE or other
upstream fitted models are used. Downloads cache raw bytes; predicates prevent
sealed outcomes from being materialised. Publication history remains unverified.
"""

from datetime import datetime, timezone
import argparse, json
from pathlib import Path
import requests
import numpy as np
import pandas as pd
from stage1b.data import read_development_snapshot
from scripts.forecast_features import schedule_times
from stage1b.artifacts import digest
from stage1c.contracts import development_filters, assert_development, team

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = [
    "game_id",
    "play_id",
    "season",
    "week",
    "season_type",
    "posteam",
    "defteam",
    "play_type",
    "pass_attempt",
    "rush_attempt",
    "sack",
    "qb_dropback",
    "qb_scramble",
    "qb_kneel",
    "qb_spike",
    "two_point_attempt",
    "no_huddle",
    "score_differential",
    "qtr",
    "half_seconds_remaining",
    "drive",
    "home_score",
    "away_score",
]


def aggregate_pbp(d):
    assert_development(d)
    if d.duplicated(["game_id", "play_id"]).any():
        raise ValueError("Duplicate play identity")
    d = d.sort_values(["game_id", "play_id"]).copy()
    # Clock gaps only within a possession/drive and half, positive and <=60s.
    g = d.groupby(["game_id", "posteam", "drive", "qtr"], dropna=False)
    d["gap"] = g.half_seconds_remaining.shift(1) - d.half_seconds_remaining
    d["neutral"] = d.score_differential.abs().le(7) & d.qtr.le(3)
    d["pace_valid"] = d.neutral & d.gap.gt(0) & d.gap.le(60)
    plays = d[
        d.play_type.isin(["pass", "run"])
        & d.two_point_attempt.ne(1)
        & d.posteam.notna()
        & d.defteam.notna()
    ].copy()
    plays["dropback"] = plays.qb_dropback.eq(1).astype(float)
    plays["rush"] = plays.rush_attempt.eq(1).astype(float)
    plays["pace_sum"] = plays.gap.where(plays.pace_valid, 0)
    plays["pace_n"] = plays.pace_valid.astype(float)
    return (
        plays.groupby(
            ["game_id", "posteam", "defteam", "season", "week"], as_index=False
        )
        .agg(
            plays=("play_id", "size"),
            dropbacks=("dropback", "sum"),
            rushes=("rush", "sum"),
            no_huddle=("no_huddle", "sum"),
            pace_sum=("pace_sum", "sum"),
            pace_n=("pace_n", "sum"),
            home_score=("home_score", "max"),
            away_score=("away_score", "max"),
        )
        .rename(columns={"posteam": "team", "defteam": "opponent"})
    )


def position_aggregates(source):
    source = source.copy()
    source["team"] = source.team.map(team)
    stats = [
        "passing_yards",
        "attempts",
        "completions",
        "rushing_yards",
        "carries",
        "receiving_yards",
        "targets",
        "receptions",
    ]
    groups = {
        "pass": source,
        "rush_QB": source[source.position.eq("QB")],
        "rush_RB": source[source.position.eq("RB")],
    }
    groups.update(
        {f"rec_{pos}": source[source.position.eq(pos)] for pos in ["RB", "WR", "TE"]}
    )
    rows = []
    for kind, d in groups.items():
        if kind == "pass":
            tc = ["team_total_" + x for x in stats]
            if d.groupby(["game_id", "team"])[tc].nunique().gt(1).any().any():
                raise ValueError("Conflicting official team totals")
            x = (
                d.groupby(["game_id", "team"], as_index=False)[tc]
                .first()
                .rename(columns=dict(zip(tc, stats)))
            )
            x["known_complete"] = (
                x[["passing_yards", "attempts", "completions"]].notna().all(axis=1)
            )
            x["unknown_players"] = 0
        else:
            x = d.groupby(["game_id", "team"], as_index=False)[stats].sum(min_count=1)
            unknown = (
                d.assign(unknown=~d.stats_observed.fillna(False))
                .groupby(["game_id", "team"], as_index=False)
                .unknown.sum()
            )
            x = x.merge(unknown, on=["game_id", "team"], validate="one_to_one").rename(
                columns={"unknown": "unknown_players"}
            )
            x["known_complete"] = x.unknown_players.eq(0)
            # Partial positional box scores are NOT complete zero-stat observations.
            x.loc[~x.known_complete, stats] = np.nan
        x["kind"] = kind
        rows.append(x)
    return pd.concat(rows, ignore_index=True)


def build(output, cache):
    output = Path(output)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("Input bundle is immutable")
    p = json.loads((ROOT / "stage1b1/protocol.json").read_text())
    pointer = json.loads((ROOT / "active_release.json").read_text())
    base = ROOT / pointer["path"]
    records = []
    frames = []
    for season in range(2019, 2027):
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
        path = cache / f"{season}.parquet"
        if not path.exists():
            r = requests.get(url, timeout=90)
            r.raise_for_status()
            path.write_bytes(r.content)
        d = pd.read_parquet(path, columns=COLUMNS, filters=development_filters())
        frames.append(aggregate_pbp(d))
        records.append(
            {
                "url": url,
                "sha256": digest(path),
                "bytes": path.stat().st_size,
                "retrieved_at": datetime.fromtimestamp(
                    path.stat().st_mtime, timezone.utc
                ).isoformat(),
                "materialisation": "Parquet development predicates before column loading",
                "publication_history_verified": False,
            }
        )
        print("READ", season, len(d), flush=True)
    games = pd.concat(frames, ignore_index=True)
    schedule = pd.read_parquet(
        base / "inputs/schedule.parquet",
        columns=[
            "game_id",
            "season",
            "week",
            "game_type",
            "gameday",
            "gametime",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
        ],
        filters=[
            [("season", ">=", 2019), ("season", "<", 2026), ("game_type", "==", "REG")],
            [("season", "==", 2026), ("week", "<", 11), ("game_type", "==", "REG")],
        ],
    )
    schedule = schedule_times(schedule)
    assert_development(schedule)
    games = games.merge(
        schedule[["game_id", "kickoff_at", "completed_at", "home_team"]],
        on="game_id",
        how="left",
        validate="many_to_one",
    )
    if games.kickoff_at.isna().any():
        raise ValueError("Unmatched fixture")
    games["is_home"] = games.team.eq(games.home_team).astype(int)
    games["points_for"] = np.where(games.is_home, games.home_score, games.away_score)
    games["points_against"] = np.where(
        games.is_home, games.away_score, games.home_score
    )
    games["margin"] = games.points_for - games.points_against
    source = read_development_snapshot(base / "data/player_features.parquet", p)
    rates = position_aggregates(source)
    for col in ["team", "opponent"]:
        games[col] = games[col].map(team)
    rates["team"] = rates.team.map(team)
    games = games.drop(columns=["home_score", "away_score", "home_team"])
    assert_development(games)
    if (
        games.duplicated(["game_id", "team"]).any()
        or not games.groupby("game_id").size().eq(2).all()
    ):
        raise ValueError("Invalid two-team fixture panel")
    output.mkdir(parents=True)
    games.to_parquet(output / "team_games.parquet", index=False)
    rates.to_parquet(output / "position_totals.parquet", index=False)
    manifest = {
        "schema": 1,
        "evidence_tier": "retrospective",
        "source_records": records,
        "player_snapshot_sha256": digest(base / "data/player_features.parquet"),
        "schedule_sha256": digest(base / "inputs/schedule.parquet"),
        "final_period_sealed": True,
        "files": {
            n: digest(output / n)
            for n in ["team_games.parquet", "position_totals.parquet"]
        },
        "rows": len(games),
        "note": "Current corrected statistics; no historical publication archive. No genuine verified predecision claim.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("FROZEN", output, len(games), flush=True)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--cache", type=Path, default=Path("/tmp/stage1c-pbp"))
    args = a.parse_args()
    build(args.output, args.cache)
