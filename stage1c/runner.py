"""Immutable C0–C2 ablation experiment. Never reads or writes production forecasts."""

import argparse, json, subprocess, tempfile, shutil
from pathlib import Path
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
from stage1b.data import (
    prepare_panel,
    read_development_snapshot,
    market_panel,
    MARKETS,
    feature_columns,
)
from stage1b.runner import probabilities, probe_lines
from stage1b.metrics import (
    binary_scores,
    probability_summary,
    reliability,
    week_block_interval,
)
from stage1b1.probability import interval_score
from stage1b1.artifacts import validate as validate_baseline
from stage1b.artifacts import digest, runtime
from stage1c.context import states, attach
from stage1c.models import fit, point_predict, curve, interval

ROOT = Path(__file__).resolve().parents[1]


def load(root):
    p = json.loads((root / "stage1c/protocol.json").read_text())
    base = root / "experiments/stage1b1" / p["baseline_experiment"]
    bm = validate_baseline(base, root)
    inp = root / p["input_bundle"]
    im = json.loads((inp / "manifest.json").read_text())
    if (
        im["player_snapshot_sha256"] != bm["input_sha256"]
        or im["evidence_tier"] != "retrospective"
        or im["final_period_sealed"] is not True
    ):
        raise ValueError("Input snapshot/tier mismatch")
    for n, h in im["files"].items():
        if "/" in n or digest(inp / n) != h:
            raise ValueError("Context input integrity")
    games = pd.read_parquet(inp / "team_games.parquet")
    rates = pd.read_parquet(inp / "position_totals.parquet")
    context = states(games, rates, p["context_lag_hours"])
    panel = prepare_panel(read_development_snapshot(root / bm["input_path"], p), p)
    return p, base, bm, inp, games, rates, context, panel


def evaluate(b, d, p):
    f = d[
        [
            "player_id",
            "player_display_name",
            "game_id",
            "position",
            "season",
            "week",
            "prediction_at",
            "history_available_at",
            "completed_at",
            "games_played_prior",
            "returning",
            "y",
            "context_information_at",
        ]
    ].reset_index(drop=True)
    for col in [
        "prediction_at",
        "history_available_at",
        "completed_at",
        "context_information_at",
    ]:
        f[col] = pd.to_datetime(f[col], utc=True).astype("datetime64[ns, UTC]")
    f["market"] = b["market"]
    f["row_id"] = f.market + "|" + f.player_id + "|" + f.game_id
    f["version"] = b["family"]
    f["projection"] = point_predict(b, d)
    f["naive"] = d[feature_columns(b["market"])[0]].to_numpy()
    lo, hi = interval(b, d, b["selected_interval"])
    f["lower90"] = lo
    f["upper90"] = hi
    f["interval_score"] = interval_score(f.y, lo, hi)
    f["evaluation_tier"] = np.where(f.season == 2026, "monitoring", "development_oos")
    f["point_method"] = b["point_method"]
    f["probability_method"] = b["selected_probability"]
    f["interval_method"] = b["selected_interval"]
    lines = probe_lines(d, b["market"], p)
    prob = probabilities(curve(b, d, b["selected_probability"]), lines)
    truth = (d.y.to_numpy()[:, None] > lines).astype(int)
    bs, ll = binary_scores(prob, truth)
    qs = []
    for i, m in enumerate(p["probe_multipliers"]):
        q = f[
            [
                "row_id",
                "market",
                "version",
                "season",
                "week",
                "game_id",
                "evaluation_tier",
            ]
        ].copy()
        q["line"] = lines[:, i]
        q["probe_multiplier"] = m
        q["probability"] = prob[:, i]
        q["event"] = truth[:, i]
        q["brier"] = bs[:, i]
        q["log_loss"] = ll[:, i]
        q["line_kind"] = "hypothetical_pregame_halfline_NOT_BOOKMAKER"
        qs.append(q)
    return f, pd.concat(qs, ignore_index=True)


def metrics(f, p):
    rows = []
    deltas = []
    for (market, tier, version), group in f.groupby(
        ["market", "evaluation_tier", "version"]
    ):
        for season, g in [("all", group)] + list(group.groupby("season")):
            e = g.projection - g.y
            rows.append(
                dict(
                    market=market,
                    evaluation_tier=tier,
                    version=version,
                    season=str(season),
                    n=len(g),
                    mae=float(abs(e).mean()),
                    rmse=float(np.sqrt(np.mean(e**2))),
                    bias=float(e.mean()),
                    zeros=int(g.y.eq(0).sum()),
                    coverage90=float(((g.y >= g.lower90) & (g.y <= g.upper90)).mean()),
                    width90=float((g.upper90 - g.lower90).mean()),
                    interval_score90=float(g.interval_score.mean()),
                )
            )
        if version == "stage1b1":
            continue
        for ref in ["stage1b1", "player_control"]:
            if ref == version:
                continue
            old = f[
                (f.market == market) & (f.evaluation_tier == tier) & (f.version == ref)
            ]
            g = group.merge(
                old[["row_id", "projection", "interval_score"]],
                on="row_id",
                suffixes=("", "_ref"),
                validate="one_to_one",
            )
            for key, values in [
                ("mae", abs(g.projection - g.y) - abs(g.projection_ref - g.y)),
                ("interval_score", g.interval_score - g.interval_score_ref),
            ]:
                g["delta"] = values
                low, high = week_block_interval(
                    g, "delta", reps=p["bootstrap_replicates"]
                )
                deltas.append(
                    dict(
                        market=market,
                        evaluation_tier=tier,
                        version=version,
                        reference=ref,
                        metric=key,
                        n=len(g),
                        delta=float(values.mean()),
                        low=low,
                        high=high,
                    )
                )
    return pd.DataFrame(rows), pd.DataFrame(deltas)


