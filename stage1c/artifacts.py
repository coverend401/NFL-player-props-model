"""Hash, runtime, semantic and full model-replay checks for C0–C2 archives."""

import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from stage1b.artifacts import digest, runtime
from stage1b1.artifacts import (
    source_hashes as frozen_sources,
    validate as validate_baseline,
)
from stage1c.contracts import assert_development, FINAL
from stage1b.data import MARKETS, feature_columns
from stage1c.context import FAMILIES
from stage1b.metrics import binary_scores


def sources(root):
    root = Path(root)
    d = frozen_sources(root)
    d.update(
        {
            str(p.relative_to(root)): digest(p)
            for p in sorted(root.glob("stage1c/*"))
            if p.suffix in [".py", ".json"]
        }
    )
    return d


def validate(directory, root):
    directory = Path(directory).resolve()
    root = Path(root).resolve()
    m = json.loads((directory / "manifest.json").read_text())
    p = json.loads((root / "stage1c/protocol.json").read_text())
    if m["source_hashes"] != sources(root) or m["runtime"] != runtime(root):
        raise ValueError("Research source/runtime mismatch")
    if (
        not m["final_period_sealed"]
        or m["status"] != "passed"
        or m["scope"] != "C0-C2 research only"
    ):
        raise ValueError("Unvalidated/unsealed archive")
    base = root / "experiments/stage1b1" / p["baseline_experiment"]
    validate_baseline(base, root)
    if (
        digest(base / "manifest.json") != m["baseline_manifest_sha256"]
        or digest(root / p["input_bundle"] / "manifest.json")
        != m["input_manifest_sha256"]
    ):
        raise ValueError("Frozen baseline/input changed")
    im = json.loads((root / p["input_bundle"] / "manifest.json").read_text())
    if set(im["files"]) != {"team_games.parquet", "position_totals.parquet"}:
        raise ValueError("Incomplete input manifest")
    for name, h in im["files"].items():
        if "/" in name or digest(root / p["input_bundle"] / name) != h:
            raise ValueError("Input payload changed")
    paths = {
        str(x.relative_to(directory))
        for x in directory.rglob("*")
        if x.is_file() and x.name != "manifest.json"
    }
    if paths != set(m["files"]):
        raise ValueError("Missing/unexpected experiment payload")
    for name, h in m["files"].items():
        raw = directory / name
        path = raw.resolve()
        if raw.is_symlink() or directory not in path.parents or digest(path) != h:
            raise ValueError("Experiment payload mismatch")
    if json.loads((directory / "protocol.json").read_text()) != p:
        raise ValueError("Protocol changed")
    f = pd.read_parquet(directory / "forecasts.parquet")
    q = pd.read_parquet(directory / "probes.parquet")
    ctx = pd.read_parquet(directory / "context.parquet")
    old = pd.read_parquet(base / "forecasts.parquet")
    assert_development(f)
    if (
        set(f.version) != {"stage1b1", *p["families"]}
        or f.duplicated(["row_id", "version"]).any()
    ):
        raise ValueError("Invalid forecast versions")
    for v, g in f.groupby("version"):
        if set(g.row_id) != set(old.row_id):
            raise ValueError("Ablation population changed")
        j = g.merge(
            old[["row_id", "y", "prediction_at", "completed_at"]],
            on="row_id",
            suffixes=("", "_old"),
            validate="one_to_one",
        )
        if not (
            j.y.eq(j.y_old)
            & j.prediction_at.eq(j.prediction_at_old)
            & j.completed_at.eq(j.completed_at_old)
        ).all():
            raise ValueError("Ablation outcomes/timing changed")
    new = f[f.version != "stage1b1"]
    if not (
        (new.history_available_at < new.prediction_at)
        & (new.context_information_at < new.prediction_at)
        & (new.prediction_at < new.completed_at)
    ).all():
        raise ValueError("Future context/player information")
    if (
        not np.isfinite(f[["projection", "lower90", "upper90", "interval_score"]])
        .all()
        .all()
        or f.lower90.gt(f.upper90).any()
    ):
        raise ValueError("Invalid forecast")
    if (
        q.duplicated(["row_id", "version", "probe_multiplier"]).any()
        or not q.groupby(["row_id", "version"]).size().eq(3).all()
        or len(q) != len(f) * 3
    ):
        raise ValueError("Incomplete probability probes")
    if (
        not np.isfinite(q[["probability", "brier", "log_loss"]]).all().all()
        or not q.probability.between(0, 1).all()
    ):
        raise ValueError("Invalid probability")
    if set(zip(q.row_id, q.version)) != set(zip(f.row_id, f.version)) or set(
        q.probe_multiplier
    ) != set(p["probe_multipliers"]):
        raise ValueError("Probe population/threshold mismatch")
    j = q.merge(
        f[["row_id", "version", "y", "naive"]],
        on=["row_id", "version"],
        validate="many_to_one",
    )
    if (
        not j.event.eq(j.y > j.line).all()
        or not q.line_kind.eq("hypothetical_pregame_halfline_NOT_BOOKMAKER").all()
    ):
        raise ValueError("Invalid probe outcomes/provenance")
    if not np.array_equal(
        j.line.to_numpy(),
        np.floor(np.maximum(j.naive.to_numpy(), 0) * j.probe_multiplier.to_numpy())
        + 0.5,
    ):
        raise ValueError("Probe line not determined pregame")
    bs, ll = binary_scores(j.probability.to_numpy(), j.event.to_numpy())
    if not np.allclose(bs, j.brier, atol=1e-12, rtol=1e-12) or not np.allclose(
        ll, j.log_loss, atol=1e-12, rtol=1e-12
    ):
        raise ValueError("Incorrect proper scores")
    oldq = pd.read_parquet(base / "probes.parquet")
    oldq = oldq[oldq.version == "stage1b1"]
    keys = ["row_id", "probe_multiplier"]
    a = q[q.version == "stage1b1"].sort_values(keys)
    b = oldq.sort_values(keys)
    if not np.allclose(a.probability, b.probability, rtol=0, atol=1e-12):
        raise ValueError("Frozen probability comparator changed")
    a = f[f.version == "stage1b1"].set_index("row_id").sort_index()
    b = old.set_index("row_id").sort_index()
    if not np.allclose(
        a[["projection", "lower90", "upper90"]],
        b[["projection", "lower90", "upper90"]],
        rtol=0,
        atol=1e-12,
    ):
        raise ValueError("Frozen point/interval comparator changed")
    if (
        not np.allclose(
            ctx[["script_trailing", "script_close", "script_leading"]].sum(axis=1), 1
        )
        or (ctx.context_information_at >= ctx.prediction_at).any()
    ):
        raise ValueError("Invalid fixture scenarios")
    if (ctx.prediction_at >= FINAL).any() or not ctx.def_known_fraction.between(
        0, 1 + 1e-10
    ).all():
        raise ValueError("Unsealed/invalid context")
    expected = {
        f"{market}-{year}-{family}.joblib"
        for market in MARKETS
        for year in p["evaluation_seasons"]
        for family in p["families"]
    }
    if {x.name for x in (directory / "models").glob("*.joblib")} != expected:
        raise ValueError("Incomplete model matrix")
    for path in (directory / "models").glob("*.joblib"):
        bundle = joblib.load(path)
        if (
            bundle["features"]
            != feature_columns(bundle["market"]) + FAMILIES[bundle["family"]]
        ):
            raise ValueError("Unexpected features: C0-C2 boundary")
        g = f[
            (f.market == bundle["market"])
            & (f.season == bundle["year"])
            & (f.version == bundle["family"])
        ]
        if (
            not pd.Timestamp(bundle["max_training_available_at"])
            < pd.Timestamp(bundle["information_available_at"])
            < g.prediction_at.min()
        ):
            raise ValueError("Model timing violation")
    if (
        m["genuine_quotes"] != 0
        or m["betting_profit"] is not None
        or m["market_information"] != "none"
        or m["evidence_tier"] != "retrospective"
    ):
        raise ValueError("Unverified historical claim")
    return {
        "player_market_games": len(old),
        "versions": len(p["families"]) + 1,
        "models": len(expected),
        "final_sealed": True,
    }


