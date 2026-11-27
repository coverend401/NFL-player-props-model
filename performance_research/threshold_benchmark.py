"""Chronological fundamental-model sprint; statistical lines, never bookmaker prices."""

import argparse
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd

from season_intelligence.probability import HurdleEmpirical
from stage1b.data import MARKETS
from weekly_learning.store import ROOT, Store, sha

from .study import holm, paired_weeks, permitted
from .threshold_models import (
    EPS,
    NEW,
    REFERENCES,
    ThresholdModels,
    loss_metrics,
    normal_reference,
    proposals,
)

PROTOCOL = Path(__file__).with_name("threshold_protocol.json")
SOURCE = ROOT / "experiments/season_intelligence/sunday-20261121-v1"


def input_data():
    m = json.loads((SOURCE / "manifest.json").read_text())
    path = SOURCE / "historical_predictions.parquet"
    if sha(path) != m["files"][path.name]:
        raise ValueError("Historical prediction integrity failed")
    raw = ROOT / m["player_source"]
    if sha(raw) != m["player_source_sha256"]:
        raise ValueError("Opportunity source integrity failed")
    filters = [[("season", "<=", 2025)], [("season", "==", 2026), ("week", "<=", 10)]]
    d = permitted(pd.read_parquet(path, filters=filters))
    opp = pd.read_parquet(
        raw,
        columns=["game_id", "player_id", "attempts", "carries", "targets"],
        filters=filters,
    )
    if opp.duplicated(["game_id", "player_id"]).any():
        raise ValueError("Ambiguous historical opportunity identity")
    opp = opp.rename(
        columns={c: "actual_" + c for c in ["attempts", "carries", "targets"]}
    )
    d = d.merge(opp, on=["game_id", "player_id"], how="left", validate="many_to_one")
    d["observed_opportunity"] = np.nan
    d["lag_anchor"] = np.nan
    for market, (target, _, opportunity, _) in MARKETS.items():
        mask = d.market.eq(market)
        d.loc[mask, "observed_opportunity"] = d.loc[mask, "actual_" + opportunity]
        past = d.loc[mask, [target + "_last5", target + "_career"]]
        d.loc[mask, "lag_anchor"] = past.mean(axis=1, skipna=True)
    for col in [
        "prediction_at",
        "kickoff_at",
        "history_available_at",
        "model_fit_before",
        "available_at",
    ]:
        d[col] = pd.to_datetime(d[col], utc=True)
    if not (
        (d.history_available_at < d.prediction_at)
        & (d.model_fit_before < d.prediction_at)
        & (d.prediction_at <= d.kickoff_at - pd.Timedelta(minutes=60))
        & (d.available_at > d.prediction_at)
    ).all():
        raise ValueError("Historical timing failed")
    d["weekly_decision_at"] = d.groupby(["season", "week"]).prediction_at.transform(
        "min"
    )
    before = len(d)
    d = d[
        np.isfinite(d.lag_anchor)
        & np.isfinite(d.baseline)
        & np.isfinite(d.champion_sigma)
        & d.champion_sigma.gt(0)
    ].copy()
    return d.sort_values(
        ["season", "week", "game_id", "player_id", "market"]
    ).reset_index(drop=True), {
        "source_sha256": sha(path),
        "opportunity_source_sha256": sha(raw),
        "common_missing_lag_or_reference_exclusions": before - len(d),
    }


def split_fold(data, year):
    test = data[data.season.eq(year)].copy()
    previous = data[data.season.eq(year - 1)].copy()
    calibration = previous[previous.week.le(9)].copy()
    validation = previous[previous.week.ge(10)].copy()
    train = data[
        data.season.ge(2022)
        & data.season.le(year - 2)
        & data.available_at.lt(calibration.prediction_at.min())
    ].copy()
    calibration = calibration[
        calibration.available_at.lt(validation.prediction_at.min())
    ]
    validation = validation[validation.available_at.lt(test.prediction_at.min())]
    if min(len(train), len(calibration), len(validation), len(test)) < 50:
        raise ValueError("Insufficient chronological fold population")
    target = MARKETS[str(data.market.iloc[0])][0]
    scale = max(float((train.y - train.lag_anchor).std()), 1.0)
    for f in [train, calibration, validation, test]:
        f["known_scale"] = f[target + "_sd5"].fillna(scale).clip(lower=1)
    return train, calibration, validation, test