def run(root, identifier):
    from stage1c.artifacts import sources, validate, replay

    root = Path(root).resolve()
    if not identifier or any(
        c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in identifier
    ):
        raise ValueError("Invalid experiment ID")
    target = root / "experiments/stage1c" / identifier
    if target.exists():
        raise ValueError("Experiment ID immutable")
    src = sources(root)
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--", *src], cwd=root, text=True
    ).strip():
        raise ValueError("Commit all scientific sources before fitting")
    p, base, bm, inp, games, rates, context, panel = load(root)
    ih = digest(inp / "manifest.json")
    rt = runtime(root)
    started = datetime.now(timezone.utc).isoformat()
    oldf = pd.read_parquet(base / "forecasts.parquet")
    oldq = pd.read_parquet(base / "probes.parquet")
    oldq = oldq[oldq.version.eq("stage1b1")].copy()
    common = [
        "player_id",
        "player_display_name",
        "game_id",
        "position",
        "season",
        "week",
        "prediction_at",
        "history_available_at",
        "completed_at",
        "games_played_prior",
        "returning",
        "y",
        "market",
        "row_id",
        "projection",
        "naive",
        "lower90",
        "upper90",
        "interval_score",
        "evaluation_tier",
    ]
    oldf = oldf[common].copy()
    oldf["version"] = "stage1b1"
    oldf["context_information_at"] = pd.Series(
        pd.NaT, index=oldf.index, dtype="datetime64[ns, UTC]"
    )
    for col in ["prediction_at", "history_available_at", "completed_at"]:
        oldf[col] = pd.to_datetime(oldf[col], utc=True).astype("datetime64[ns, UTC]")
    fs = [oldf]
    qs = [oldq]
    folds = []
    with tempfile.TemporaryDirectory(prefix="nfl-c0-c2-") as tmp:
        work = Path(tmp)
        (work / "models").mkdir()
        for market in MARKETS:
            d = attach(market_panel(panel, market), context, market)
            for year in p["evaluation_seasons"]:
                for family in p["families"]:
                    print("FIT", market, year, family, flush=True)
                    b, meta, e = fit(d, market, year, family, p)
                    f, q = evaluate(b, e, p)
                    fs.append(f)
                    qs.append(q)
                    folds.append(meta)
                    joblib.dump(
                        b,
                        work / "models" / f"{market}-{year}-{family}.joblib",
                        compress=3,
                    )
        f = pd.concat(fs, ignore_index=True)
        q = pd.concat(qs, ignore_index=True)
        f.to_parquet(work / "forecasts.parquet", index=False)
        q.to_parquet(work / "probes.parquet", index=False)
        context.to_parquet(work / "context.parquet", index=False)
        a, delta = metrics(f, p)
        a.to_csv(work / "accuracy.csv", index=False)
        delta.to_csv(work / "paired_accuracy.csv", index=False)
        probability_summary(q, p).to_csv(work / "probability_metrics.csv", index=False)
        reliability(q, p).to_csv(work / "reliability.csv", index=False)
        (work / "folds.json").write_text(json.dumps(folds, indent=2) + "\n")
        (work / "protocol.json").write_text(json.dumps(p, indent=2) + "\n")
        if src != sources(root) or digest(inp / "manifest.json") != ih:
            raise ValueError("Source/input changed during experiment")
        manifest = dict(
            schema_version=1,
            experiment_id=identifier,
            status="passed",
            scope="C0-C2 research only",
            final_period_sealed=True,
            source_commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            source_hashes=src,
            runtime=rt,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            input_manifest_sha256=ih,
            baseline_manifest_sha256=digest(base / "manifest.json"),
            files={
                str(x.relative_to(work)): digest(x)
                for x in sorted(work.rglob("*"))
                if x.is_file()
            },
            genuine_quotes=0,
            betting_profit=None,
            market_information="none",
            evidence_tier="retrospective",
        )
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        validate(work, root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, target)
    print("PASSED", target, flush=True)
    replay(target, root)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    a = p.parse_args()
    run(ROOT, a.id)