def replay(directory, root):
    from stage1c.runner import load, evaluate
    from stage1c.context import attach
    from stage1b.data import market_panel

    directory = Path(directory)
    root = Path(root)
    audit = validate(directory, root)
    p, base, bm, inp, games, rates, ctx, panel = load(root)
    original = pd.read_parquet(directory / "forecasts.parquet")
    probes = pd.read_parquet(directory / "probes.parquet")
    for market in MARKETS:
        d = attach(market_panel(panel, market), ctx, market)
        for year in p["evaluation_seasons"]:
            e = d[d.season.eq(year) & d.feature_complete & d.scorable]
            for family in p["families"]:
                b = joblib.load(
                    directory / "models" / f"{market}-{year}-{family}.joblib"
                )
                f, q = evaluate(b, e, p)
                ref = original[
                    (original.market == market)
                    & (original.season == year)
                    & (original.version == family)
                ]
                cols = list(f.columns)
                pd.testing.assert_frame_equal(
                    f[cols].sort_values("row_id").reset_index(drop=True),
                    ref[cols].sort_values("row_id").reset_index(drop=True),
                    rtol=1e-12,
                    atol=1e-12,
                )
                ref = probes[
                    (probes.market == market)
                    & (probes.season == year)
                    & (probes.version == family)
                ]
                keys = ["row_id", "probe_multiplier"]
                pd.testing.assert_frame_equal(
                    q.sort_values(keys).reset_index(drop=True),
                    ref[q.columns].sort_values(keys).reset_index(drop=True),
                    rtol=1e-12,
                    atol=1e-12,
                )
    print(json.dumps({**audit, "all_models_replayed": True}))
    return audit


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("directory", type=Path)
    p.add_argument("--replay", action="store_true")
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    if a.replay:
        replay(a.directory, root)
    else:
        print(json.dumps(validate(a.directory, root)))