def empirical_reference(frame, training, current_method, mode):
    if mode != "empirical":
        return normal_reference(frame)
    law = HurdleEmpirical().fit(training[current_method], training.y, training.position)
    count = MARKETS[str(frame.market.iloc[0])][3]
    result = np.zeros(len(frame))
    mu = frame[current_method].to_numpy()
    # One conditional distribution per player-game, queried at each fixed threshold.
    for ids in frame.groupby(["game_id", "player_id"]).groups.values():
        ids = np.asarray(list(ids))
        local = frame.index.get_indexer(ids)
        values, weights = law.samples(
            mu[local[0]], frame.loc[ids[0], "position"], count
        )
        cum = np.r_[0.0, np.cumsum(weights)]
        at = np.searchsorted(
            values, frame.loc[ids, "research_line"].to_numpy(), side="right"
        )
        result[local] = 1 - cum[at]
    return np.clip(result, EPS, 1 - EPS)


def select_rows(frame, method, mode, *, cutoff=0.0):
    f = frame.copy()
    f["probability"] = np.maximum(f[method], 1 - f[method])
    f["side"] = np.where(f[method] >= 0.5, "over", "under")
    f["hit"] = np.where(f[method] >= 0.5, f.observed_over, 1 - f.observed_over)
    # Reconstruct one weekly decision state; later player-history information cannot rank earlier selections.
    first = (
        f.weekly_decision_at
        if "weekly_decision_at" in f
        else f.groupby(["season", "week"]).prediction_at.transform("min")
    )
    f = f[f.history_available_at.lt(first) & f.probability.ge(cutoff)]
    f = f.sort_values(
        ["probability", "game_id", "player_id", "market", "research_line"],
        ascending=[False, True, True, True, True],
    )
    if mode == "slate":
        f = f.drop_duplicates(["season", "week", "player_id"])
        return f.groupby(["season", "week"], sort=False).head(8)
    f = f.drop_duplicates(["game_id", "player_id"])
    return f.groupby("game_id", sort=False).head(2)


def policy_cutoff(frame, method, policy):
    p = policy["selection"]
    for cutoff in p["probability_cutoffs"]:
        f = select_rows(frame, method, "slate", cutoff=cutoff)
        weekly = f.groupby(["season", "week"]).hit.mean()
        if len(f) < p["validation_min_legs"] or len(weekly) < p["validation_min_weeks"]:
            continue
        values = weekly.to_numpy()
        blocks = np.array([values[i : i + 2].mean() for i in range(0, len(values), 2)])
        draws = (
            np.random.default_rng(policy["seed"])
            .choice(blocks, (1000, len(blocks)), replace=True)
            .mean(axis=1)
        )
        gap = abs(float(f.probability.mean() - f.hit.mean()))
        if (
            f.hit.mean() >= p["validation_hit_rate_min"]
            and np.quantile(draws, 0.025) >= p["validation_week_bootstrap_lower_min"]
            and gap <= p["calibration_gap_max"]
        ):
            return float(cutoff)
    return None


def validated_members(frame):
    base = loss_metrics(frame, "champion_normal")
    eligible, metrics = [], {}
    for method in NEW[:-1]:
        score = loss_metrics(frame, method)
        metrics[method] = score
        if (
            score["player_markets"] >= 100
            and score["log_loss"] <= 0.99 * base["log_loss"]
            and score["brier"] <= base["brier"]
            and score["calibration_gap"] <= 0.05
        ):
            eligible.append(method)
    return eligible, metrics


