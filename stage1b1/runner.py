"""Versioned Stage 1B.1 comparison; never mutates the frozen Stage 1B package."""

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import tempfile
import shutil

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from stage1b.artifacts import digest, runtime, validate as validate_baseline
from stage1b.data import (
    prepare_panel,
    read_development_snapshot,
    market_panel,
    feature_columns,
    before,
    MARKETS,
)
from stage1b.runner import model_predictions, cdf_for, probabilities, probe_lines
from stage1b.metrics import (
    binary_scores,
    probability_summary,
    paired_improvements,
    week_block_interval,
    reliability,
)
from stage1b1.metrics import summaries
from stage1b1.models import LagBlend, CompletionThinning
from stage1b1.probability import (
    ShrunkSigmoid,
    student_cdf,
    mix_cdf,
    nb_cdf,
    shrink_dispersion,
    conformal_offset,
    interval_score,
)

ROOT = Path(__file__).resolve().parents[1]


def phases(d, year, p):
    evaluate = d[d.season.eq(year)]
    choose = d[d.season.eq(year - 2)]
    cal = d[d.season.eq(year - 1)]
    if evaluate.empty or choose.empty or cal.empty:
        raise ValueError("Missing chronological season")
    initial = before(d, choose.prediction_at.min())
    select_point = before(choose, cal.prediction_at.min())
    train = before(d, cal.prediction_at.min())
    a = cal[cal.week <= p["distribution_fit_last_week"]]
    b = cal[
        (cal.week > p["distribution_fit_last_week"])
        & (cal.week <= p["calibration_last_week"])
    ]
    c = cal[cal.week > p["calibration_last_week"]]
    if a.empty or b.empty or c.empty:
        raise ValueError("Missing phase")
    a = before(a, b.prediction_at.min())
    b = before(b, c.prediction_at.min())
    c = before(c, evaluate.prediction_at.min())
    if min(map(len, [initial, select_point, train, a, b, c])) < p["minimum_phase_rows"]:
        raise ValueError("Insufficient independent phase observations")
    return (
        initial,
        select_point,
        train,
        a,
        b,
        c,
        evaluate[evaluate.feature_complete & evaluate.scorable].copy(),
    )


def point_policy(initial, validation, train, cols, p):
    builders = {
        "career_mean": lambda: LagBlend((1, 0, 0)),
        "recent3": lambda: LagBlend((0, 1, 0)),
        "shrunk_recent3": lambda: LagBlend((0.75, 0.25, 0)),
        "shrunk_recent5": lambda: LagBlend((0.5, 0, 0.5)),
        "blended_recent": lambda: LagBlend((0.25, 0.5, 0.25)),
        "scaled_ridge100": lambda: make_pipeline(StandardScaler(), Ridge(alpha=100)),
    }
    predictions = {}
    rows = []
    for name, build in builders.items():
        m = build()
        if name.startswith("scaled"):
            m.fit(initial[cols], initial.y)
        predictions[name] = m.predict(validation[cols])
    incumbent = np.abs(predictions["career_mean"] - validation.y.to_numpy())
    best = "career_mean"
    best_mae = float(incumbent.mean())
    for name, pred in predictions.items():
        err = np.abs(pred - validation.y.to_numpy())
        g = validation[["season", "week"]].copy()
        g["delta"] = err - incumbent
        low, high = week_block_interval(
            g,
            "delta",
            reps=p["point_bootstrap_replicates"],
            block=p["bootstrap_week_block"],
        )
        gain = 1 - float(err.mean()) / max(float(incumbent.mean()), 1e-9)
        accepted = name == "career_mean" or (
            gain >= p["point_minimum_relative_gain"]
            and high < 0
            and g.week.nunique() >= p["minimum_gate_weeks"]
        )
        rows.append(
            dict(
                candidate=name,
                mae=float(err.mean()),
                delta_low=low,
                delta_high=high,
                accepted=bool(accepted),
            )
        )
        if accepted and float(err.mean()) < best_mae:
            best = name
            best_mae = float(err.mean())
    model = builders[best]()
    if best.startswith("scaled"):
        model.fit(train[cols], train.y)
    return model, best, rows


def prediction(bundle, d):
    x = d[bundle["features"]]
    mu = bundle["point"].predict(x)
    if bundle["count"]:
        mu = np.maximum(mu, 0)
    quantiles = np.column_stack([m.predict(x) for m in bundle["quantiles"]])
    return mu, np.sort(quantiles, axis=1)


