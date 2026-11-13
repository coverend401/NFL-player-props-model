"""Annual rolling-origin evaluation; no production models, APIs or final outcomes used."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge, LogisticRegression, PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from stage1b.point_models import CareerMean
from stage1b.data import (
    prepare_panel,
    market_panel,
    feature_columns,
    before,
    MARKETS,
    read_development_snapshot,
)
from stage1b.probability import Distribution, Calibration, outcomes, inverse_cdf
from stage1b.metrics import (
    binary_scores,
    accuracy,
    reliability,
    probability_summary,
    paired_improvements,
)
from stage1b.artifacts import (
    digest,
    runtime,
    validate,
    validate_results,
    freeze_sources,
    verify_sources,
    require_committed_sources,
)


def probe_lines(d, market, protocol):
    # Explicit hypothetical HALF lines determined only from historical features.
    mean = np.maximum(d[feature_columns(market)[0]].to_numpy(), 0)
    return np.column_stack(
        [np.floor(mean * m) + 0.5 for m in protocol["probe_multipliers"]]
    )


def probabilities(cdf, lines):
    return np.column_stack(
        [outcomes(cdf, lines[:, i])[:, 0] for i in range(lines.shape[1])]
    )


def model_predictions(bundle, d):
    x = d[bundle["features"]]
    mu = bundle["point"].predict(x)
    if bundle.get("is_count", False):
        mu = np.maximum(mu, 0)
    zero = (
        bundle["zero"].predict_proba(x)[:, 1]
        if bundle["zero"] is not None
        else np.full(len(d), bundle["zero_rate"])
    )
    quantile = np.column_stack([q.predict(x) for q in bundle["quantiles"]])
    poisson = bundle["poisson"].predict(x) if bundle["poisson"] is not None else mu
    return mu, zero, quantile, poisson


def cdf_for(bundle, kind, prediction, calibration=None):
    mu, zero, quantiles, poisson = prediction
    base = bundle["distributions"][kind].cdf(
        poisson if kind in ("poisson", "negative_binomial") else mu,
        zero_probability=zero,
        quantiles=quantiles,
    )
    return base if calibration is None else calibration.cdf(base)


def price_bundle(bundle, d, lines):
    """Same model path for future authentic-quote replay, with push mass intact."""
    prediction = model_predictions(bundle, d)
    cdf = cdf_for(
        bundle, bundle["selected_kind"], prediction, bundle["selected_calibration"]
    )
    return outcomes(cdf, lines)


def fit_fold(d, market, year, protocol):
    cols = feature_columns(market)
    count = MARKETS[market][3]
    eval_candidates = d[d.season.eq(year)]
    if eval_candidates.empty:
        return None
    # Selection labels are separated from model fitting and distribution fitting.
    point_select = d[d.season.eq(year - 2)]
    calibrating = d[d.season.eq(year - 1)]
    if point_select.empty or calibrating.empty:
        return None
    select_cutoff = point_select.prediction_at.min()
    residual_cutoff = calibrating.prediction_at.min()
    eval_cutoff = eval_candidates.prediction_at.min()
    initial = before(d, select_cutoff)
    select = before(point_select, residual_cutoff)
    train = before(d, residual_cutoff)
    residual_candidates = calibrating[
        calibrating.week <= protocol["distribution_fit_last_week"]
    ]
    calibration_candidates = calibrating[
        (calibrating.week > protocol["distribution_fit_last_week"])
        & (calibrating.week <= protocol["calibration_last_week"])
    ]
    selection_candidates = calibrating[
        calibrating.week > protocol["calibration_last_week"]
    ]
    if calibration_candidates.empty or selection_candidates.empty:
        return None
    residual = before(residual_candidates, calibration_candidates.prediction_at.min())
    calibration = before(
        calibration_candidates, selection_candidates.prediction_at.min()
    )
    selection = before(selection_candidates, eval_cutoff)
    phases = [initial, select, train, residual, calibration, selection]
    if min(map(len, phases)) < protocol["minimum_phase_rows"]:
        return None
    builders = {
        "career_mean": lambda: CareerMean(),
        "ridge": lambda: Ridge(alpha=1.0),
        "gradient_boosting": lambda: GradientBoostingRegressor(
            n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42
        ),
    }
    point_scores = {}
    for name, build in builders.items():
        m = build()
        if name != "career_mean":
            m.fit(initial[cols], initial.y)
        selection_prediction = m.predict(select[cols])
        if count:
            selection_prediction = np.maximum(selection_prediction, 0)
        point_scores[name] = float(np.mean(np.abs(selection_prediction - select.y)))
    winner = min(point_scores, key=point_scores.get)
    point = builders[winner]()
    if winner != "career_mean":
        point.fit(train[cols], train.y)
    train_prediction = point.predict(train[cols])
    if count:
        train_prediction = np.maximum(train_prediction, 0)
    sigma = max(float(np.std(train.y - train_prediction)), 1e-3)
    zero = None
    if train.y.eq(0).nunique() == 2:
        zero = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=500, random_state=protocol["seed"]),
        )
        zero.fit(train[cols], train.y.eq(0).astype(int))
    poisson = None
    if count:
        poisson = make_pipeline(
            StandardScaler(), PoissonRegressor(alpha=1.0, max_iter=500)
        )
        poisson.fit(train[cols], train.y)
    qs = []
    for q in [0.1, 0.5, 0.9]:
        m = HistGradientBoostingRegressor(
            loss="quantile",
            quantile=q,
            max_iter=100,
            max_leaf_nodes=7,
            min_samples_leaf=30,
            early_stopping=False,
            random_state=protocol["seed"],
        )
        m.fit(train[cols], train.y)
        qs.append(m)
    kinds = [
        "stage1a_normal",
        "normal_oos",
        "empirical",
        "scaled_empirical",
        "hurdle",
        "quantile",
    ]
    if count:
        kinds += ["poisson", "negative_binomial"]
    bundle = {
        "features": cols,
        "point": point,
        "zero": zero,
        "poisson": poisson,
        "zero_rate": float(train.y.eq(0).mean()),
        "quantiles": qs,
        "distributions": {},
        "is_count": count,
        "point_method": winner,
        "market": market,
        "year": year,
        "train_completed_before": residual_cutoff.isoformat(),
        "max_training_outcome_available": train.completed_at.max().isoformat(),
        "model_information_available_at": selection.completed_at.max().isoformat(),
        "replay_status": "counterfactual reconstruction; not a historically published forecast",
        "model_information_cutoff": selection.completed_at.max().isoformat(),
    }
    rpred = model_predictions(bundle, residual)
    for kind in kinds:
        mu = rpred[3] if kind in ("poisson", "negative_binomial") else rpred[0]
        bundle["distributions"][kind] = Distribution(kind, count).fit(
            mu, residual.y, in_sample_scale=sigma
        )
    cpred = model_predictions(bundle, calibration)
    spred = model_predictions(bundle, selection)
    clines = probe_lines(calibration, market, protocol)
    slines = probe_lines(selection, market, protocol)
    cy = (calibration.y.to_numpy()[:, None] > clines).astype(int)
    sy = (selection.y.to_numpy()[:, None] > slines).astype(int)
    candidates = []
    calibrators = {}
    for kind in kinds:
        cprob = probabilities(cdf_for(bundle, kind, cpred), clines)
        sprob = probabilities(cdf_for(bundle, kind, spred), slines)
        for method in ["identity", "sigmoid", "isotonic"]:
            # Preserve an untouched legacy-rule comparator, never calibrate it.
            if kind == "stage1a_normal" and method != "identity":
                continue
            cal = Calibration(method).fit(cprob.ravel(), cy.ravel())
            p = cal(sprob)
            brier, ll = binary_scores(p, sy)
            key = kind + "|" + method
            calibrators[key] = cal
            candidates.append(
                {
                    "market": market,
                    "season": year,
                    "candidate": key,
                    "selection_n": len(selection),
                    "selection_brier": float(brier.mean()),
                    "selection_log_loss": float(ll.mean()),
                }
            )
    # The legacy rule is a benchmark, not a deployable calibrated candidate.
    eligible = [
        x for x in candidates if not x["candidate"].startswith("stage1a_normal|")
    ]
    best = min(eligible, key=lambda x: (x["selection_log_loss"], x["candidate"]))
    kind, method = best["candidate"].split("|")
    bundle["calibrators"] = calibrators
    bundle["selected_kind"] = kind
    bundle["selected_calibration"] = calibrators[best["candidate"]]
    bundle["selected_candidate"] = best["candidate"]
    info = dict(
        market=market,
        season=year,
        point_method=winner,
        point_selection_mae=point_scores,
        selected=best["candidate"],
        phase_n=dict(
            zip(
                [
                    "point_train",
                    "point_select",
                    "refit_train",
                    "distribution_fit",
                    "calibration",
                    "method_selection",
                ],
                map(len, phases),
            )
        ),
        train_cutoff=residual_cutoff.isoformat(),
        calibration_cutoff=selection_candidates.prediction_at.min().isoformat(),
        selection_cutoff=eval_cutoff.isoformat(),
        maximum_training_outcome=train.completed_at.max().isoformat(),
        maximum_selection_outcome=selection.completed_at.max().isoformat(),
    )
    return bundle, info, candidates


def evaluate_fold(bundle, d, year, protocol):
    market = bundle["market"]
    candidates = d[d.season.eq(year)]
    eval_data = candidates[candidates.feature_complete & candidates.scorable].copy()
    if eval_data.empty:
        raise ValueError("Empty evaluation fold")
    pred = model_predictions(bundle, eval_data)
    selected_cdf = cdf_for(
        bundle, bundle["selected_kind"], pred, bundle["selected_calibration"]
    )
    baseline_cdf = cdf_for(bundle, "stage1a_normal", pred)
    lines = probe_lines(eval_data, market, protocol)
    event = (eval_data.y.to_numpy()[:, None] > lines).astype(int)
    selected = probabilities(selected_cdf, lines)
    baseline = probabilities(baseline_cdf, lines)
    # Disagreement is a descriptive diagnostic, not a confidence percentage.
    alternatives = np.stack(
        [
            probabilities(cdf_for(bundle, k, pred), lines)
            for k in bundle["distributions"]
            if k != "stage1a_normal"
        ]
    )
    identity = eval_data[
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
    identity["row_id"] = market + "|" + identity.player_id + "|" + identity.game_id
    identity["market"] = market
    identity["projection"] = pred[0]
    identity["naive"] = eval_data[feature_columns(market)[0]].to_numpy()
    identity["lower90"] = inverse_cdf(selected_cdf, len(identity), 0.05)
    identity["upper90"] = inverse_cdf(selected_cdf, len(identity), 0.95)
    identity["q10"] = np.sort(pred[2], axis=1)[:, 0]
    identity["q90"] = np.sort(pred[2], axis=1)[:, -1]
    identity["selected_method"] = bundle["selected_candidate"]
    identity["evaluation_tier"] = "monitoring" if year == 2026 else "development_oos"
    probes = []
    for name, p in [("stage1a_normal_rule", baseline), ("selected_stage1b", selected)]:
        brier, ll = binary_scores(p, event)
        for i, multiplier in enumerate(protocol["probe_multipliers"]):
            q = identity[
                ["row_id", "market", "season", "week", "game_id", "evaluation_tier"]
            ].copy()
            q["version"] = name
            q["probe_multiplier"] = multiplier
            q["line"] = lines[:, i]
            q["probability"] = p[:, i]
            q["event"] = event[:, i]
            q["brier"] = brier[:, i]
            q["log_loss"] = ll[:, i]
            q["model_disagreement"] = alternatives[:, :, i].max(axis=0) - alternatives[
                :, :, i
            ].min(axis=0)
            q["line_kind"] = "hypothetical_pregame_halfline_NOT_BOOKMAKER"
            probes.append(q)
    coverage = {
        "market": market,
        "season": year,
        "pregame_panel_candidates": len(candidates),
        "missing_pregame_features_or_availability": int(
            (~candidates.feature_complete).sum()
        ),
        "unscorable_with_complete_features": int(
            (candidates.feature_complete & ~candidates.scorable).sum()
        ),
        "evaluated": len(identity),
        "observed_zero_outcomes": int(identity.y.eq(0).sum()),
    }
    diagnostics = []
    for key, cal in bundle["calibrators"].items():
        kind = key.split("|")[0]
        probability = cal(probabilities(cdf_for(bundle, kind, pred), lines))
        brier, ll = binary_scores(probability, event)
        diagnostics.append(
            dict(
                market=market,
                season=year,
                candidate=key,
                n=len(identity),
                brier=float(brier.mean()),
                log_loss=float(ll.mean()),
                purpose="diagnostic_only_NOT_USED_FOR_SELECTION",
            )
        )
    return identity, pd.concat(probes, ignore_index=True), coverage, diagnostics


def run(root, experiment_id):
    root = Path(root).resolve()
    protocol = json.loads((root / "stage1b/protocol.json").read_text())
    if not experiment_id or any(
        c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in experiment_id
    ):
        raise ValueError("Use a simple immutable experiment ID")
    target = root / "experiments/stage1b" / experiment_id
    if target.exists():
        raise ValueError("Experiment IDs are immutable")
    rt = runtime(root)
    source_commit = require_committed_sources(root)
    source_hashes = freeze_sources(root)
    from release_utils import resolve_release

    data, release = resolve_release(root)
    source = data / "player_features.parquet"
    input_hash = digest(source)
    panel = prepare_panel(read_development_snapshot(source, protocol), protocol)
    if digest(source) != input_hash:
        raise ValueError("Input snapshot changed during loading")
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="nfl-stage1b-") as tmp:
        work = Path(tmp)
        (work / "models").mkdir()
        forecasts = []
        probes = []
        folds = []
        candidates = []
        coverage = []
        diagnostics = []
        for market in MARKETS:
            d = market_panel(panel, market)
            for year in protocol["evaluation_seasons"]:
                print("EVALUATING", market, year, flush=True)
                fitted = fit_fold(d, market, year, protocol)
                if fitted is None:
                    raise ValueError(f"Insufficient historical phases: {market}/{year}")
                bundle, info, scores = fitted
                f, p, cov, diagnostic = evaluate_fold(bundle, d, year, protocol)
                diagnostics.extend(diagnostic)
                forecasts.append(f)
                probes.append(p)
                folds.append(info)
                candidates.extend(scores)
                coverage.append(cov)
                joblib.dump(
                    bundle, work / "models" / f"{market}-{year}.joblib", compress=3
                )
        f = pd.concat(forecasts, ignore_index=True)
        p = pd.concat(probes, ignore_index=True)
        if (f.prediction_at >= pd.Timestamp(protocol["final_start"])).any():
            raise ValueError("Sealed final period entered experiment")
        if (f.history_available_at >= f.prediction_at).any():
            raise ValueError("Unavailable history entered forecast")
        f.to_parquet(work / "forecasts.parquet", index=False)
        p.to_parquet(work / "probes.parquet", index=False)
        accuracy(f).to_csv(work / "accuracy.csv", index=False)
        reliability(p, protocol).to_csv(work / "reliability.csv", index=False)
        probability_summary(p, protocol).to_csv(
            work / "probability_metrics.csv", index=False
        )
        paired_improvements(p, protocol).to_csv(
            work / "paired_differences.csv", index=False
        )
        pd.DataFrame(coverage).to_csv(work / "coverage.csv", index=False)
        pd.DataFrame(candidates).to_csv(work / "candidate_selection.csv", index=False)
        pd.DataFrame(diagnostics).to_csv(
            work / "candidate_outer_metrics.csv", index=False
        )
        (work / "folds.json").write_text(json.dumps(folds, indent=2) + "\n")
        (work / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
        (work / "betting_status.json").write_text(
            json.dumps(
                {
                    "authentic_quotes": 0,
                    "genuine_bets": 0,
                    "realised_profit": None,
                    "reason": "No timestamped, provenance-reviewed historical bookmaker player-prop prices supplied. Probes are not odds.",
                },
                indent=2,
            )
            + "\n"
        )
        verify_sources(root, source_hashes)
        if digest(source) != input_hash:
            raise ValueError("Input snapshot changed during experiment")
        manifest = {
            "schema_version": 1,
            "experiment_id": experiment_id,
            "status": "passed",
            "final_period_sealed": True,
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "source_commit": source_commit,
            "input_release": release["release_id"],
            "input_relative_path": str(source.relative_to(root)),
            "input_sha256": input_hash,
            "runtime": rt,
            "source_hashes": source_hashes,
            "files": {
                str(s.relative_to(work)): digest(s)
                for s in sorted(work.rglob("*"))
                if s.is_file()
            },
            "n_player_games": len(f),
            "n_probes": len(p),
            "genuine_betting_results": False,
            "interpretation": "Development OOS / monitoring; retrospective stat revisions and roster-selection limitations remain.",
        }
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        validate(work, root)
        validate_results(work)
        shutil.copytree(work, target)
    print("PASSED", target, flush=True)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], args.id)
