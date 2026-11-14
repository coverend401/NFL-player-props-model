"""Independent immutable provenance and replay; every earlier benchmark stays frozen."""

import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from stage1c.artifacts import sources as previous_sources, validate as validate_c0
from stage1b1.artifacts import validate as validate_b1
from stage1b.artifacts import digest, runtime
from stage1c.contracts import assert_development
from stage1b.data import MARKETS, feature_columns
from stage1b.metrics import binary_scores
from stage1c1.data import CONTEXTS


def sources(root):
    root = Path(root)
    result = previous_sources(root)
    result.update(
        {
            str(p.relative_to(root)): digest(p)
            for p in sorted(root.glob("stage1c1/*"))
            if p.suffix in [".py", ".json"]
        }
    )
    return result


def validate(directory, root):
    root = Path(root).resolve()
    directory = Path(directory).resolve()
    p = json.loads((root / "stage1c1/protocol.json").read_text())
    m = json.loads((directory / "manifest.json").read_text())
    if m["source_hashes"] != sources(root) or m["runtime"] != runtime(root):
        raise ValueError("Scientific source/runtime changed")
    if (
        m["status"] != "passed"
        or not m["final_period_sealed"]
        or m["scope"] != "Stage1C.1 controlled diagnostics only; no C3-C6"
    ):
        raise ValueError("Unvalidated/unsealed research")
    b1 = root / "experiments/stage1b1/improvements-20261113-v1"
    c0 = root / "experiments/stage1c/c0-c2-20261113-v1"
    validate_b1(b1, root)
    validate_c0(c0, root)
    for name, d in [("b1", b1), ("c0", c0)]:
        if digest(d / "manifest.json") != m["baseline_manifests"][name]:
            raise ValueError("Frozen benchmark manifest changed")
    inp = root / p["input_bundle"]
    im = json.loads((inp / "manifest.json").read_text())
    if digest(inp / "manifest.json") != m["input_manifest_sha256"]:
        raise ValueError("Reconciliation input changed")
    if set(im["files"]) != {
        "position_totals.parquet",
        "team_reconciliation.parquet",
        "player_reconciliation.parquet",
        "unresolved_events.parquet",
    }:
        raise ValueError("Incomplete input manifest")
    for name, h in im["files"].items():
        if digest(inp / name) != h:
            raise ValueError("Input payload changed")
    files = {
        str(x.relative_to(directory))
        for x in directory.rglob("*")
        if x.is_file() and x.name != "manifest.json"
    }
    if files != set(m["files"]):
        raise ValueError("Missing/unexpected research payload")
    for name, h in m["files"].items():
        raw = directory / name
        f = raw.resolve()
        if raw.is_symlink() or directory not in f.parents or digest(f) != h:
            raise ValueError("Research payload mismatch")
    if json.loads((directory / "protocol.json").read_text()) != p:
        raise ValueError("Protocol mismatch")
    f = pd.read_parquet(directory / "forecasts.parquet")
    q = pd.read_parquet(directory / "probes.parquet")
    old = pd.read_parquet(b1 / "forecasts.parquet")
    oldq = pd.read_parquet(b1 / "probes.parquet")
    oldq = oldq[oldq.version.eq("stage1b1")]
    assert_development(f)
    if (
        set(f.version) != {"frozen_b1", *p["variants"]}
        or f.duplicated(["row_id", "version"]).any()
    ):
        raise ValueError("Forecast version population")
    if (
        not np.isfinite(f[["projection", "lower90", "upper90", "interval_score"]])
        .all()
        .all()
        or f.lower90.gt(f.upper90).any()
    ):
        raise ValueError("Invalid forecasts")
    for variant, g in f.groupby("version"):
        if set(g.row_id) != set(old.row_id):
            raise ValueError("Eligible population changed")
        j = g.merge(
            old[["row_id", "y", "prediction_at", "completed_at"]],
            on="row_id",
            suffixes=("", "_ref"),
            validate="one_to_one",
        )
        if not (
            j.y.eq(j.y_ref)
            & j.prediction_at.eq(j.prediction_at_ref)
            & j.completed_at.eq(j.completed_at_ref)
        ).all():
            raise ValueError("Outcomes/timing changed")
    new = f[f.version != "frozen_b1"]
    if not (
        (new.history_available_at < new.prediction_at)
        & (new.context_information_at < new.prediction_at)
        & (new.prediction_at < new.completed_at)
    ).all():
        raise ValueError("Future feature information")
    if not new.probability_method.eq(p["probability_method"]).all():
        raise ValueError("Probability methodology is not constant")
    if (
        set(zip(q.row_id, q.version)) != set(zip(f.row_id, f.version))
        or q.duplicated(["row_id", "version", "probe_multiplier"]).any()
        or not q.groupby(["row_id", "version"]).size().eq(3).all()
    ):
        raise ValueError("Probability population mismatch")
    if (
        set(q.probe_multiplier) != set(p["probe_multipliers"])
        or not q.probability.between(0, 1).all()
        or not np.isfinite(q[["probability", "brier", "log_loss"]]).all().all()
    ):
        raise ValueError("Invalid probes")
    j = q.merge(
        f[["row_id", "version", "y", "naive"]],
        on=["row_id", "version"],
        validate="many_to_one",
    )
    if (
        not np.array_equal(
            j.line, np.floor(np.maximum(j.naive, 0) * j.probe_multiplier) + 0.5
        )
        or not j.event.eq(j.y > j.line).all()
        or not q.line_kind.eq("hypothetical_pregame_halfline_NOT_BOOKMAKER").all()
    ):
        raise ValueError("Invalid hypothetical lines/outcomes")
    bs, ll = binary_scores(j.probability.to_numpy(), j.event.to_numpy())
    if not np.allclose(bs, j.brier, rtol=1e-12, atol=1e-12) or not np.allclose(
        ll, j.log_loss, rtol=1e-12, atol=1e-12
    ):
        raise ValueError("Incorrect probability scores")
    reference = f[f.version.eq("frozen_b1")].set_index("row_id").sort_index()
    original = old.set_index("row_id").sort_index()
    if not np.allclose(
        reference[["projection", "lower90", "upper90"]],
        original[["projection", "lower90", "upper90"]],
        rtol=0,
        atol=1e-12,
    ):
        raise ValueError("Frozen comparator changed")
    native = f[f.version.eq("b1_none")].set_index("row_id").sort_index()
    if not np.allclose(native.projection, original.projection, rtol=0, atol=1e-10):
        raise ValueError("Native backbone no-context identity failed")
    oq = q[q.version.eq("frozen_b1")].sort_values(["row_id", "probe_multiplier"])
    oldq = oldq.sort_values(["row_id", "probe_multiplier"])
    if not np.allclose(oq.probability, oldq.probability, rtol=0, atol=1e-12):
        raise ValueError("Frozen probabilities changed")
    expected = {
        f"{market}-{year}-{variant}.joblib"
        for market in MARKETS
        for year in p["evaluation_seasons"]
        for variant in p["variants"]
    }
    if {x.name for x in (directory / "models").glob("*.joblib")} != expected:
        raise ValueError("Incomplete model matrix")
    for path in (directory / "models").glob("*.joblib"):
        b = joblib.load(path)
        rows = f[
            (f.market == b["market"])
            & f.season.eq(b["year"])
            & f.version.eq(b["variant"])
        ]
        if (
            b["features"]
            != feature_columns(b["market"])
            + CONTEXTS[p["variants"][b["variant"]]["context"]]
        ):
            raise ValueError("Unapproved features")
        if (
            not pd.Timestamp(b["max_training_available_at"])
            < pd.Timestamp(b["information_available_at"])
            < rows.prediction_at.min()
        ):
            raise ValueError("Model information timing")
        if b["probability_method"] != p["probability_method"]:
            raise ValueError("Mixed probability method")
    oracle = pd.read_parquet(directory / "oracle_diagnostics.parquet")
    assert_development(oracle)
    if (
        set(oracle.row_id) != set(old.row_id)
        or oracle.row_id.duplicated().any()
        or oracle.candidate_forecast.fillna(True).any()
        or not oracle.classification.eq(
            "HINDSIGHT_ONLY_ERROR_ACCOUNTING_NOT_FORECAST"
        ).all()
    ):
        raise ValueError("Oracle/forecast separation violated")
    eligible = oracle[oracle.eligible]
    if not (
        (eligible.historical_information_max < eligible.prediction_at)
        & (eligible.team_information_max < eligible.prediction_at)
    ).all():
        raise ValueError("Future information in diagnostic strawman")
    pp = pd.read_csv(directory / "inner_permutation.csv")
    if not pp.window.eq("prior_year_weeks11to18_ONLY").all():
        raise ValueError("Outer evaluation used for feature diagnostics")
    for (market, year, variant), g in pp.groupby(["market", "season", "variant"]):
        start = f[
            (f.market == market) & f.season.eq(year) & f.version.eq(variant)
        ].prediction_at.min()
        if not (pd.to_datetime(g.information_max, utc=True) < start).all():
            raise ValueError("Feature diagnostic uses outer-year labels")
    coherent = eligible[~eligible.actual_share_incoherent]
    if not np.allclose(coherent.corner_15, coherent.y, rtol=1e-10, atol=1e-10):
        raise ValueError("Oracle accounting identity failed")
    contribution = coherent[
        [
            "shapley_team_error_reduction",
            "shapley_share_error_reduction",
            "shapley_efficiency_error_reduction",
            "shapley_exception_error_reduction",
        ]
    ].sum(axis=1)
    if not np.allclose(
        contribution,
        abs(coherent.corner_0 - coherent.y) - abs(coherent.corner_15 - coherent.y),
        rtol=1e-9,
        atol=1e-9,
    ):
        raise ValueError("Oracle factor reductions do not reconcile")
    if (
        m["oracle_outputs_are_forecasts"] is not False
        or m["genuine_quotes"] != 0
        or m["betting_profit"] is not None
        or m["evidence_tier"] != p["evidence_tier"]
    ):
        raise ValueError("Unsupported evidence claim")
    return {
        "models": len(expected),
        "versions": len(p["variants"]) + 1,
        "player_market_games": len(old),
        "final_sealed": True,
        "oracle_outputs_separate": True,
    }