def candidate_cdf(bundle, d, key, tail_weight=None):
    name, calibration = key.split("|")
    mu, qs = prediction(bundle, d)
    anchor = student_cdf(mu, bundle["bias"], bundle["scale"], bundle["count"])
    if name == "reference":
        base = lambda t: stats.norm.cdf(
            np.asarray(t) + 0.5, mu, bundle["in_sample_scale"]
        )
        if bundle["count"]:
            unbounded = base
            base = lambda t: np.where(np.asarray(t) < 0, 0, unbounded(t))
    elif name == "normal_oos":
        base = lambda t: stats.norm.cdf(
            np.asarray(t) + 0.5, mu + bundle["bias"], bundle["scale"]
        )
        if bundle["count"]:
            unbounded = base
            base = lambda t: np.where(np.asarray(t) < 0, 0, unbounded(t))
    elif name == "scaled_empirical":
        scale = (
            np.sqrt(np.maximum(mu, 1)) if bundle["count"] else np.maximum(abs(mu), 10)
        )
        residual = bundle["scaled_errors"]

        def base(t):
            t = np.asarray(t)
            q = np.searchsorted(residual, (t + 0.5 - mu) / scale, side="left") / len(
                residual
            )
            return np.where(t < 0, 0, q) if bundle["count"] else q
    elif name == "nb2":
        if bundle["joint"] is not None:
            mean = bundle["joint"].predict(d[bundle["features"]])
        else:
            mean = bundle["incumbent"]["poisson"].predict(d[bundle["features"]])
        base = nb_cdf(mean, bundle["alpha"])
    elif name == "dense_quantile":
        spread = max(bundle["scale"], 1.0)
        lower = np.minimum(
            qs[:, 0] - 1,
            mu + bundle["bias"] + stats.t.ppf(0.001, 5) * spread * np.sqrt(3 / 5),
        )
        upper = np.maximum(
            qs[:, -1] + 1,
            mu + bundle["bias"] + stats.t.ppf(0.999, 5) * spread * np.sqrt(3 / 5),
        )
        nodes = np.column_stack([lower, qs, upper])
        levels = [0, *bundle["quantile_levels"], 1]

        def base(t):
            t = np.broadcast_to(t, mu.shape)
            q = np.array([np.interp(v + 0.5, x, levels) for v, x in zip(t, nodes)])
            return np.where(t < 0, 0, q) if bundle["count"] else q
    else:
        raise ValueError("Unknown probability candidate")
    if calibration == "sigmoid":
        base = bundle["calibrators"][key].cdf(base)
    return mix_cdf(
        base, anchor, bundle["tail_weight"] if tail_weight is None else tail_weight
    )


def final_cdf(bundle, d):
    if bundle["selected_probability"] == "retain_stage1b":
        b = bundle["incumbent"]
        return cdf_for(
            b, b["selected_kind"], model_predictions(b, d), b["selected_calibration"]
        )
    return candidate_cdf(bundle, d, bundle["selected_probability"])


def intervals(bundle, d, kind):
    mu, qs = prediction(bundle, d)
    if kind == "cqr":
        lo = np.floor(qs[:, 0]) - bundle["cqr_offset"]
        hi = np.ceil(qs[:, -1]) + bundle["cqr_offset"]
    elif kind == "normal_oos":
        lo = np.floor(mu + bundle["bias"] + stats.norm.ppf(0.05) * bundle["scale"])
        hi = np.ceil(mu + bundle["bias"] + stats.norm.ppf(0.95) * bundle["scale"])
    else:
        raise ValueError("Unknown interval method")
    if bundle["count"]:
        lo = np.maximum(lo, 0)
    return lo, hi