def fit_market(data, year, policy, current):
    train, calibration, validation, test = split_fold(data, year)
    model = ThresholdModels(str(data.market.iloc[0]), policy).fit(train, calibration)
    vp = proposals(validation, model.offsets)
    tp = proposals(test, model.offsets)
    for frame in [vp, tp]:
        predictions = model.predict(frame)
        for name, values in predictions.items():
            frame[name] = values
        frame["champion_normal"] = normal_reference(frame)
        frame["threshold_prior"] = frame.threshold_level.map(model.priors)
    vp["existing_research"] = empirical_reference(
        vp, train, current["point"], current["mode"]
    )
    all_prior = data[data.available_at.lt(test.prediction_at.min())]
    tp["existing_research"] = empirical_reference(
        tp, all_prior, current["point"], current["mode"]
    )
    eligible, validation_metrics = validated_members(vp)
    for frame in [vp, tp]:
        frame["validated_ensemble"] = (
            frame[eligible].mean(axis=1) if eligible else frame.champion_normal
        )
    cuts = {method: policy_cutoff(vp, method, policy) for method in REFERENCES + NEW}
    q = model.interval(test)
    metadata = {
        **model.fit_details,
        "market": str(data.market.iloc[0]),
        "test_year": year,
        "train_max_outcome_available_at": train.available_at.max().isoformat(),
        "calibration_first_prediction": calibration.prediction_at.min().isoformat(),
        "calibration_max_outcome_available_at": calibration.available_at.max().isoformat(),
        "validation_first_prediction": validation.prediction_at.min().isoformat(),
        "validation_max_outcome_available_at": validation.available_at.max().isoformat(),
        "test_first_prediction": test.prediction_at.min().isoformat(),
        "ensemble_members": eligible,
        "ensemble_fallback": not bool(eligible),
        "component_validation": validation_metrics,
        "selection_cutoffs": cuts,
        "current_probability_reference_mode": current["mode"],
        "quantile_20_coverage": float(np.mean(test.y.to_numpy() <= q[:, 0])),
        "quantile_80_coverage": float(np.mean(test.y.to_numpy() <= q[:, 2])),
        "interval_20_80_coverage": float(
            np.mean((test.y.to_numpy() >= q[:, 0]) & (test.y.to_numpy() <= q[:, 2]))
        ),
        "interval_20_80_width": float(np.mean(q[:, 2] - q[:, 0])),
    }
    keep = [
        "game_id",
        "player_id",
        "market",
        "position",
        "season",
        "week",
        "prediction_at",
        "history_available_at",
        "weekly_decision_at",
        "threshold_level",
        "research_line",
        "observed_over",
        *REFERENCES,
        *NEW,
    ]
    return tp[keep], vp[keep], metadata


def unit_balanced_difference(frame, difference):
    weights = 1 / frame.groupby(
        ["game_id", "player_id", "market"]
    ).research_line.transform("size")
    normalizer = weights.groupby([frame.season, frame.week]).transform("mean")
    return difference * weights / normalizer


