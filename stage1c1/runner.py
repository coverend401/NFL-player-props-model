"""Preregistered controlled diagnostics. No deployment or final evaluation access."""

import argparse, json, tempfile, subprocess, shutil
from pathlib import Path
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
from stage1b.data import MARKETS, market_panel, feature_columns
from stage1b.runner import probabilities, probe_lines
from stage1b.metrics import binary_scores, probability_summary, reliability
from stage1b1.probability import interval_score
from stage1b.artifacts import digest, runtime
from stage1c.context import attach
from stage1c1.data import load, ROOT
from stage1c1.models import fit, predict, cdf, bounds
from stage1c1.diagnostics import feature_diagnostics, effective_samples
from stage1c1.metrics import summaries, paired
from stage1c1.oracles import build as oracle_diagnostics


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
    f["version"] = b["variant"]
    f["projection"] = predict(b, d)
    f["naive"] = d[feature_columns(b["market"])[0]].to_numpy()
    f["lower90"], f["upper90"] = bounds(b, d)
    f["interval_score"] = interval_score(f.y, f.lower90, f.upper90)
    f["evaluation_tier"] = np.where(f.season.eq(2026), "monitoring", "development_oos")
    f["point_method"] = b["point_method"]
    f["probability_method"] = b["probability_method"]
    lines = probe_lines(d, b["market"], p)
    prob = probabilities(cdf(b, d), lines)
    truth = (d.y.to_numpy()[:, None] > lines).astype(int)
    bs, ll = binary_scores(prob, truth)
    probes = []
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
        probes.append(q)
    return f, pd.concat(probes, ignore_index=True)