def fit(d, market, year, base, p):
    initial, psel, train, residual, calibration, selection, evaluate = phases(
        d, year, p
    )
    cols = feature_columns(market)
    point = base["point"]
    point_name = "retain_stage1b"
    point_rows = []
    if market == "passing_yards":
        point, point_name, point_rows = point_policy(initial, psel, train, cols, p)
    changed = market in p["probability_changed_markets"]
    levels = [0.05, 0.25, 0.5, 0.75, 0.95] if changed else [0.05, 0.95]
    qs = []
    for level in levels:
        q = HistGradientBoostingRegressor(
            loss="quantile",
            quantile=level,
            max_iter=100,
            max_leaf_nodes=7,
            min_samples_leaf=30,
            early_stopping=False,
            random_state=p["seed"],
        )
        q.fit(train[cols], train.y)
        qs.append(q)
    b = {
        "market": market,
        "year": year,
        "features": cols,
        "point": point,
        "point_method": point_name,
        "count": MARKETS[market][3],
        "incumbent": base,
        "quantiles": qs,
        "quantile_levels": levels,
        "tail_weight": p["tail_weight"],
        "joint": None,
        "calibrators": {},
        "information_available_at": selection.completed_at.max().isoformat(),
        "max_training_available_at": train.completed_at.max().isoformat(),
    }
    rmu, _ = prediction(b, residual)
    error = residual.y.to_numpy() - rmu
    train_mu = point.predict(train[cols])
    if b["count"]:
        train_mu = np.maximum(train_mu, 0)
    b.update(
        bias=float(np.mean(error)),
        scale=max(float(np.std(error)), 1e-3),
        in_sample_scale=max(float(np.std(train.y - train_mu)), 1e-3),
        scaled_errors=np.sort(
            error
            / (np.sqrt(np.maximum(rmu, 1)) if b["count"] else np.maximum(abs(rmu), 10))
        ),
    )
    kinds = ["reference", "normal_oos", "scaled_empirical", "dense_quantile"]
    if changed and b["count"]:
        if market == "completions":
            joint_rows = train[train.attempts.notna()]
            b["joint"] = CompletionThinning().fit(
                joint_rows[cols], joint_rows.attempts, joint_rows.y
            )
            amu = b["joint"].attempt_mean(residual[cols])
            labels = residual.attempts.to_numpy()
        else:
            amu = base["poisson"].predict(residual[cols])
            labels = residual.y.to_numpy()
        ok = np.isfinite(labels)
        b["alpha"] = shrink_dispersion(
            amu[ok], labels[ok], p["nb_prior_strength"], p["nb_prior_alpha"]
        )
        kinds.append("nb2")
    candidate_rows = []
    if changed:
        clines = probe_lines(calibration, market, p)
        slines = probe_lines(selection, market, p)
        cy = (calibration.y.to_numpy()[:, None] > clines).astype(int)
        sy = (selection.y.to_numpy()[:, None] > slines).astype(int)
        errors = {}
        briers = {}
        for kind in kinds:
            raw = kind + "|identity"
            pc = probabilities(
                candidate_cdf(b, calibration, raw, tail_weight=0), clines
            )
            cmu, _ = prediction(b, calibration)
            anchor_prob = probabilities(
                student_cdf(cmu, b["bias"], b["scale"], b["count"]), clines
            )
            # Sigmoid is fitted before the separate selection window. The final
            # tail mixture is retained for every candidate, including reference.
            b["calibrators"][kind + "|sigmoid"] = ShrunkSigmoid(
                p["calibration_penalty"]
            ).fit(pc.ravel(), cy.ravel(), anchor_prob.ravel(), b["tail_weight"])
            for method in ["identity", "sigmoid"]:
                key = kind + "|" + method
                q = probabilities(candidate_cdf(b, selection, key), slines)
                bs, ll = binary_scores(q, sy)
                errors[key] = ll.mean(axis=1)
                briers[key] = bs.mean(axis=1)
        reference = "reference|identity"
        winner = reference
        winner_loss = float(errors[reference].mean())
        for key, ll in errors.items():
            g = selection[["season", "week"]].copy()
            g["delta"] = ll - errors[reference]
            low, high = week_block_interval(
                g,
                "delta",
                reps=p["bootstrap_replicates"],
                block=p["bootstrap_week_block"],
            )
            gain = float(errors[reference].mean() - ll.mean())
            accepted = key == reference or (
                selection.week.nunique() >= p["minimum_gate_weeks"]
                and high < 0
                and gain >= p["probability_minimum_log_loss_gain"]
                and float(briers[key].mean()) <= float(briers[reference].mean())
            )
            candidate_rows.append(
                dict(
                    candidate=key,
                    selection_log_loss=float(ll.mean()),
                    selection_brier=float(briers[key].mean()),
                    delta_log_loss_low=low,
                    delta_log_loss_high=high,
                    accepted=bool(accepted),
                )
            )
            if accepted and float(ll.mean()) < winner_loss:
                winner = key
                winner_loss = float(ll.mean())
        b["selected_probability"] = winner
    else:
        b["selected_probability"] = "retain_stage1b"
    _, cq = prediction(b, calibration)
    b["cqr_offset"] = float(
        np.ceil(
            conformal_offset(
                calibration.y, np.floor(cq[:, 0]), np.ceil(cq[:, -1]), p["cqr_alpha"]
            )
        )
    )
    intervals_info = {}
    for name in ["normal_oos", "cqr"]:
        lo, hi = intervals(b, selection, name)
        intervals_info[name] = {
            "score": float(interval_score(selection.y, lo, hi).mean()),
            "coverage": float(((selection.y >= lo) & (selection.y <= hi)).mean()),
            "width": float(np.mean(hi - lo)),
        }
    ref = intervals_info["normal_oos"]
    alt = intervals_info["cqr"]
    b["selected_interval"] = (
        "cqr"
        if alt["coverage"] >= 0.85
        and alt["score"] < ref["score"] * (1 - p["interval_minimum_relative_gain"])
        else "normal_oos"
    )
    info = {
        "market": market,
        "season": year,
        "point_method": point_name,
        "probability_method": b["selected_probability"],
        "interval_method": b["selected_interval"],
        "phase_n": dict(
            zip(
                [
                    "point_train",
                    "point_select",
                    "refit_train",
                    "distribution",
                    "calibration",
                    "selection",
                    "evaluation",
                ],
                map(
                    len,
                    [initial, psel, train, residual, calibration, selection, evaluate],
                ),
            )
        ),
        "maximum_training_information": b["max_training_available_at"],
        "maximum_selection_information": b["information_available_at"],
        "evaluation_first_decision": evaluate.prediction_at.min().isoformat(),
        "point_candidates": point_rows,
        "probability_candidates": candidate_rows,
        "interval_candidates": intervals_info,
    }
    return b, info, evaluate


