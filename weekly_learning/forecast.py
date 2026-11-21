"""Refresh only current-season inputs and reuse the existing frozen-model builder."""

import shutil
from pathlib import Path
from types import FunctionType

import pandas as pd
import pyarrow.parquet as pq

from release_utils import resolve_release, validate_manifest
from scripts.build_features import build_player_features
from scripts.forecast_features import schedule_times
from scripts.prepare_research_inference import prepare

from .sources import permitted, verify_snapshot
from .store import ROOT, encoded, sha


def require_current_depth(depth, teams, since):
    latest = depth.groupby("team")["observed"].max().reindex(sorted(teams))
    if latest.isna().any() or (latest < pd.Timestamp(since).normalize()).any():
        raise ValueError(
            "Target-week depth evidence missing/stale; no prior-week starter reuse"
        )


def prepare_next(sources, work, target_week, policy, release_id, model_parent=None):
    season = 2026
    permitted(season, target_week - 1, policy)
    sources = Path(sources)
    work = Path(work)
    work.mkdir(parents=True, exist_ok=False)
    meta = verify_snapshot(sources, max_age_hours=48)
    admission = None
    if target_week - 1 >= policy["final_week"]:
        from .admission import validate_receipt

        admission = sources / "operational_admission.json"
        receipt = validate_receipt(ROOT, admission, policy)
        if receipt["target_week"] != target_week:
            raise ValueError("Forecast target differs from operational admission")
    required = {
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
    if not required <= set(meta):
        raise ValueError("Forecast sources incomplete; no stale auxiliary fallback")
    now = pd.Timestamp.now(tz="UTC")
    cutoff = now
    parent_data, _parent = resolve_release(ROOT)
    old = pd.read_parquet(parent_data / "player_features.parquet")
    old_schedule = pd.read_parquet(parent_data.parent / "inputs/schedule.parquet")

    def read(name, columns=None):
        path = sources / (name + ".parquet")
        schema = pq.read_schema(path)
        value = str(season) if str(schema.field("season").type) == "string" else season
        return pd.read_parquet(
            path,
            columns=columns,
            filters=[
                ("season", "==", value),
                ("week", ">=", 1),
                ("week", "<", target_week),
            ],
        )

    past = read("schedule")
    columns = [
        "season",
        "week",
        "game_type",
        "game_id",
        "gameday",
        "gametime",
        "home_team",
        "away_team",
        "spread_line",
        "total_line",
        "roof",
    ]
    future = pd.read_parquet(
        sources / "schedule.parquet",
        columns=columns,
        filters=[("season", "==", season), ("week", "==", target_week)],
    )
    schedule = pd.concat(
        [old_schedule[old_schedule.season.lt(season)], past, future], ignore_index=True
    )
    schedule = schedule.drop(
        columns=[
            "kickoff_at",
            "completed_at",
            "completion_time_basis",
            "stats_available_at",
        ],
        errors="ignore",
    )
    schedule["context_available_at"] = now
    schedule = schedule_times(schedule)
    if (
        future.empty
        or not (
            schedule[
                schedule.week.eq(target_week) & schedule.season.eq(season)
            ].kickoff_at
            > now + pd.Timedelta(minutes=60)
        ).any()
    ):
        raise ValueError("No verified upcoming requested fixtures")
    box = read("player_stats").rename(
        columns={"passing_interceptions": "interceptions"}
    )
    ids = (
        pd.read_parquet(sources / "players.parquet", columns=["gsis_id", "pfr_id"])
        .dropna()
        .drop_duplicates()
    )
    snaps = read("snaps")
    snaps = snaps[snaps.game_type.eq("REG")].merge(
        ids,
        left_on="pfr_player_id",
        right_on="pfr_id",
        how="left",
        validate="many_to_one",
    )
    unmapped = (
        snaps[snaps.gsis_id.isna() & snaps.offense_pct.gt(0)]
        .groupby("position")
        .size()
        .to_dict()
    )
    # Preserve the existing Stage 1A source-processing contract: unknown IDs
    # remain unmapped; never invent identities, team assignments or zero stats.
    # The exact losses are retained in certified source provenance.
    coverage = {
        **meta["snaps"],
        "source_id": "participation_mapping",
        "unmapped_positive_offensive_snap_rows": unmapped,
        "handling": "Existing core drops unlinked snap IDs; box observations remain observed/missing as supplied",
        "preparation_code_sha256": sha(Path(__file__)),
    }
    snaps = snaps.dropna(subset=["gsis_id"]).rename(
        columns={
            "gsis_id": "player_id",
            "player": "player_display_name",
            "opponent": "opponent_team",
            "game_type": "season_type",
        }
    )
    snaps = snaps[
        [
            "player_id",
            "season",
            "week",
            "game_id",
            "season_type",
            "player_display_name",
            "position",
            "team",
            "opponent_team",
            "offense_pct",
        ]
    ]
    if snaps.duplicated(["player_id", "season", "week"]).any():
        raise ValueError("Duplicate participation identity")
    ff = read("opportunity")
    ff.season = ff.season.astype(int)
    ff.week = ff.week.astype(int)
    ff = ff[
        [
            "player_id",
            "season",
            "week",
            "receptions_exp",
            "rec_yards_gained_exp",
            "pass_completions_exp",
            "pass_yards_gained_exp",
            "rush_yards_gained_exp",
        ]
    ].dropna(subset=["player_id"])
    ngs = read("ngs").rename(
        columns={
            "player_gsis_id": "player_id",
            "completion_percentage_above_expectation": "completion_pct_above_expectation",
        }
    )
    ngs = ngs[
        [
            "player_id",
            "season",
            "week",
            "completion_pct_above_expectation",
            "avg_time_to_throw",
        ]
    ].dropna(subset=["player_id"])
    aux = ff.merge(
        snaps, on=["player_id", "season", "week"], how="outer", validate="one_to_one"
    ).merge(ngs, on=["player_id", "season", "week"], how="outer", validate="one_to_one")
    context = []
    for side, other, flag in [("home", "away", 1), ("away", "home", 0)]:
        g = schedule.copy()
        g["team_implied_total"] = (
            g.total_line + (g.spread_line if flag else -g.spread_line)
        ) / 2
        g["opp_implied_total"] = g.total_line - g.team_implied_total
        g["indoor"] = g.roof.map({"dome": 1, "closed": 1, "outdoors": 0, "open": 0})
        g["is_home"] = flag
        context.append(
            g[
                [
                    "season",
                    "week",
                    side + "_team",
                    other + "_team",
                    "team_implied_total",
                    "opp_implied_total",
                    "total_line",
                    "indoor",
                    "is_home",
                ]
            ].rename(columns={side + "_team": "team", other + "_team": "opponent_team"})
        )
    fresh = build_player_features(
        box,
        aux=aux,
        game_context=pd.concat(context),
        schedule=schedule,
        team_stats=read("team_stats"),
        data_cutoff=cutoff,
    )
    features = pd.concat([old[old.season.lt(season)], fresh], ignore_index=True)
    # Missing latest completed fixture observations may not silently become old features.
    due = schedule[
        schedule.season.eq(season)
        & schedule.week.lt(target_week)
        & (schedule.kickoff_at + pd.Timedelta(hours=8)).lt(cutoff)
    ]
    if due.completed_at.isna().any():
        raise ValueError(
            "Past fixture lacks confirmed completion in source; no stale forecast publication"
        )
    team_rows = read("team_stats")
    required_pairs = {
        (g.game_id, t) for g in due.itertuples() for t in [g.home_team, g.away_team]
    }
    actual_pairs = set(zip(team_rows.game_id, team_rows.team))
    if not required_pairs <= actual_pairs:
        raise ValueError("Completed team-game totals missing from refreshed source")
    completed = schedule[
        schedule.season.eq(season)
        & schedule.completed_at.lt(cutoff)
        & schedule.week.lt(target_week)
    ]
    if not set(completed.game_id) <= set(features.game_id):
        raise ValueError("Completed fixture missing from refreshed features")
    depth = pd.read_parquet(sources / "depth.parquet")
    depth["observed"] = pd.to_datetime(depth.dt, utc=True)
    depth = depth[depth.observed.le(now)]
    depth = depth[depth.observed.eq(depth.groupby("team")["observed"].transform("max"))]
    if admission is not None:
        upcoming = schedule[
            schedule.season.eq(season)
            & schedule.week.eq(target_week)
            & schedule.kickoff_at.gt(now + pd.Timedelta(minutes=60))
        ]
        teams = set(upcoming.home_team) | set(upcoming.away_team)
        require_current_depth(depth, teams, receipt["settlement_cutoff"])
    qb = depth[depth.pos_abb.eq("QB") & depth.pos_rank.eq(1)][
        ["team", "gsis_id"]
    ].drop_duplicates()
    if qb.team.duplicated().any():
        raise ValueError("Ambiguous QB1 evidence")
    features.to_parquet(work / "features.filtered.parquet", index=False)
    schedule.to_parquet(work / "schedule.filtered.parquet", index=False)
    shutil.copyfile(
        sources / "roster.parquet", work / "roster_2026.quarantined.parquet"
    )
    (work / "roster_source.json").write_text(encoded(meta["roster"]))
    (work / "generation.json").write_text(
        encoded(
            {
                "completed_before": cutoff.isoformat(),
                "prediction_at": now.isoformat(),
                "qb_starters": dict(zip(qb.team, qb.gsis_id)),
            }
        )
    )
    # Existing builder expects provenance documents one directory above its inputs.
    (work.parent / "source-gate.json").write_text(encoded(meta["player_stats"]))
    (work.parent / "required-source-report.json").write_text(
        encoded(
            [{"name": k, **v} for k, v in meta.items() if k != "player_stats"]
            + [{**coverage, "name": "participation_mapping"}]
        )
    )
    output = ROOT / "research_inference_releases" / release_id
    if admission is not None:
        from .build_release import build_prepared

        if model_parent is not None:
            source_parent = (ROOT / model_parent).resolve()
            source_parent.relative_to(ROOT)
            parent_manifest = validate_manifest(source_parent, ROOT)
            namespace = {
                **build_prepared.__globals__,
                "resolve_release": lambda repo: (
                    source_parent / "data",
                    parent_manifest,
                ),
            }
            builder = FunctionType(
                build_prepared.__code__,
                namespace,
                build_prepared.__name__,
                build_prepared.__defaults__,
                build_prepared.__closure__,
            )
            builder(work, output, admission)
        else:
            build_prepared(work, output, admission)
    elif model_parent is None:
        prepare(work, output)
    else:
        parent_path = (ROOT / model_parent).resolve()
        parent_path.relative_to(ROOT)
        parent_manifest = validate_manifest(parent_path, ROOT)
        namespace = {
            **prepare.__globals__,
            "resolve_release": lambda repo: (parent_path / "data", parent_manifest),
        }
        isolated = FunctionType(
            prepare.__code__,
            namespace,
            prepare.__name__,
            prepare.__defaults__,
            prepare.__closure__,
        )
        isolated(work, output)
    return output