def reports(predictions, folds):
    metrics = []
    selections = []
    weekly = []
    reliability = []
    cohorts = []
    methods = REFERENCES + NEW
    for (season, market), g in predictions.groupby(["season", "market"]):
        base = np.clip(g.champion_normal, EPS, 1 - EPS)
        y = g.observed_over
        base_loss = -(y * np.log(base) + (1 - y) * np.log1p(-base))
        for method in methods:
            p = np.clip(g[method], EPS, 1 - EPS)
            loss = -(y * np.log(p) + (1 - y) * np.log1p(-p))
            row = {
                "season": int(season),
                "market": market,
                "method": method,
                **loss_metrics(g, method),
                **paired_weeks(g, unit_balanced_difference(g, base_loss - loss)),
            }
            metrics.append(row)
            for position, h in g.groupby("position"):
                cohorts.append(
                    {
                        "season": int(season),
                        "market": market,
                        "position": position,
                        "method": method,
                        **loss_metrics(h, method),
                    }
                )
            for band, b in g.groupby(
                pd.cut(p, np.linspace(0, 1, 11), include_lowest=True), observed=True
            ):
                reliability.append(
                    {
                        "season": int(season),
                        "market": market,
                        "method": method,
                        "band": str(band),
                        "n": len(b),
                        "predicted": float(b[method].mean()),
                        "observed": float(b.observed_over.mean()),
                    }
                )
    # Global equal-market weekly log-loss test, not a search for isolated favourable markets.
    macro = []
    for season, g in predictions.groupby("season"):
        y = g.observed_over
        for method in NEW:
            losses = []
            for (week, market), h in g.groupby(["week", "market"]):
                b = np.clip(h.champion_normal, EPS, 1 - EPS)
                p = np.clip(h[method], EPS, 1 - EPS)
                z = h.observed_over
                losses.append(
                    {
                        "season": season,
                        "week": week,
                        "delta": float(
                            unit_balanced_difference(
                                h,
                                -(z * np.log(b) + (1 - z) * np.log1p(-b))
                                + (z * np.log(p) + (1 - z) * np.log1p(-p)),
                            ).mean()
                        ),
                    }
                )
            weekly_macro = (
                pd.DataFrame(losses)
                .groupby(["season", "week"], as_index=False)
                .delta.mean()
            )
            method_rows = [
                r for r in metrics if r["season"] == season and r["method"] == method
            ]
            base_rows = [
                r
                for r in metrics
                if r["season"] == season and r["method"] == "champion_normal"
            ]
            macro_loss = float(np.mean([r["log_loss"] for r in method_rows]))
            base_loss = float(np.mean([r["log_loss"] for r in base_rows]))
            macro.append(
                {
                    "season": int(season),
                    "method": method,
                    "macro_log_loss": macro_loss,
                    "macro_brier": float(np.mean([r["brier"] for r in method_rows])),
                    "macro_log_loss_gain": 1 - macro_loss / base_loss,
                    "mean_weekly_log_loss_advantage": float(weekly_macro.delta.mean()),
                    **paired_weeks(weekly_macro, weekly_macro.delta),
                }
            )
    for season in predictions.season.unique():
        holm([r for r in macro if r["season"] == season])
        holm([r for r in metrics if r["season"] == season and r["method"] in NEW])
    for season, g in predictions.groupby("season"):
        info = {f["market"]: f for f in folds if f["test_year"] == season}
        for method in methods:
            # Fold policies are chosen before this test year, per market. Fixed-count is separate.
            allowed = []
            for market, h in g.groupby("market"):
                cutoff = info[market]["selection_cutoffs"][method]
                if cutoff is not None:
                    p = np.maximum(h[method], 1 - h[method])
                    allowed.append(h[p >= cutoff])
            qualified = pd.concat(allowed) if allowed else g.iloc[:0]
            for mode in ["slate", "game"]:
                for kind, pool in [("fixed_count", g), ("prior_qualified", qualified)]:
                    selected = (
                        select_rows(pool, method, mode) if len(pool) else pool.copy()
                    )
                    if len(selected):
                        ws = selected.groupby(["season", "week"]).hit.mean()
                        summary = {
                            "selections": len(selected),
                            "weeks_with_selections": len(ws),
                            "hit_rate": float(selected.hit.mean()),
                            "weekly_mean_hit": float(ws.mean()),
                            "weekly_q25_hit": float(ws.quantile(0.25)),
                            "weekly_min_hit": float(ws.min()),
                            "weekly_std_hit": float(ws.std(ddof=0)),
                            "mean_predicted_hit": float(selected.probability.mean()),
                            "games_covered": selected.game_id.nunique(),
                        }
                        for (s, w), h in selected.groupby(["season", "week"]):
                            weekly.append(
                                {
                                    "season": int(s),
                                    "week": int(w),
                                    "method": method,
                                    "mode": mode,
                                    "kind": kind,
                                    "n": len(h),
                                    "hit_rate": float(h.hit.mean()),
                                    "mean_probability": float(h.probability.mean()),
                                    "lower_threshold_fraction": float(
                                        h.threshold_level.eq(0).mean()
                                    ),
                                }
                            )
                    else:
                        summary = {
                            "selections": 0,
                            "weeks_with_selections": 0,
                            "hit_rate": None,
                            "games_covered": 0,
                        }
                    selections.append(
                        {
                            "season": int(season),
                            "method": method,
                            "mode": mode,
                            "kind": kind,
                            "total_weeks": int(g.week.nunique()),
                            **summary,
                            "scope": "statistical thresholds, conditional participation; no bookmaker prices or betting performance",
                        }
                    )
    return metrics, macro, selections, weekly, reliability, cohorts