def evaluate(b, d, p):
    market = b["market"]
    base = b["incumbent"]
    basepred = model_predictions(base, d)
    oldcdf = cdf_for(
        base, base["selected_kind"], basepred, base["selected_calibration"]
    )
    cdf = final_cdf(b, d)
    mu, _ = prediction(b, d)
    lo, hi = intervals(b, d, b["selected_interval"])
    from stage1b.probability import inverse_cdf

    oldlo = inverse_cdf(oldcdf, len(d), 0.05)
    oldhi = inverse_cdf(oldcdf, len(d), 0.95)
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
        ]
    ].reset_index(drop=True)
    f["market"] = market
    f["row_id"] = market + "|" + f.player_id + "|" + f.game_id
    f["projection"] = mu
    f["stage1b_projection"] = basepred[0]
    f["naive"] = d[feature_columns(market)[0]].to_numpy()
    f["lower90"] = lo
    f["upper90"] = hi
    f["stage1b_lower90"] = oldlo
    f["stage1b_upper90"] = oldhi
    f["selected_method"] = b["selected_probability"]
    f["point_method"] = b["point_method"]
    f["interval_method"] = b["selected_interval"]
    f["evaluation_tier"] = "monitoring" if b["year"] == 2026 else "development_oos"
    f["interval_score"] = interval_score(f.y, lo, hi)
    f["stage1b_interval_score"] = interval_score(f.y, oldlo, oldhi)
    lines = probe_lines(d, market, p)
    truth = (d.y.to_numpy()[:, None] > lines).astype(int)
    records = []
    for name, curve in [("stage1b", oldcdf), ("stage1b1", cdf)]:
        prob = probabilities(curve, lines)
        bs, ll = binary_scores(prob, truth)
        for i, mult in enumerate(p["probe_multipliers"]):
            q = f[
                ["row_id", "market", "season", "week", "game_id", "evaluation_tier"]
            ].copy()
            q["version"] = name
            q["line"] = lines[:, i]
            q["probe_multiplier"] = mult
            q["probability"] = prob[:, i]
            q["event"] = truth[:, i]
            q["brier"] = bs[:, i]
            q["log_loss"] = ll[:, i]
            q["line_kind"] = "hypothetical_pregame_halfline_NOT_BOOKMAKER"
            records.append(q)
    return f, pd.concat(records, ignore_index=True)