def run(root, identifier):
    from stage1c1.artifacts import sources, validate, replay

    root = Path(root).resolve()
    if not identifier or any(
        c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in identifier
    ):
        raise ValueError("Invalid immutable experiment ID")
    target = root / "experiments/stage1c1" / identifier
    if target.exists():
        raise ValueError("Experiment ID already exists")
    src = sources(root)
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--", *src], cwd=root, text=True
    ).strip():
        raise ValueError("Commit scientific protocol/sources before fitting")
    p, b1, c0, inputs, games, rates, contexts, source, panel = load(root)
    ih = digest(inputs / "manifest.json")
    rt = runtime(root)
    c0ref = pd.read_parquet(c0 / "forecasts.parquet")
    c0ref = c0ref[c0ref.version.eq("player_control")]
    oldf = pd.read_parquet(b1 / "forecasts.parquet")
    oldq = pd.read_parquet(b1 / "probes.parquet")
    oldq = oldq[oldq.version.eq("stage1b1")].copy()
    oldq["version"] = "frozen_b1"
    fields = [
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
    frozen = oldf[fields].copy()
    frozen["version"] = "frozen_b1"
    frozen["context_information_at"] = pd.Series(
        pd.NaT, index=frozen.index, dtype="datetime64[ns, UTC]"
    )
    for col in ["prediction_at", "history_available_at", "completed_at"]:
        frozen[col] = pd.to_datetime(frozen[col], utc=True).astype(
            "datetime64[ns, UTC]"
        )
    frames = [frozen]
    probes = [oldq]
    folds = []
    permutation = []
    redundancy = []
    weights = []
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="nfl-c1-1-") as tmp:
        work = Path(tmp)
        (work / "models").mkdir()
        for market in MARKETS:
            data = {
                key: attach(market_panel(panel, market), ctx, market)
                for key, ctx in contexts.items()
            }
            for year in p["evaluation_seasons"]:
                archived = {
                    "b1": joblib.load(b1 / "models" / f"{market}-{year}.joblib"),
                    "c0": joblib.load(
                        c0 / "models" / f"{market}-{year}-player_control.joblib"
                    ),
                }
                for variant, config in p["variants"].items():
                    print("FIT", market, year, variant, flush=True)
                    d = data[config["source"]]
                    b, info, e, selection, train = fit(
                        d, market, year, variant, p, archived[config["backbone"]]
                    )
                    f, q = evaluate(b, e, p)
                    if config.get("archived_point"):
                        reference = (
                            oldf[(oldf.market == market) & oldf.season.eq(year)]
                            if config["backbone"] == "b1"
                            else c0ref[(c0ref.market == market) & c0ref.season.eq(year)]
                        )
                        j = f[["row_id", "projection"]].merge(
                            reference[["row_id", "projection"]],
                            on="row_id",
                            suffixes=("_new", "_old"),
                            validate="one_to_one",
                        )
                        if not np.allclose(
                            j.projection_new, j.projection_old, rtol=0, atol=1e-10
                        ):
                            raise ValueError("Archived point identity failed")
                    pp, rr, ww = feature_diagnostics(b, train, selection, p)
                    permutation.extend(pp)
                    redundancy.extend(rr)
                    weights.extend(ww)
                    frames.append(f)
                    probes.append(q)
                    folds.append(info)
                    joblib.dump(
                        b,
                        work / "models" / f"{market}-{year}-{variant}.joblib",
                        compress=3,
                    )
        f = pd.concat(frames, ignore_index=True)
        q = pd.concat(probes, ignore_index=True)
        f.to_parquet(work / "forecasts.parquet", index=False)
        q.to_parquet(work / "probes.parquet", index=False)
        summaries(f).to_csv(work / "accuracy.csv", index=False)
        probability_summary(q, p).to_csv(work / "probability_metrics.csv", index=False)
        reliability(q, p).to_csv(work / "reliability.csv", index=False)
        paired(f, q, p).to_csv(work / "paired_metrics.csv", index=False)
        pd.DataFrame(permutation).to_csv(work / "inner_permutation.csv", index=False)
        pd.DataFrame(redundancy).to_csv(work / "training_redundancy.csv", index=False)
        pd.DataFrame(weights).to_csv(work / "training_weights.csv", index=False)
        for name, ctx in contexts.items():
            if name == "legacy":
                rr = pd.read_parquet(
                    root
                    / "research_inputs/stage1c/public-20261113-v3/position_totals.parquet"
                )
            else:
                rr = rates
            effective_samples(games, rr, ctx).to_parquet(
                work / f"effective_samples_{name}.parquet", index=False
            )
        official = pd.read_parquet(
            root / "research_inputs/stage1c/public-20261113-v3/position_totals.parquet"
        )
        print("HINDSIGHT-ONLY ORACLE ACCOUNTING", flush=True)
        oracle_diagnostics(
            oldf, source, games, official, contexts["reconciled"]
        ).to_parquet(work / "oracle_diagnostics.parquet", index=False)
        (work / "folds.json").write_text(json.dumps(folds, indent=2) + "\n")
        (work / "protocol.json").write_text(json.dumps(p, indent=2) + "\n")
        if src != sources(root) or ih != digest(inputs / "manifest.json"):
            raise ValueError("Scientific source/input changed during experiment")
        manifest = dict(
            schema=1,
            experiment_id=identifier,
            status="passed",
            scope="Stage1C.1 controlled diagnostics only; no C3-C6",
            source_commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            source_hashes=src,
            runtime=rt,
            input_manifest_sha256=ih,
            baseline_manifests={
                "b1": digest(b1 / "manifest.json"),
                "c0": digest(c0 / "manifest.json"),
            },
            files={
                str(x.relative_to(work)): digest(x)
                for x in sorted(work.rglob("*"))
                if x.is_file()
            },
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            final_period_sealed=True,
            evidence_tier=p["evidence_tier"],
            oracle_outputs_are_forecasts=False,
            genuine_quotes=0,
            betting_profit=None,
        )
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        validate(work, root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, target)
    print("PASSED", target, flush=True)
    replay(target, root)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--id", required=True)
    args = a.parse_args()
    run(ROOT, args.id)