def current_reference_comparison(predictions, metrics, selections, weekly):
    """Secondary analysis against the stronger existing research reference, never selection."""
    probability, selection = [], []
    for season, g in predictions.groupby("season"):
        for method in NEW:
            differences = []
            for (week, market), h in g.groupby(["week", "market"]):
                y = h.observed_over
                b = np.clip(h.existing_research, EPS, 1 - EPS)
                p = np.clip(h[method], EPS, 1 - EPS)
                delta = (
                    -(y * np.log(b) + (1 - y) * np.log1p(-b))
                    + y * np.log(p)
                    + (1 - y) * np.log1p(-p)
                )
                differences.append(
                    {
                        "season": season,
                        "week": week,
                        "delta": float(unit_balanced_difference(h, delta).mean()),
                    }
                )
            blocks = (
                pd.DataFrame(differences)
                .groupby(["season", "week"], as_index=False)
                .delta.mean()
            )
            rows = [
                r for r in metrics if r["season"] == season and r["method"] == method
            ]
            base = [
                r
                for r in metrics
                if r["season"] == season and r["method"] == "existing_research"
            ]
            probability.append(
                {
                    "season": int(season),
                    "method": method,
                    "reference": "existing_research",
                    "analysis": "secondary_not_model_selection",
                    "macro_log_loss_gain": 1
                    - np.mean([r["log_loss"] for r in rows])
                    / np.mean([r["log_loss"] for r in base]),
                    **paired_weeks(blocks, blocks.delta),
                }
            )
            for mode in ["slate", "game"]:
                subset = [
                    r
                    for r in selections
                    if r["season"] == season
                    and r["kind"] == "fixed_count"
                    and r["mode"] == mode
                ]
                a = next(r for r in subset if r["method"] == method)
                b = next(r for r in subset if r["method"] == "existing_research")
                w = pd.DataFrame(
                    [
                        r
                        for r in weekly
                        if r["season"] == season
                        and r["kind"] == "fixed_count"
                        and r["mode"] == mode
                    ]
                )
                paired = w[w.method.eq(method)].merge(
                    w[w.method.eq("existing_research")],
                    on=["season", "week"],
                    suffixes=("", "_base"),
                    validate="one_to_one",
                )
                selection.append(
                    {
                        "season": int(season),
                        "method": method,
                        "mode": mode,
                        "reference": "existing_research",
                        "equal_counts": bool(
                            a["selections"] == b["selections"]
                            and paired.n.eq(paired.n_base).all()
                        ),
                        "hit_rate_gain": a["hit_rate"] - b["hit_rate"],
                        **paired_weeks(paired, paired.hit_rate - paired.hit_rate_base),
                    }
                )
        holm([r for r in probability if r["season"] == season])
    return probability, selection