def run(root, identifier):
    from stage1b1.artifacts import source_hashes, validate, validate_results

    root = Path(root).resolve()
    p = json.loads((root / "stage1b1/protocol.json").read_text())
    runtime_info = runtime(root)
    if not identifier or any(
        c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in identifier
    ):
        raise ValueError("Invalid experiment ID")
    target = root / "experiments/stage1b1" / identifier
    if target.exists():
        raise ValueError("Immutable experiment ID already exists")
    src = source_hashes(root)
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--", *src], cwd=root, text=True
    )
    if dirty.strip():
        raise ValueError("Commit source/protocol before experiment")
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    baseline = root / "experiments/stage1b" / p["baseline_experiment"]
    bm = validate_baseline(baseline, root)
    input_path = root / bm["input_relative_path"]
    input_hash = digest(input_path)
    panel = prepare_panel(read_development_snapshot(input_path, p), p)
    frames = []
    probes = []
    folds = []
    coverage = []
    with tempfile.TemporaryDirectory(prefix="nfl-stage1b1-") as tmp:
        work = Path(tmp)
        (work / "models").mkdir()
        started = datetime.now(timezone.utc).isoformat()
        for market in MARKETS:
            d = market_panel(panel, market)
            for year in p["evaluation_seasons"]:
                print("EVALUATING", market, year, flush=True)
                base = joblib.load(baseline / "models" / f"{market}-{year}.joblib")
                b, info, e = fit(d, market, year, base, p)
                f, q = evaluate(b, e, p)
                frames.append(f)
                probes.append(q)
                folds.append(info)
                candidates = d[d.season.eq(year)]
                coverage.append(
                    dict(
                        market=market,
                        season=year,
                        pregame_candidates=len(candidates),
                        evaluated=len(e),
                        zeros=int(e.y.eq(0).sum()),
                        excluded_missing_features=int(
                            (~candidates.feature_complete).sum()
                        ),
                        excluded_unscorable=int(
                            (candidates.feature_complete & ~candidates.scorable).sum()
                        ),
                    )
                )
                joblib.dump(b, work / "models" / f"{market}-{year}.joblib", compress=3)
        f = pd.concat(frames, ignore_index=True)
        q = pd.concat(probes, ignore_index=True)
        f.to_parquet(work / "forecasts.parquet", index=False)
        q.to_parquet(work / "probes.parquet", index=False)
        # Point/interval accuracy uses the actual 90% interval, not mislabelled .1/.9 quantiles.
        a, point_intervals = summaries(f, p)
        a.to_csv(work / "accuracy.csv", index=False)
        point_intervals.to_csv(
            work / "paired_point_interval_differences.csv", index=False
        )
        probability_summary(q, p).to_csv(work / "probability_metrics.csv", index=False)
        reliability(q, p).to_csv(work / "reliability.csv", index=False)
        paired = q.copy()
        paired["version"] = paired.version.map(
            {"stage1b": "stage1a_normal_rule", "stage1b1": "selected_stage1b"}
        )
        paired_improvements(paired, p).to_csv(
            work / "paired_probability_differences.csv", index=False
        )
        pd.DataFrame(coverage).to_csv(work / "coverage.csv", index=False)
        (work / "folds.json").write_text(json.dumps(folds, indent=2) + "\n")
        (work / "protocol.json").write_text(json.dumps(p, indent=2) + "\n")
        if src != source_hashes(root) or digest(input_path) != input_hash:
            raise ValueError("Source or input changed during experiment")
        manifest = {
            "schema_version": 1,
            "experiment_id": identifier,
            "status": "passed",
            "final_period_sealed": True,
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "source_commit": source_commit,
            "source_hashes": src,
            "runtime": runtime_info,
            "baseline_path": str(baseline.relative_to(root)),
            "baseline_manifest_sha256": digest(baseline / "manifest.json"),
            "input_path": str(input_path.relative_to(root)),
            "input_sha256": input_hash,
            "files": {
                str(x.relative_to(work)): digest(x)
                for x in sorted(work.rglob("*"))
                if x.is_file()
            },
            "n_player_market_games": len(f),
            "genuine_quotes": 0,
            "betting_profit": None,
        }
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        validate(work, root)
        validate_results(work, root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, target)
    print("PASSED", target, flush=True)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    run(ROOT, args.id)
