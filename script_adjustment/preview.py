"""Numerical overlays stay outside certified slates, recommendation ranking and prices."""

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from research_platform.inference_builder import candidate_state
from research_platform.inference_release import resolve_research_release
from scripts.build_slate import MARKETS as LABELS
from weekly_learning.store import ROOT, Store, encoded, sha

from .data import team_panel
from .players import Z, allocate, innovations, player_histories


def requests_for(fixtures, season, week):
    rows = []
    for g in fixtures:
        for team, opp, home in [
            (g["home_team"], g["away_team"], 1),
            (g["away_team"], g["home_team"], 0),
        ]:
            rows.append(
                {
                    "game_id": g["game_id"],
                    "team": team,
                    "opponent": opp,
                    "season": season,
                    "week": week,
                    "kickoff_at": pd.Timestamp(g["kickoff_at"]),
                    "is_home": home,
                }
            )
    return pd.DataFrame(rows)


def predict_teams(model, games, cells, requests, as_of, admission=None):
    state = team_panel(games, cells, requests, as_of=as_of, admission=admission)
    current = state[state.game_id.isin(requests.game_id)].copy()
    if current.empty or len(current) != len(requests):
        raise ValueError("Incomplete future fixture states")
    if not current.history_available_at.lt(pd.Timestamp(as_of)).all():
        raise ValueError("Unavailable future fixture evidence")
    return model["script"].predict(model["outcome"].predict(current))


def overlay(directory, manifest, challenger, games, cells, *, now=None, admission=None):
    directory = Path(directory)
    now = pd.Timestamp(now or datetime.now(UTC))
    if pd.Timestamp(challenger["artifact_created_at"]) > now:
        raise ValueError("Challenger artifact was not available at overlay time")
    slate = pd.read_parquet(directory / "slate.parquet")
    slate = slate[slate.projection_status.eq("complete")].copy()
    allowed = {
        g
        for g, k in manifest["game_kickoffs"].items()
        if now < pd.Timestamp(k) - pd.Timedelta(minutes=60)
    }
    slate = slate[slate.game_id.isin(allowed)]
    if slate.empty:
        raise ValueError("No complete forecasts before T-60; no backdated overlay")
    features = pd.read_parquet(directory / "features.parquet")
    schedule = pd.read_parquet(directory / "schedule.parquet")
    cutoff = pd.Timestamp(manifest["feature_data_cutoff"])
    if (
        features.completed_at.isna().any()
        or not pd.to_datetime(features.completed_at, utc=True).lt(cutoff).all()
    ):
        raise ValueError("Uncertified feature timing")
    request_records = []
    for gid, g in slate.groupby("game_id"):
        s = schedule[schedule.game_id.eq(gid)].iloc[0]
        request_records.append(
            {
                "game_id": gid,
                "home_team": s.home_team,
                "away_team": s.away_team,
                "kickoff_at": manifest["game_kickoffs"][gid],
            }
        )
    requests = requests_for(
        request_records, int(slate.season.iloc[0]), int(slate.week.iloc[0])
    )
    team = predict_teams(
        challenger["team"], games, cells, requests, now, admission=admission
    )
    starters = json.loads((directory / "qb_starters.json").read_text())["starters"]
    states = candidate_state(
        features,
        schedule,
        manifest["prediction_at"],
        manifest["feature_data_cutoff"],
        starters,
    )
    reverse = {v: k for k, v in LABELS.items()}
    base = slate.rename(columns={"projection": "baseline"}).copy()
    base["market"] = base.market.map(reverse)
    # Exact accepted player/team identity comes from the certified slate, not old team history.
    required = {
        c for model in challenger["corrections"].values() for c in model.columns
    } | {"player_display_name"}
    extras = sorted(
        c for c in required if c in states and c not in base and c != "player_id"
    )
    base = base.merge(
        states[["player_id"] + [c for c in extras if c != "player_id"]],
        on="player_id",
        validate="many_to_one",
    )
    base["y"] = np.nan
    identities = base[
        ["player_id", "game_id", "team", "position", "season", "week"]
    ].drop_duplicates()
    identities["kickoff_at"] = identities.game_id.map(manifest["game_kickoffs"]).map(
        pd.Timestamp
    )
    identities["completed_at"] = pd.NaT
    identities["stats_observed"] = False
    identities["offense_pct"] = np.nan
    history = features[features.player_id.isin(identities.player_id)]
    operational_available = None
    if admission is not None:
        from weekly_learning.admission import validate_receipt
        from weekly_learning.engine import POLICY

        receipt = validate_receipt(ROOT, admission, json.loads(POLICY.read_text()))
        operational_available = {
            g["game_id"]: receipt["created_at"] for g in receipt["allowed_games"]
        }
    histories = player_histories(
        pd.concat([history, identities], ignore_index=True),
        operational_available,
        fixtures=requests[["game_id", "team", "season", "week", "kickoff_at"]],
    )
    future = histories[histories.game_id.isin(allowed)].merge(
        identities[["game_id", "player_id", "team"]],
        on=["game_id", "player_id", "team"],
        validate="many_to_one",
    )
    allocations, coherence = allocate(future, team, challenger["shares"])
    out = innovations(base, allocations)
    out["delta"] = 0.0
    out["adjustment_status"] = "missing_context_baseline_retained"
    out["cap_applied"] = False
    p = challenger["protocol"]
    for market, g in out.groupby("market"):
        model = challenger["corrections"].get(market)
        if model is None:
            continue
        valid = g.adjustment_features_available & g[model.columns].notna().all(axis=1)
        indices = g.index[valid]
        if not len(indices):
            continue
        raw, contrib = model.predict(g.loc[indices])
        cap = np.maximum(
            abs(g.loc[indices, "baseline"]) * p["maximum_adjustment_fraction"],
            p["maximum_adjustment_floors"][market],
        )
        out.loc[indices, "delta"] = np.clip(raw, -cap, cap)
        out.loc[indices, "cap_applied"] = np.abs(raw) > cap
        out.loc[indices, "adjustment_status"] = "EXPERIMENTAL_NOT_SELECTED"
        for j, name in enumerate(Z):
            out.loc[indices, "contribution_" + name] = contrib[:, j]
    out["adjusted"] = out.baseline + out.delta
    from stage1b.data import MARKETS

    count = out.market.map(lambda m: MARKETS[m][3])
    out.loc[count, "adjusted"] = out.loc[count, "adjusted"].clip(lower=0)
    out["delta"] = out.adjusted - out.baseline
    out["baseline_prediction_at"] = out.prediction_at
    out["prediction_at"] = now
    out["baseline_release_id"] = manifest["release_id"]
    for state in ["leading", "tied", "trailing"]:
        lookup = team.set_index(["game_id", "team"])
        cat = out.market.map(lambda m: MARKETS[m][2])
        weighted = []
        for row, category in zip(out.itertuples(), cat):
            t = lookup.loc[(row.game_id, row.team)]
            numerator = (
                t["carries_" + state]
                if category == "carries"
                else t["attempts_" + state]
            )
            denominator = (
                t.expected_carries if category == "carries" else t.expected_attempts
            )
            weighted.append(
                row.allocated_opportunities * numerator / denominator
                if denominator > 0
                else np.nan
            )
        out["weighted_player_opportunities_" + state] = weighted
    return out, team, coherence