def evidence_gates(metrics, macro, selections, weekly, policy):
    rows = []
    gates = policy["evidence_gates"]
    for global_row in macro:
        season, method = global_row["season"], global_row["method"]
        base = [
            r
            for r in metrics
            if r["season"] == season and r["method"] == "champion_normal"
        ]
        candidate = [
            r for r in metrics if r["season"] == season and r["method"] == method
        ]
        lookup = {r["market"]: r for r in base}
        probability_ok = bool(
            global_row["macro_log_loss_gain"] >= gates["macro_log_loss_gain_min"]
            and global_row["macro_brier"] <= np.mean([r["brier"] for r in base])
            and global_row.get("holm_p", 1.0) <= gates["familywise_alpha"]
            and global_row["low95"] is not None
            and global_row["low95"] > 0
            and all(
                r["log_loss"] <= 1.02 * lookup[r["market"]]["log_loss"]
                for r in candidate
            )
        )
        for mode in ["slate", "game"]:
            a = next(
                r
                for r in selections
                if r["season"] == season
                and r["method"] == method
                and r["mode"] == mode
                and r["kind"] == "fixed_count"
            )
            b = next(
                r
                for r in selections
                if r["season"] == season
                and r["method"] == "champion_normal"
                and r["mode"] == mode
                and r["kind"] == "fixed_count"
            )
            wa = pd.DataFrame(
                [
                    r
                    for r in weekly
                    if r["season"] == season
                    and r["method"] == method
                    and r["mode"] == mode
                    and r["kind"] == "fixed_count"
                ]
            )
            wb = pd.DataFrame(
                [
                    r
                    for r in weekly
                    if r["season"] == season
                    and r["method"] == "champion_normal"
                    and r["mode"] == mode
                    and r["kind"] == "fixed_count"
                ]
            )
            pair = wa.merge(
                wb, on=["season", "week"], validate="one_to_one", suffixes=("", "_base")
            )
            uncertainty = paired_weeks(pair, pair.hit_rate - pair.hit_rate_base)
            fair = bool(
                a["selections"] == b["selections"] and pair.n.eq(pair.n_base).all()
            )
            gain = float(a["hit_rate"] - b["hit_rate"])
            selection_ok = bool(
                fair
                and gain >= gates["fixed_count_hit_rate_gain_min"]
                and a["weekly_q25_hit"] >= b["weekly_q25_hit"]
                and uncertainty["low95"] is not None
                and uncertainty["low95"] > 0
            )
            rows.append(
                {
                    "season": season,
                    "method": method,
                    "mode": mode,
                    "probability_screen": probability_ok,
                    "selection_screen": selection_ok,
                    "equal_counts": fair,
                    "hit_rate_gain": gain,
                    "selection_low95": uncertainty["low95"],
                    "selection_high95": uncertainty["high95"],
                    "passes_registered_research_screen": probability_ok
                    and selection_ok,
                    "commercially_approved": False,
                    "reason": "Statistical thresholds and inspected periods; no offered prices or validated ticket probability",
                }
            )
    return rows


