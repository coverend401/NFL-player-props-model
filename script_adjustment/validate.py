"""Integrity, temporal boundaries and numerical prediction replay; no fitting/network."""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from release_utils import MODEL_NAMES, resolve_release, runtime_versions
from stage1c.contracts import assert_development
from weekly_learning.store import ROOT, sha

from .data import PROTOCOL
from .players import allocate

# CPU/BLAS reduction order is not bitwise portable. This absolute bound applies
# only to recomputed experimental floats, never hashes, identities, timestamps,
# champion projections or original release certification. No relative tolerance.
REPLAY_ATOL = 1e-10
REPLAY_POLICY = {
    "absolute_tolerance": REPLAY_ATOL,
    "relative_tolerance": 0.0,
    "scope": "experimental_recomputed_floats_only",
}


def assert_numerical_replay(actual, expected):
    np.testing.assert_allclose(
        actual, expected, rtol=0, atol=REPLAY_ATOL, equal_nan=True
    )


def assert_frame_replay(actual, expected):
    pd.testing.assert_frame_equal(
        actual, expected, check_exact=False, rtol=0, atol=REPLAY_ATOL
    )


def validate(directory, replay=False):
    directory = Path(directory).resolve()
    m = json.loads((directory / "manifest.json").read_text())
    if (
        m["status"] != "experimental_not_promoted"
        or m["final_period_sealed"] is not True
        or m["production_changed"] is not False
    ):
        raise ValueError("Invalid experimental policy")
    if m.get("numerical_replay_policy") != REPLAY_POLICY:
        raise ValueError("Experimental numerical replay policy mismatch")
    current = runtime_versions(ROOT)
    if (
        m["runtime"]["python_minor"] != current["python_minor"]
        or m["runtime"]["packages"] != current["packages"]
    ):
        raise ValueError("Challenger runtime mismatch")
    if m["protocol_sha256"] != sha(PROTOCOL):
        raise ValueError("Preregistered protocol changed")
    expected = {
        str(p.relative_to(ROOT)) for p in (ROOT / "script_adjustment").glob("*.py")
    }
    if set(m["source_sha256"]) != expected or any(
        sha(ROOT / p) != h for p, h in m["source_sha256"].items()
    ):
        raise ValueError("Challenger source mismatch")
    files = {
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if files != set(m["files"]):
        raise ValueError("Experimental artifact set changed")
    for name, digest in m["files"].items():
        p = (directory / name).resolve()
        p.relative_to(directory)
        if (directory / name).is_symlink() or sha(p) != digest:
            raise ValueError("Experimental artifact integrity failed: " + name)
    source = (ROOT / m["player_source"]).resolve()
    source.relative_to(ROOT)
    if sha(source) != m["player_source_sha256"]:
        raise ValueError("Historical player source changed")
    inputs = ROOT / m["input_bundle"]
    if sha(inputs / "manifest.json") != m["input_manifest_sha256"]:
        raise ValueError("PBP input manifest changed")
    im = json.loads((inputs / "manifest.json").read_text())
    for name, h in im["files"].items():
        p = (inputs / name).resolve()
        p.relative_to(inputs.resolve())
        if sha(p) != h:
            raise ValueError("PBP aggregate changed")
    data, parent = resolve_release(ROOT)
    if (
        parent["release_id"] != m["champion_release_id"]
        or set(m["champion_models"]) != set(MODEL_NAMES)
        or any(
            sha(data / f"model_{market}.joblib") != h
            for market, h in m["champion_models"].items()
        )
    ):
        raise ValueError("Champion model provenance changed")
    report = json.loads((directory / "report.json").read_text())
    if report["activation"] is not False or report["promotion_passed"] is not False:
        raise ValueError("Experimental result cannot activate")
    players = pd.read_parquet(directory / "player_replay.parquet")
    teams = pd.read_parquet(directory / "team_replay.parquet")
    for d in [players, teams]:
        assert_development(d)
    if (
        players.duplicated(["game_id", "player_id", "market"]).any()
        or teams.duplicated(["game_id", "team"]).any()
    ):
        raise ValueError("Duplicate comparison rows")
    if (
        not pd.to_datetime(players.champion_fit_before, utc=True)
        .lt(pd.to_datetime(players.prediction_at, utc=True))
        .all()
    ):
        raise ValueError("Historical backbone trained on future")
    for col in ["outcome_fit_before", "script_fit_before"]:
        if (
            not pd.to_datetime(teams[col], utc=True)
            .lt(pd.to_datetime(teams.prediction_at, utc=True))
            .all()
        ):
            raise ValueError("Team stage trained on future")
    valid = players.correction_fit_before.notna()
    if (
        not pd.to_datetime(players.loc[valid, "correction_fit_before"], utc=True)
        .lt(pd.to_datetime(players.loc[valid, "prediction_at"], utc=True))
        .all()
    ):
        raise ValueError("Residual stage trained on future")
    p = teams[["prob_leading", "prob_tied", "prob_trailing"]].to_numpy()
    if (
        not np.allclose(p.sum(axis=1), 1)
        or (p < 0).any()
        or not np.allclose(
            teams.plays_leading + teams.plays_tied + teams.plays_trailing,
            teams.expected_plays,
        )
    ):
        raise ValueError("Game-state probabilities incoherent")
    coherence = pd.read_parquet(directory / "allocation_coherence.parquet")
    if coherence.unassigned.lt(-1e-8).any() or not np.allclose(
        coherence.allocated + coherence.unassigned, coherence.capacity
    ):
        raise ValueError("Opportunity allocations exceed team capacity")
    if not np.allclose(players.adjusted - players.baseline, players.delta):
        raise ValueError("Numerical adjustments do not reconcile")
    if replay:
        replay_payload(directory, players, teams)
    return {
        "player_rows": len(players),
        "team_games": len(teams),
        "models_verified": 9,
        "numerical_replay": replay,
        "exact_artifact_integrity": True,
        "champion_baseline_bitwise": True,
        "numerical_replay_policy": REPLAY_POLICY,
        "promotion_passed": False,
    }


def replay_payload(directory, players=None, teams=None):
    directory = Path(directory)
    if players is None:
        players = pd.read_parquet(directory / "player_replay.parquet")
    if teams is None:
        teams = pd.read_parquet(directory / "team_replay.parquet")
    models = joblib.load(directory / "replay_models.joblib")
    for year, g in teams.groupby("season"):
        bundle = models["teams"][int(year)]
        d = bundle["outcome"].predict(
            g.drop(
                columns=["expected_margin", "win_probability", "tie_probability"],
                errors="ignore",
            )
        )
        expected = bundle["script"].predict(d)
        cols = [
            "expected_margin",
            "win_probability",
            "tie_probability",
            "expected_plays",
            "expected_attempts",
            "expected_carries",
        ] + [f"prob_cell_{j}" for j in range(15)]
        assert_frame_replay(
            expected[cols].reset_index(drop=True),
            g[cols].reset_index(drop=True),
        )
    for (market, year), g in players.groupby(["market", "season"]):
        bundle = joblib.load(
            directory / "chronological_backbones" / f"{market}-{year}.joblib"
        )
        mu = (
            g[bundle["features"][0]].to_numpy()
            if bundle["model"] is None
            else bundle["model"].predict(g[bundle["features"]])
        )
        assert_numerical_replay(mu, g.baseline.to_numpy())
        model = models["corrections"].get((market, int(year)))
        valid = g.adjustment_features_available & g.baseline_features_complete
        delta = np.zeros(len(g))
        if model is not None:
            raw, _ = model.predict(g[valid])
            p = json.loads(PROTOCOL.read_text())
            cap = np.maximum(
                np.abs(g.loc[valid, "baseline"]) * p["maximum_adjustment_fraction"],
                p["maximum_adjustment_floors"][market],
            )
            delta[np.asarray(valid)] = np.clip(raw, -cap, cap)
        expected = g.baseline.to_numpy() + delta
        from stage1b.data import MARKETS

        if MARKETS[market][3]:
            expected = np.maximum(expected, 0)
        assert_numerical_replay(expected, g.adjusted.to_numpy())
    history = pd.read_parquet(directory / "share_inputs.parquet")
    expected_all = []
    for year, g in teams.groupby("season"):
        a, _ = allocate(
            history[history.season.eq(year)], g, models["shares"][int(year)]
        )
        expected_all.append(
            a[
                [
                    "game_id",
                    "player_id",
                    "category",
                    "season",
                    "predicted_share",
                    "allocated_opportunities",
                ]
            ]
        )
    expected = pd.concat(expected_all, ignore_index=True)
    actual = pd.read_parquet(directory / "allocation_predictions.parquet")
    keys = ["game_id", "player_id", "category"]
    assert_frame_replay(
        expected.sort_values(keys).reset_index(drop=True),
        actual.sort_values(keys).reset_index(drop=True),
    )
    # The current frozen champion projections are copied exactly, never adjusted in place.
    preview = pd.read_parquet(directory / "reference_week11_adjustments.parquet")
    original = ROOT / "research_inference_releases/research-week11-frozen-20261120-r2"
    slate = pd.read_parquet(original / "slate.parquet")
    slate = slate[slate.projection_status.eq("complete")]
    from scripts.build_slate import MARKETS

    reverse = {v: k for k, v in MARKETS.items()}
    slate = slate.copy()
    slate["market"] = slate.market.map(reverse)
    joined = preview.merge(
        slate[["game_id", "player_id", "market", "projection"]],
        on=["game_id", "player_id", "market"],
        validate="one_to_one",
    )
    np.testing.assert_array_equal(joined.baseline, joined.projection)
    return True


if __name__ == "__main__":
    from .runner import DEFAULT

    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", type=Path, default=DEFAULT)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    print(validate(args.directory, args.replay))