def replay(directory, root):
    from stage1c1.data import load
    from stage1c1.runner import evaluate
    from stage1c.context import attach
    from stage1b.data import market_panel

    directory = Path(directory)
    root = Path(root)
    audit = validate(directory, root)
    p, b1, c0, inp, games, rates, contexts, source, panel = load(root)
    original = pd.read_parquet(directory / "forecasts.parquet")
    probes = pd.read_parquet(directory / "probes.parquet")
    for market in MARKETS:
        data = {
            name: attach(market_panel(panel, market), ctx, market)
            for name, ctx in contexts.items()
        }
        for year in p["evaluation_seasons"]:
            for variant, config in p["variants"].items():
                b = joblib.load(
                    directory / "models" / f"{market}-{year}-{variant}.joblib"
                )
                d = data[config["source"]]
                d = d[d.season.eq(year) & d.feature_complete & d.scorable]
                f, q = evaluate(b, d, p)
                old = original[
                    (original.market == market)
                    & original.season.eq(year)
                    & original.version.eq(variant)
                ]
                keys = ["row_id"]
                pd.testing.assert_frame_equal(
                    f.sort_values(keys).reset_index(drop=True),
                    old[f.columns].sort_values(keys).reset_index(drop=True),
                    rtol=1e-12,
                    atol=1e-12,
                )
                old = probes[
                    (probes.market == market)
                    & probes.season.eq(year)
                    & probes.version.eq(variant)
                ]
                keys = ["row_id", "probe_multiplier"]
                pd.testing.assert_frame_equal(
                    q.sort_values(keys).reset_index(drop=True),
                    old[q.columns].sort_values(keys).reset_index(drop=True),
                    rtol=1e-12,
                    atol=1e-12,
                )
    print(json.dumps({**audit, "all_models_replayed": True}))
    return audit


if __name__ == "__main__":
    import argparse

    a = argparse.ArgumentParser()
    a.add_argument("directory", type=Path)
    a.add_argument("--replay", action="store_true")
    args = a.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.replay:
        replay(args.directory, root)
    else:
        print(json.dumps(validate(args.directory, root)))