def run(output, cache):
    policy = json.loads(PROTOCOL.read_text())
    d, inputs = input_data()
    import importlib.metadata

    runtime = {
        "python": platform.python_version(),
        "packages": {
            n: importlib.metadata.version(n)
            for n in ["numpy", "pandas", "scikit-learn", "pyarrow", "scipy"]
        },
    }
    from selection_learning.engine import digest

    inputs.update(
        {
            n: sha(ROOT / n)
            for n in [
                "performance_research/threshold_models.py",
                "performance_research/threshold_benchmark.py",
                "performance_research/threshold_protocol.json",
                "performance_research/study.py",
            ]
        }
    )
    frozen_path = (
        ROOT
        / "research_selection_releases/enhanced-sunday-20261121-v1/forecasts.parquet"
    )
    frozen_manifest = json.loads((frozen_path.parent / "manifest.json").read_text())
    expected = frozen_manifest["files"]["forecasts.parquet"]
    expected = expected["sha256"] if isinstance(expected, dict) else expected
    if sha(frozen_path) != expected:
        raise ValueError("Existing research reference integrity failed")
    inputs["existing_research_policy_sha256"] = sha(frozen_path)
    for name in [
        "season_intelligence/probability.py",
        "stage1b/data.py",
        "weekly_learning/store.py",
        "selection_learning/engine.py",
    ]:
        inputs[name] = sha(ROOT / name)
    identity = digest({"inputs": inputs, "runtime": runtime})[:24]
    store = Store(output)
    target = store.root / "studies" / identity
    if target.exists():
        store.validate(target)
        return target
    frozen_path = (
        ROOT
        / "research_selection_releases/enhanced-sunday-20261121-v1/forecasts.parquet"
    )
    frozen = pd.read_parquet(
        frozen_path,
        columns=["market", "point_admitted", "point_family", "probability_mode"],
    )
    current = {
        m: {
            "point": g.iloc[0].point_family if g.iloc[0].point_admitted else "baseline",
            "mode": g.iloc[0].probability_mode,
        }
        for m, g in frozen.groupby("market")
    }
    import inspect

    fit_functions = [
        input_data,
        split_fold,
        empirical_reference,
        select_rows,
        policy_cutoff,
        validated_members,
        fit_market,
    ]
    fit_identity = digest(
        {
            "data": {
                k: v
                for k, v in inputs.items()
                if k
                not in [
                    "performance_research/threshold_benchmark.py",
                    "performance_research/study.py",
                ]
            },
            "functions": {f.__name__: inspect.getsource(f) for f in fit_functions},
            "runtime": runtime,
        }
    )[:24]
    checkpoint = Path(cache) / fit_identity
    checkpoint.mkdir(parents=True, exist_ok=True)
    all_test = []
    all_validation = []
    folds = []
    for year in policy["test_seasons"]:
        for market, g in d.groupby("market", sort=True):
            folder = checkpoint / f"{year}-{market}"
            if folder.exists():
                manifest = json.loads((folder / "hashes.json").read_text())
                if any(sha(folder / name) != v for name, v in manifest.items()):
                    raise ValueError("Checkpoint integrity failed")
                test = pd.read_parquet(folder / "test.parquet")
                val = pd.read_parquet(folder / "validation.parquet")
                meta = json.loads((folder / "fold.json").read_text())
            else:
                print(f"fit {year} {market}", flush=True)
                test, val, meta = fit_market(g, year, policy, current[market])
                folder.mkdir()
                test.to_parquet(folder / "test.parquet", index=False)
                val.to_parquet(folder / "validation.parquet", index=False)
                (folder / "fold.json").write_text(
                    json.dumps(meta, allow_nan=False, indent=2)
                )
                (folder / "hashes.json").write_text(
                    json.dumps(
                        {
                            name: sha(folder / name)
                            for name in [
                                "test.parquet",
                                "validation.parquet",
                                "fold.json",
                            ]
                        }
                    )
                )
            all_test.append(test)
            all_validation.append(val)
            folds.append(meta)
    test = pd.concat(all_test, ignore_index=True)
    val = pd.concat(all_validation, ignore_index=True)
    metrics, macro, selections, weekly, reliability, cohorts = reports(test, folds)
    screens = evidence_gates(metrics, macro, selections, weekly, policy)
    current_probability, current_selection = current_reference_comparison(
        test, metrics, selections, weekly
    )
    summary = {
        "version": policy["version"],
        "model_fit_identity": fit_identity,
        "all_passes_are_research_only": True,
        "identity": identity,
        "runtime": runtime,
        "inputs": inputs,
        "original_rows": len(d),
        "test_player_markets": test[["game_id", "player_id", "market", "season"]]
        .drop_duplicates()
        .shape[0],
        "threshold_observations": len(test),
        "promotion": "RETAIN_CHAMPION",
        "statistical_thresholds_only": True,
        "genuine_bookmaker_lines": 0,
        "ROI": None,
        "accumulator_success": None,
        "scope": "2025 and 2026w1-10 previously inspected chronological diagnostics; not independent final validation",
        "limitations": [
            "Confirmed participation/stat-observation cohort; not complete pregame offered market universe",
            "Champion references retain inherited unverified market publication vintages; new models exclude those values as inputs",
            "Weekly states reconstructed from lag availability, not genuine archived quotes",
            "No ticket probability, offered odds or betting-profit claims",
        ],
    }
    with store.transaction():
        return store.publish(
            "studies",
            identity,
            frames={
                "test_predictions.parquet": test,
                "validation_predictions.parquet": val,
                "probability_metrics.parquet": pd.DataFrame(metrics),
                "macro_tests.parquet": pd.DataFrame(macro),
                "evidence_gates.parquet": pd.DataFrame(screens),
                "current_reference_comparison.parquet": pd.DataFrame(
                    current_probability
                ),
                "current_selection_comparison.parquet": pd.DataFrame(current_selection),
                "selection_metrics.parquet": pd.DataFrame(selections),
                "weekly_selection_metrics.parquet": pd.DataFrame(weekly),
                "reliability.parquet": pd.DataFrame(reliability),
                "position_metrics.parquet": pd.DataFrame(cohorts),
            },
            documents={
                "summary.json": summary,
                "folds.json": folds,
                "protocol.json": policy,
            },
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="weekly_learning_state/threshold_benchmark")
    parser.add_argument("--cache", default="/tmp/nfl-threshold-checkpoints")
    args = parser.parse_args()
    print(run(args.output, args.cache))
