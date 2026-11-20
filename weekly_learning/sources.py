"""Bounded free nflverse snapshots. Quarantine precedes sealed-outcome filtering."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from .store import encoded, sha


def permitted(season, week, policy):
    if season > policy["final_season"] or (
        season == policy["final_season"] and week >= policy["final_week"]
    ):
        raise ValueError(
            "SEALED: prospective settlement policy and compatible inference contract require owner approval"
        )


def filters(season, through_week, policy):
    permitted(season, through_week, policy)
    return [("season", "==", season), ("week", "<=", through_week)]


def fetch(root, season, through_week, policy, *, forecasting=False):
    permitted(
        season, through_week, policy
    )  # Before any HTTP or result materialisation.
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    base = "https://github.com/nflverse/nflverse-data/releases/download/"
    paths = {
        "player_stats": f"stats_player/stats_player_week_{season}.parquet",
        "team_stats": f"stats_team/stats_team_week_{season}.parquet",
        "schedule": "schedules/games.parquet",
        "snaps": f"snap_counts/snap_counts_{season}.parquet",
        "players": "players/players.parquet",
    }
    if forecasting:
        paths.update(
            {
                "ngs": "nextgen_stats/ngs_passing.parquet",
                "depth": f"depth_charts/depth_charts_{season}.parquet",
                "roster": f"rosters/roster_{season}.parquet",
            }
        )
        paths["opportunity"] = (
            f"https://github.com/ffverse/ffopportunity/releases/download/latest-data/ep_weekly_{season}.parquet"
        )
    records = {}
    for name, suffix in paths.items():
        now = datetime.now(UTC).isoformat()
        url = (
            suffix
            if suffix.startswith("https://github.com/ffverse/")
            else base + suffix
        )
        path = root / (name + ".parquet")
        if path.exists():
            raise ValueError("Source snapshot directory must be new; no overwrite")
        with requests.get(url, stream=True, timeout=(5, 30)) as response:
            response.raise_for_status()
            size = 0
            with path.open("xb") as out:
                for block in response.iter_content(1024 * 1024):
                    size += len(block)
                    if size > 32 * 1024 * 1024:
                        raise ValueError("Source size bound exceeded")
                    out.write(block)
            records[name] = {
                "url": url,
                "retrieval_started_at": now,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "sha256": sha(path),
                "bytes": size,
                "last_modified": response.headers.get("Last-Modified"),
            }
    (root / "sources.json").write_text(encoded(records))
    return root


def verify_snapshot(root, *, max_age_hours=None):
    root = Path(root)
    records = json.loads((root / "sources.json").read_text())
    allowed = {
        "player_stats",
        "team_stats",
        "schedule",
        "snaps",
        "players",
        "opportunity",
        "ngs",
        "depth",
        "roster",
    }
    if not records or not set(records) <= allowed:
        raise ValueError("Unexpected source identity")
    for name, record in records.items():
        path = root / (name + ".parquet")
        if not record["url"].startswith(
            (
                "https://github.com/nflverse/nflverse-data/releases/download/",
                "https://github.com/ffverse/ffopportunity/releases/download/",
            )
        ):
            raise ValueError("Unapproved source provenance")
        retrieved = pd.Timestamp(record["retrieved_at"])
        if retrieved.tzinfo is None or retrieved > pd.Timestamp.now(tz="UTC"):
            raise ValueError("Invalid source retrieval timestamp")
        if max_age_hours is not None and pd.Timestamp.now(
            tz="UTC"
        ) - retrieved > pd.Timedelta(hours=max_age_hours):
            raise ValueError("Forecast source snapshot is stale")
        if path.stat().st_size > 32 * 1024 * 1024 or sha(path) != record["sha256"]:
            raise ValueError("Raw source integrity mismatch")
    return records


def load_results(root, season, week, policy):
    from scripts.forecast_features import schedule_times

    root = Path(root)
    f = filters(season, week, policy)
    verify_snapshot(root)
    box = pd.read_parquet(root / "player_stats.parquet", filters=f).rename(
        columns={"passing_interceptions": "interceptions"}
    )
    schedule = schedule_times(pd.read_parquet(root / "schedule.parquet", filters=f))
    identities = (
        pd.read_parquet(root / "players.parquet", columns=["gsis_id", "pfr_id"])
        .dropna()
        .drop_duplicates()
    )
    snaps = pd.read_parquet(root / "snaps.parquet", filters=f).merge(
        identities,
        left_on="pfr_player_id",
        right_on="pfr_id",
        how="left",
        validate="many_to_one",
    )
    snaps = snaps.dropna(subset=["gsis_id"]).rename(columns={"gsis_id": "player_id"})
    if snaps.duplicated(["player_id", "game_id"]).any():
        raise ValueError("Ambiguous player snap identity")
    box["stats_observed"] = True
    participation = snaps[["player_id", "game_id", "offense_pct"]]
    box = box.merge(
        participation, on=["player_id", "game_id"], how="outer", validate="one_to_one"
    )
    box["stats_observed"] = box.stats_observed.eq(True)
    teams = pd.read_parquet(root / "team_stats.parquet", filters=f)
    teams["offensive_plays"] = teams.attempts + teams.carries + teams.sacks_suffered
    teams["play_definition"] = (
        "official attempts + carries + sacks suffered; not total PBP rows"
    )
    return box, schedule, teams
