"""Replay current states through the existing frozen research methods; never fit models."""

import json
from functools import lru_cache
from pathlib import Path
from types import FunctionType

import joblib
import numpy as np
import pandas as pd

from scripts.build_slate import MARKETS as LABELS
from season_intelligence.data import STATS, history_features, market_data, team_features
from stage1b.data import MARKETS

from .enhanced_engine import DIRECTORY, EXPERIMENT, explain
from .weekly_serving import PROFILE, RELEASE


def _build(directory, profile):
    manifest = json.loads((directory / "manifest.json").read_text())
    prediction = pd.Timestamp(manifest["prediction_at"])
    built = json.loads((profile / "selection_build.json").read_text())["built_at"]
    if pd.Timestamp(built) < prediction or pd.Timestamp(built) > pd.Timestamp.now(
        tz="UTC"
    ):
        raise ValueError("Invalid selection-build timestamp")
    slate = pd.read_parquet(directory / "slate.parquet")
    complete = slate[slate.projection_status.eq("complete")].copy()
    complete["market"] = complete.market.map({v: k for k, v in LABELS.items()})
    source = pd.read_parquet(directory / "features.parquet")
    columns = list(
        dict.fromkeys(
            STATS
            + [
                "player_id",
                "game_id",
                "team",
                "opponent_team",
                "position",
                "season",
                "week",
                "kickoff_at",
                "completed_at",
                "stats_observed",
                "team_total_attempts",
                "team_total_carries",
                "team_total_targets",
                "sacks_suffered",
            ]
        )
    )
    source = source[columns].copy()
    for c in ["kickoff_at", "completed_at"]:
        source[c] = pd.to_datetime(source[c], utc=True)
    available = pd.concat(
        [source.completed_at, source.kickoff_at + pd.Timedelta(hours=36)], axis=1
    ).max(axis=1)
    # Preserve the existing research family's conservative publication assumption.
    source = source[available.lt(prediction)].copy()
    requests = (
        complete[
            ["player_id", "game_id", "team", "opponent", "position", "season", "week"]
        ]
        .drop_duplicates(["game_id", "player_id"])
        .rename(columns={"opponent": "opponent_team"})
    )
    requests["kickoff_at"] = requests.game_id.map(manifest["game_kickoffs"]).map(
        pd.Timestamp
    )
    requests["completed_at"] = pd.NaT
    requests["stats_observed"] = False
    for c in STATS:
        requests[c] = np.nan
    requests["is_home"] = requests.apply(
        lambda r: float(r.team == r.game_id.split("_")[-1]), axis=1
    )
    histories = history_features(pd.concat([source, requests], ignore_index=True))
    current = histories[histories.game_id.isin(complete.game_id.unique())].copy()
    if (
        not pd.to_datetime(current.history_available_at, utc=True)
        .dropna()
        .lt(prediction)
        .all()
    ):
        raise ValueError("Selection state contains data unavailable at forecast build")
    scope = dict(
        team_features.__globals__,
        CERTIFIED=directory,
        FILTERS=[
            ("season", "==", manifest["fixture_slate"]["season"]),
            ("week", "<", manifest["fixture_slate"]["week"]),
        ],
    )
    teams = FunctionType(team_features.__code__, scope)(source, requests)
    current = current.drop(
        columns=[c for c in teams if c in current and c not in ["game_id", "team"]]
    ).merge(teams, on=["game_id", "team"], how="left", validate="many_to_one")
    reference = pd.read_parquet(DIRECTORY / "forecasts.parquet")
    frozen = joblib.load(EXPERIMENT / "sunday_models.joblib")
    rows = []
    for market, base in complete.groupby("market", sort=True):
        target, _, opp, count = MARKETS[market]
        template = reference[reference.market.eq(market)].iloc[0].to_dict()
        states = market_data(current, market).set_index(["game_id", "player_id"])
        model = frozen["points"][market]
        model_states = states.loc[list(zip(base.game_id, base.player_id))]
        predictions = (
            model.predict(model_states)
            if template["point_admitted"]
            else base.projection.to_numpy()
        )
        if pd.Timestamp(model.fit_before) >= prediction:
            raise ValueError("Frozen research model contains unavailable training data")
        for r, candidate in zip(base.to_dict("records"), predictions, strict=True):
            state = states.loc[(r["game_id"], r["player_id"])]
            point = float(candidate)
            # A frozen policy is reused; no new challenger or parameter is selected here.
            d = {
                **template,
                **r,
                "market": market,
                "baseline": float(r["projection"]),
                "enhanced_projection": point,
                "projection_change": point - float(r["projection"]),
                "selection_built_at": built,
                "prediction_at": built,
                "original_baseline_prediction_at": manifest["prediction_at"],
                "kickoff_at": manifest["game_kickoffs"][r["game_id"]],
                "prices_verified": False,
                "history_n": float(state.history_n),
                "last3": float(state[target + "_last3"]),
                "last5": float(state[target + "_last5"]),
                "season_mean": float(state[target + "_season"]),
                "recent_opportunities": float(state[opp + "_last3"]),
                "recent_snap_share": float(state.offense_pct_last3),
                "workload5": float(state[opp + "_last5"]),
                "role_share3": float(state[opp + "_share3"]),
                "role_variability": float(state[opp + "_sd5"])
                / max(float(state[opp + "_last5"]), 1),
                "opponent_attempts_allowed": float(state.opp_allowed_attempts),
                "opponent_carries_allowed": float(state.opp_allowed_carries),
                "team_recent_plays": float(state.own_plays),
                "feature_cutoff": manifest["feature_data_cutoff"],
            }
            q = frozen["laws"][market].price(
                point, r["position"], count, max(0.5, np.floor(point) + 0.5)
            )
            d["q05"], d["q95"] = q["q05"], q["q95"]
            d["relative_width"] = (d["q95"] - d["q05"]) / max(abs(point), 1)
            d["why_pick"], d["principal_risk"] = explain(d)
            rows.append(d)
    frame = (
        pd.DataFrame(rows)
        .sort_values(["game_id", "player_id", "market"])
        .reset_index(drop=True)
    )
    if (
        len(frame) != len(complete)
        or frame.duplicated(["game_id", "player_id", "market"]).any()
    ):
        raise ValueError("Weekly selection population mismatch")
    schedule = pd.read_parquet(directory / "schedule.parquet")
    fixtures = schedule[schedule.game_id.isin(manifest["game_kickoffs"])].copy()
    fixtures["coverage_status"] = fixtures.game_id.map(
        lambda gid: (
            "Complete frozen forecasts"
            if gid in set(frame.game_id)
            else "ROOF SCENARIOS ONLY — pricing and selections withheld"
        )
    )
    return frame, fixtures.sort_values("kickoff_at")


@lru_cache(maxsize=4)
def _cached(directory, profile, fingerprint):
    return _build(Path(directory), Path(profile))


def build(directory=RELEASE, profile=PROFILE):
    from release_utils import sha256

    directory, profile = Path(directory), Path(profile)
    fingerprint = tuple(
        sha256(p)
        for p in [
            directory / "manifest.json",
            directory / "features.parquet",
            directory / "slate.parquet",
            directory / "schedule.parquet",
            profile / "selection_build.json",
            EXPERIMENT / "sunday_models.joblib",
            DIRECTORY / "forecasts.parquet",
        ]
    )
    frame, fixtures = _cached(str(directory), str(profile), fingerprint)
    return frame.copy(deep=True), fixtures.copy(deep=True)
