"""Optional prospective sidecars; never selects a forecast or promotes a model."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

from scripts.forecast_features import schedule_times
from weekly_learning.admission import validate_receipt
from weekly_learning.engine import POLICY
from weekly_learning.store import ROOT, sha

from .data import COLUMNS, aggregate
from .metrics import point


def current_inputs(store, admission, experiment):
    receipt = validate_receipt(ROOT, admission, json.loads(POLICY.read_text()))
    key = "admitted-" + sha(admission)[:20]
    target = store.root / "script_inputs" / key
    if target.exists():
        store.validate(target)
        return pd.read_parquet(target / "games.parquet"), pd.read_parquet(
            target / "cells.parquet"
        )
    base = ROOT / json.loads((experiment / "manifest.json").read_text())["input_bundle"]
    games = pd.read_parquet(base / "games.parquet", filters=[("season", "<", 2026)])
    cells = pd.read_parquet(base / "cells.parquet", filters=[("season", "<", 2026)])
    url = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
    with tempfile.TemporaryDirectory(prefix="script-admitted-pbp-") as tmp:
        path = Path(tmp) / "pbp.parquet"
        size = 0
        with requests.get(url, stream=True, timeout=(5, 60)) as r:
            r.raise_for_status()
            with path.open("xb") as f:
                for block in r.iter_content(1024 * 1024):
                    size += len(block)
                    if size > 64 * 1024 * 1024:
                        raise ValueError("Admitted PBP exceeds64MiB; no retry")
                    f.write(block)
        now = datetime.now(UTC).isoformat()
        provenance = {
            "url": url,
            "retrieved_at": now,
            "sha256": sha(path),
            "admission_sha256": sha(admission),
            "through_week": receipt["through_week"],
        }
        raw = pd.read_parquet(
            path,
            columns=COLUMNS + ["drive", "no_huddle"],
            filters=[
                ("season", "==", 2026),
                ("week", "<=", receipt["through_week"]),
                ("season_type", "==", "REG"),
            ],
        )
        added = aggregate(raw, admission=admission)
        required = {g["game_id"] for g in receipt["allowed_games"]}
        if not required <= set(added.game_id):
            raise ValueError("Admitted final games absent from PBP; no stale fallback")
        schedule = schedule_times(
            pd.read_parquet(
                ROOT / receipt["source_path"] / "schedule.parquet",
                filters=[
                    ("season", "==", 2026),
                    ("week", "<=", receipt["through_week"]),
                    ("game_type", "==", "REG"),
                ],
            )
        )
        live = (
            raw[
                raw.play_type.isin(["pass", "run", "qb_kneel", "qb_spike"])
                & raw.two_point_attempt.ne(1)
                & raw.posteam.notna()
                & raw.defteam.notna()
            ]
            .sort_values(["game_id", "play_id"])
            .copy()
        )
        live["gap"] = (
            live.groupby(
                ["game_id", "posteam", "drive", "qtr"]
            ).game_seconds_remaining.shift(1)
            - live.game_seconds_remaining
        )
        valid = (
            live.score_differential.abs().le(7)
            & live.qtr.le(3)
            & live.gap.gt(0)
            & live.gap.le(60)
        )
        live["pace_sum"] = live.gap.where(valid, 0)
        live["pace_n"] = valid.astype(int)
        volume = (
            live.groupby(["game_id", "posteam"], as_index=False)
            .agg(
                plays=("play_id", "size"),
                dropbacks=("pass_attempt", "sum"),
                rushes=("rush_attempt", "sum"),
                no_huddle=("no_huddle", "sum"),
                pace_sum=("pace_sum", "sum"),
                pace_n=("pace_n", "sum"),
            )
            .rename(columns={"posteam": "team"})
        )
        from stage1c.contracts import team

        volume["team"] = volume.team.map(team)
        s = volume.merge(schedule, on="game_id", validate="many_to_one")
        s["opponent"] = np.where(s.team.eq(s.home_team), s.away_team, s.home_team)
        s["is_home"] = s.team.eq(s.home_team).astype(int)
        s["points_for"] = np.where(s.is_home, s.home_score, s.away_score)
        s["points_against"] = np.where(s.is_home, s.away_score, s.home_score)
        s["margin"] = s.points_for - s.points_against
        s["observed_available_at"] = now
        columns = list(games.columns) + ["observed_available_at"]
        s = s[columns]
        # Protected game counts must agree with the already admitted official team totals.
        totals = added.pivot_table(
            index=["game_id", "team"],
            columns="action",
            values="n",
            aggfunc="sum",
            fill_value=0,
        )
        official = pd.read_parquet(
            ROOT / receipt["source_path"] / "team_stats.parquet",
            filters=[
                ("season", "==", 2026),
                ("week", ">=", 11),
                ("week", "<=", receipt["through_week"]),
            ],
        )
        for row in official.itertuples():
            value = totals.loc[(row.game_id, row.team)]
            if (
                value.get("attempt", 0) != row.attempts
                or sum(value.get(k, 0) for k in ["designed_carry", "scramble", "kneel"])
                != row.carries
            ):
                raise ValueError(
                    "Protected PBP/official opportunity mismatch; experimental capture blocked"
                )
        games = pd.concat([games, s], ignore_index=True)
        cells = pd.concat([cells, added], ignore_index=True)
    with store.transaction():
        target = store.publish(
            "script_inputs",
            key,
            frames={"games.parquet": games, "cells.parquet": cells},
            documents={"source.json": provenance},
        )
    return games, cells


def capture_overlay(store, directory, manifest):
    from .preview import overlay
    from .runner import DEFAULT
    from .validate import validate

    target = store.root / "script_captures" / manifest["release_id"]
    if target.exists():
        store.validate(target)
        return target
    validate(DEFAULT)
    expected = json.loads((DEFAULT / "manifest.json").read_text())["champion_models"]
    if {k: v["sha256"] for k, v in manifest["models"].items()} != expected:
        raise ValueError("Experimental model trained against a different champion")
    now = pd.Timestamp.now(tz="UTC")
    if not all(
        now < pd.Timestamp(t) - pd.Timedelta(minutes=60)
        for t in manifest["game_kickoffs"].values()
    ):
        raise ValueError("No late/backdated experimental capture")
    admission = Path(directory) / "admission.json"
    model = joblib.load(DEFAULT / "challenger.joblib")
    if admission.exists():
        games, cells = current_inputs(store, admission, DEFAULT)
    else:
        base = (
            ROOT / json.loads((DEFAULT / "manifest.json").read_text())["input_bundle"]
        )
        games = pd.read_parquet(base / "games.parquet")
        cells = pd.read_parquet(base / "cells.parquet")
    now = pd.Timestamp.now(tz="UTC")
    if not all(
        now < pd.Timestamp(t) - pd.Timedelta(minutes=60)
        for t in manifest["game_kickoffs"].values()
    ):
        raise ValueError("Experimental inputs arrived after activation cutoff")
    predictions, teams, coherence = overlay(
        directory,
        manifest,
        model,
        games,
        cells,
        now=now,
        admission=admission if admission.exists() else None,
    )
    frozen = pd.Timestamp.now(tz="UTC")
    if not all(
        frozen < pd.Timestamp(t) - pd.Timedelta(minutes=60)
        for t in manifest["game_kickoffs"].values()
    ):
        raise ValueError("Experimental forecast finished after decision cutoff")
    meta = {
        "baseline_release_id": manifest["release_id"],
        "baseline_manifest_sha256": sha(Path(directory) / "manifest.json"),
        "challenger_manifest_sha256": sha(DEFAULT / "manifest.json"),
        "challenger_sha256": sha(DEFAULT / "challenger.joblib"),
        "prediction_at": now.isoformat(),
        "frozen_at": frozen.isoformat(),
        "game_kickoffs": manifest["game_kickoffs"],
        "activation": False,
        "selected": False,
        "tier": "genuine_predecision_experimental_capture_no_promotion",
        "benchmark_final_period_used_for_selection": False,
    }
    with store.transaction():
        return store.publish(
            "script_captures",
            manifest["release_id"],
            frames={
                "predictions.parquet": predictions,
                "teams.parquet": teams,
                "coherence.parquet": coherence,
            },
            documents={"capture.json": meta},
        )


def try_capture(store, directory, manifest):
    try:
        return capture_overlay(store, directory, manifest)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AssertionError,
        requests.RequestException,
    ) as e:
        with store.transaction():
            store.audit(
                "experimental_script_capture_blocked",
                {
                    "release_id": manifest["release_id"],
                    "reason": str(e),
                    "champion_unchanged": True,
                },
            )
        return None


def evaluate_captured(store, cycle_id, release_id, reconciled, admission_path=None):
    target = store.root / "script_evaluations" / cycle_id
    if target.exists():
        store.validate(target)
        return target
    capture = store.root / "script_captures" / release_id
    if not capture.exists():
        return None  # Never reconstruct historical experimental picks after results.
    store.validate(capture)
    meta = json.loads((capture / "capture.json").read_text())
    # Verify an authorised operational receipt before joining protected actual outcomes.
    baseline = store.root / "cycles" / cycle_id / "report.json"
    report = json.loads(baseline.read_text())
    sources = (
        Path(admission_path)
        if admission_path
        else store.root / "sources" / cycle_id / "operational_admission.json"
    )
    if not sources.exists():
        raise ValueError("No prospective settlement admission for script scoring")
    validate_receipt(ROOT, sources, json.loads(POLICY.read_text()))
    predictions = pd.read_parquet(capture / "predictions.parquet")
    from scripts.build_slate import MARKETS

    reverse = {v: k for k, v in MARKETS.items()}
    scores = reconciled[reconciled.status.eq("scored")].copy()
    scores["market"] = scores.market.map(lambda m: reverse.get(m, m))
    keys = ["game_id", "player_id", "market"]
    joined = predictions.merge(
        scores[
            keys
            + [
                "actual",
                "projection",
                "actual_team_attempts",
                "actual_team_carries",
                "actual_attempts",
                "actual_carries",
                "actual_targets",
                "actual_home_score",
                "actual_away_score",
            ]
        ],
        on=keys,
        validate="one_to_one",
    )
    if not np.allclose(joined.baseline, joined.projection):
        raise ValueError("Frozen champion comparison changed")
    from stage1b.data import MARKETS as CONFIG

    joined["actual_opportunities"] = [
        row["actual_" + CONFIG[row["market"]][2]] for row in joined.to_dict("records")
    ]
    joined["actual_team_opportunities"] = np.where(
        joined.market.str.contains("rushing"),
        joined.actual_team_carries,
        joined.actual_team_attempts,
    )
    from .metrics import attribution, team_metrics

    joined = attribution(joined.assign(y=joined.actual))
    from .runner import DEFAULT

    games, cells = current_inputs(store, sources, DEFAULT)
    frozen_team = pd.read_parquet(capture / "teams.parquet")
    current = games[games.game_id.isin(frozen_team.game_id)]
    counts = (
        cells[cells.game_id.isin(frozen_team.game_id)]
        .groupby(["game_id", "team", "cell"])
        .n.sum()
        .unstack(fill_value=0)
        .reindex(columns=range(15), fill_value=0)
    )
    counts.columns = ["cell_" + str(i) for i in counts.columns]
    actions = cells[cells.game_id.isin(frozen_team.game_id)].pivot_table(
        index=["game_id", "team"],
        columns="action",
        values="n",
        aggfunc="sum",
        fill_value=0,
    )
    actuals = current[["game_id", "team", "margin"]].merge(
        counts, on=["game_id", "team"], validate="one_to_one"
    )
    actuals["plays"] = actuals[["cell_" + str(i) for i in range(15)]].sum(axis=1)
    actuals = actuals.merge(actions, on=["game_id", "team"], validate="one_to_one")
    actuals["attempts"] = actuals["attempt"]
    actuals["carries"] = actuals[["designed_carry", "scramble", "kneel"]].sum(axis=1)
    target_cols = ["margin", "plays", "attempts", "carries"] + [
        "cell_" + str(i) for i in range(15)
    ]
    team_scored = frozen_team.drop(columns=target_cols, errors="ignore").merge(
        actuals[["game_id", "team"] + target_cols],
        on=["game_id", "team"],
        validate="one_to_one",
    )
    measured_team, reliability = team_metrics(team_scored)
    summary = []
    for market, g in joined.groupby("market"):
        summary.append(
            {
                "market": market,
                "baseline": point(g.actual, g.baseline),
                "experimental": point(g.actual, g.adjusted),
                "n": len(g),
            }
        )
    with store.transaction():
        return store.publish(
            "script_evaluations",
            cycle_id,
            frames={
                "joined.parquet": joined,
                "team_metrics.parquet": measured_team,
                "team_reliability.parquet": reliability,
            },
            documents={
                "report.json": {
                    "cycle_id": cycle_id,
                    "capture_manifest_sha256": sha(capture / "manifest.json"),
                    "settlement_report_sha256": sha(baseline),
                    "measured": summary,
                    "champion_retained": True,
                    "promotion": False,
                    "final_evaluation": "Monitoring only; does not spend or open the reserved untouched final period",
                    "capture": meta,
                    "operational_status": report["status"],
                }
            },
        )