def build_previews(output, panel, cells, source):
    output = Path(output)
    model = joblib.load(output / "challenger.joblib")
    raw = ROOT / "research_inputs/script_adjustment/pbp-20261121-v2/games.parquet"
    games = pd.read_parquet(raw)
    directory, release = resolve_research_release(ROOT)
    preds, teams, coherence = overlay(directory, release, model, games, cells)
    preds.to_parquet(output / "reference_week11_adjustments.parquet", index=False)
    teams.to_parquet(output / "reference_week11_teams.parquet", index=False)
    coherence.to_parquet(output / "reference_week11_coherence.parquet", index=False)
    plans = sorted(
        (ROOT / "weekly_learning_state/plans").glob("week12-fixtures-*/plan.json")
    )
    if not plans:
        raise ValueError("Week12 verified metadata plan unavailable")
    plan = plans[-1]
    Store(ROOT / "weekly_learning_state").validate(plan.parent)
    spec = json.loads(plan.read_text())
    now = pd.Timestamp.now(tz="UTC")
    req = requests_for(spec["fixtures"], spec["season"], spec["week"])
    future = predict_teams(model["team"], games, cells, req, now)
    future["preview_tier"] = "EARLY_TEAM_ONLY_NO_CERTIFIED_PLAYER_CANDIDATE"
    future.to_parquet(output / "week12_team_preview.parquet", index=False)
    status = {
        "prediction_at": now.isoformat(),
        "fixture_plan": str(plan.relative_to(ROOT)),
        "fixture_plan_sha256": sha(plan),
        "fixtures": len(spec["fixtures"]),
        "forecast_release_selected": False,
        "player_candidate_certified": False,
        "player_forecasts_generated": False,
        "blocker": "Week11 operational settlement gate is closed until2026-11-24T12:00Z and fresh Week12 roster/depth/inference admission are not yet available; no Week11 eligibility recycled",
        "history": "Existing permitted2026weeks1-10 only; no Week11 outcomes accessed",
        "preview": "Team predictions only, captured earlier than T-60 and not a certified player slate",
    }
    (output / "week12_status.json").write_text(encoded(status))
