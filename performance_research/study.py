"""Bounded chronological comparison of forecasting and probability challengers."""

import argparse
import itertools
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from stage1b.data import MARKETS
from weekly_learning.store import ROOT, Store, sha

PROTOCOL = Path(__file__).with_name("protocol.json")


def permitted(frame):
    if ((frame.season > 2026) | ((frame.season == 2026) & (frame.week > 10))).any():
        raise ValueError("Sealed final-period rows prohibited in development study")
    return frame


def candidates(frame):
    d = permitted(frame.copy())
    for weight in [0.25, 0.5, 0.75]:
        d[f"frozen_recency_{weight:g}"] = np.nan
        d[f"workload_efficiency_{weight:g}"] = np.nan
    for market, (target, _, opportunity, count) in MARKETS.items():
        mask = d.market.eq(market)
        for weight in [0.25, 0.5, 0.75]:
            # These are archived pregame lags, never the same-game outcome.
            d.loc[mask, f"frozen_recency_{weight:g}"] = (
                weight * d.loc[mask, target + "_last3"]
                + (1 - weight) * d.loc[mask, target + "_career"]
            )
            volume = (
                weight * d.loc[mask, opportunity + "_last3"]
                + (1 - weight) * d.loc[mask, opportunity + "_last5"]
            )
            efficiency = (
                0.25 * d.loc[mask, "efficiency3"]
                + 0.75 * d.loc[mask, "efficiency_career"]
            )
            value = volume if target == opportunity else volume * efficiency
            d.loc[mask, f"workload_efficiency_{weight:g}"] = (
                value.clip(lower=0) if count else value
            )
    methods = [
        "baseline",
        "recent_shrunk",
        "player_ridge",
        "role_ridge",
        "opponent_ridge",
        "context_tree",
        *[
            f"{family}_{w:g}"
            for family in ["frozen_recency", "workload_efficiency"]
            for w in [0.25, 0.5, 0.75]
        ],
    ]
    for method in methods:
        d[method + "_missing_input_fallback"] = ~np.isfinite(d[method])
        d[method] = d[method].where(np.isfinite(d[method]), d.baseline)
    return d, methods


def paired_weeks(frame, difference, *, seed=241126):
    weekly = (
        frame.assign(delta=difference)
        .groupby(["season", "week"])
        .delta.mean()
        .to_numpy()
    )
    blocks = np.array([weekly[i : i + 2].mean() for i in range(0, len(weekly), 2)])
    if len(blocks) < 2:
        return {"weeks": len(weekly), "low95": None, "high95": None, "p": 1.0}
    rng = np.random.default_rng(seed)
    draws = rng.choice(blocks, (1000, len(blocks)), replace=True).mean(axis=1)
    if len(blocks) <= 12:
        signs = np.asarray(list(itertools.product([-1.0, 1.0], repeat=len(blocks))))
    else:
        signs = rng.choice([-1.0, 1.0], (4096, len(blocks)))
    null = (signs * blocks).mean(axis=1)
    exceedances = (null >= blocks.mean() - 1e-12).sum()
    p = (
        exceedances / len(null)
        if len(blocks) <= 12
        else (1 + exceedances) / (1 + len(null))
    )
    return {
        "weeks": len(weekly),
        "low95": float(np.quantile(draws, 0.025)),
        "high95": float(np.quantile(draws, 0.975)),
        "p": float(p),
    }


def holm(records):
    previous = 0.0
    for i, row in enumerate(sorted(records, key=lambda r: r["p"])):
        previous = max(previous, min(1.0, row["p"] * (len(records) - i)))
        row["holm_p"] = previous


def point_metrics(d, column):
    error = d[column] - d.y
    return {
        "n": len(d),
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt((error**2).mean())),
        "bias": float(error.mean()),
        "zero_outcomes": int(d.y.eq(0).sum()),
    }


def point_study(d, current_policy=None):
    d, methods = candidates(d)
    rows, choices = [], {}
    for market, group in d.groupby("market"):
        selection = group[group.season.eq(2025)]
        losses = {m: float((selection[m] - selection.y).abs().mean()) for m in methods}
        best = min(losses, key=losses.get)
        choices[market] = (
            best if losses[best] <= 0.98 * losses["baseline"] else "baseline"
        )
        for season, g in group.groupby("season"):
            if season < 2025:
                continue
            for m in methods:
                row = {
                    "market": market,
                    "season": int(season),
                    "method": m,
                    **point_metrics(g, m),
                    "missing_input_fallback_n": int(
                        g[m + "_missing_input_fallback"].sum()
                    ),
                    **paired_weeks(g, (g.baseline - g.y).abs() - (g[m] - g.y).abs()),
                }
                row["selected_using_2025"] = m == choices[market]
                row["mae_gain"] = 1 - row["mae"] / point_metrics(g, "baseline")["mae"]
                current = (
                    (current_policy or {}).get(market, {}).get("point", "baseline")
                )
                row["current_research_method"] = current
                row["current_research_mae"] = point_metrics(g, current)["mae"]
                row["mae_gain_vs_current_research"] = (
                    1 - row["mae"] / row["current_research_mae"]
                )
                rows.append(row)
    # Include all alternatives in each diagnostic family, not just winning methods.
    for season in [2025, 2026]:
        holm([r for r in rows if r["season"] == season and r["method"] != "baseline"])
    cohort = []
    unknown = pd.Series(np.nan, index=d.index)
    d["history_band"] = (
        pd.cut(
            d.get("history_n", unknown),
            [-np.inf, 5, 15, np.inf],
            labels=["up_to_5", "6_to_15", "16_plus"],
        )
        .astype(object)
        .fillna("unknown")
    )
    d["playing_time_change"] = (
        pd.cut(
            d.get("role_snap_change", unknown).abs(),
            [-np.inf, 0.1, np.inf],
            labels=["within_10_percentage_points", "larger_change"],
        )
        .astype(object)
        .fillna("unknown")
    )
    for axis in ["position", "history_band", "playing_time_change"]:
        for (market, value, season), g in d[d.season.ge(2025)].groupby(
            ["market", axis, "season"]
        ):
            method = choices[market]
            current = (current_policy or {}).get(market, {}).get("point", "baseline")
            cohort.append(
                {
                    "market": market,
                    "cohort_axis": axis,
                    "cohort": str(value),
                    "season": int(season),
                    "method": method,
                    **point_metrics(g, method),
                    "baseline_mae": point_metrics(g, "baseline")["mae"],
                    "current_research_mae": point_metrics(g, current)["mae"],
                }
            )
    return rows, choices, cohort


def walk_calibrate(frame):
    """Prefix-only monotone recalibration; illustrative lines count as one player-game."""
    d = (
        permitted(frame.copy())
        .sort_values(["season", "week", "game_id", "player_id", "offset"])
        .reset_index(drop=True)
    )
    d["calibrated"] = d.p_over
    d["calibration_training_rows"] = 0
    for (market, method, season, week), test in d.groupby(
        ["market", "method", "season", "week"]
    ):
        cutoff = test.prediction_at.min()
        train = d[d.market.eq(market) & d.method.eq(method) & d.available_at.lt(cutoff)]
        if (
            train[["game_id", "player_id"]].drop_duplicates().shape[0] < 100
            or train[["season", "week"]].drop_duplicates().shape[0] < 6
        ):
            continue
        weights = (
            1
            / train.groupby(["game_id", "player_id"])
            .p_over.transform("size")
            .to_numpy()
        )
        identity = np.linspace(0.05, 0.95, 10)
        model = IsotonicRegression(y_min=1e-6, y_max=1 - 1e-6, out_of_bounds="clip")
        model.fit(
            np.r_[train.p_over, identity],
            np.r_[train.observed_over, identity],
            sample_weight=np.r_[weights, np.full(10, 10.0)],
        )
        d.loc[test.index, "calibrated"] = model.predict(test.p_over)
        d.loc[test.index, "calibration_training_rows"] = len(train)
    return d


def probability_study(probabilities, timing, current_policy=None):
    t = timing[["game_id", "player_id", "market", "prediction_at", "available_at"]]
    d = probabilities.merge(
        t, on=["game_id", "player_id", "market"], validate="many_to_one"
    )
    for col in ["prediction_at", "available_at"]:
        d[col] = pd.to_datetime(d[col], utc=True)
    if not np.isfinite(d.p_over).all() or not d.p_over.between(0, 1).all():
        raise ValueError("Invalid probability source")
    # Fair comparison on positive illustrative lines and identical keys/method coverage.
    d = d[d.hypothetical_line.ge(0.5)].copy()
    keys = ["game_id", "player_id", "market", "season", "week", "offset"]
    if d.duplicated(keys + ["method"]).any():
        raise ValueError("Ambiguous probability observations")
    size = d.groupby(keys).method.nunique()
    if not size.eq(d.method.nunique()).all():
        raise ValueError("Probability methods differ in eligible populations")
    calibrated = walk_calibrate(d)
    base = calibrated.copy()
    alternate = calibrated.copy()
    alternate["method"] += "_shrunk_isotonic"
    alternate["p_over"] = alternate.calibrated
    combined = pd.concat([base, alternate], ignore_index=True)
    p = combined.p_over.clip(1e-9, 1 - 1e-9)
    combined["brier_new"] = (p - combined.observed_over) ** 2
    combined["log_new"] = -(
        combined.observed_over * np.log(p) + (1 - combined.observed_over) * np.log1p(-p)
    )
    rows, choices, reliability = [], {}, []
    for market, g in combined.groupby("market"):
        selection = g[g.season.eq(2025)].groupby("method").log_new.mean()
        best = selection.idxmin()
        choices[market] = (
            best
            if selection[best] <= 0.98 * selection["champion_normal"]
            else "champion_normal"
        )
        for (season, method), h in g.groupby(["season", "method"]):
            benchmark = g[g.season.eq(season) & g.method.eq("champion_normal")][
                keys + ["log_new"]
            ]
            paired = h.merge(
                benchmark, on=keys, validate="one_to_one", suffixes=("", "_baseline")
            )
            rows.append(
                {
                    "market": market,
                    "season": int(season),
                    "method": method,
                    "line_observations": len(h),
                    "player_games": len(h[["game_id", "player_id"]].drop_duplicates()),
                    "brier": float(h.brier_new.mean()),
                    "log_loss": float(h.log_new.mean()),
                    "selected_using_2025": method == choices[market],
                    **paired_weeks(paired, paired.log_new_baseline - paired.log_new),
                }
            )
            current = (current_policy or {}).get(market, {}).get("probability")
            rows[-1]["current_research_method"] = current
            current_rows = (
                g[g.season.eq(season) & g.method.eq(current)]
                if current is not None
                else g.iloc[:0]
            )
            rows[-1]["current_research_log_loss"] = (
                float(current_rows.log_new.mean()) if len(current_rows) else None
            )
            rows[-1]["log_loss_gain_vs_current_research"] = (
                float(1 - h.log_new.mean() / current_rows.log_new.mean())
                if len(current_rows)
                else None
            )
            for band, b in h.groupby(
                pd.cut(h.p_over, np.linspace(0, 1, 11), include_lowest=True),
                observed=True,
            ):
                reliability.append(
                    {
                        "market": market,
                        "season": int(season),
                        "method": method,
                        "band": str(band),
                        "line_observations": len(b),
                        "predicted": float(b.p_over.mean()),
                        "observed": float(b.observed_over.mean()),
                    }
                )
    for season in [2025, 2026]:
        holm(
            [
                r
                for r in rows
                if r["season"] == season and r["method"] != "champion_normal"
            ]
        )
    return rows, choices, reliability


def run(output):
    policy = json.loads(PROTOCOL.read_text())
    source = ROOT / policy["source"]
    inputs = {
        name: sha(source / name)
        for name in [
            "historical_predictions.parquet",
            "probability_predictions.parquet",
            "manifest.json",
        ]
    }
    manifest = json.loads((source / "manifest.json").read_text())
    for name in ["historical_predictions.parquet", "probability_predictions.parquet"]:
        if sha(source / name) != manifest["files"][name]:
            raise ValueError("Frozen comparison source integrity failure")
    policy_path = (
        ROOT
        / "research_selection_releases/enhanced-sunday-20261121-v1/forecasts.parquet"
    )
    policy_manifest = json.loads((policy_path.parent / "manifest.json").read_text())
    expected = policy_manifest["files"]["forecasts.parquet"]
    expected = expected["sha256"] if isinstance(expected, dict) else expected
    if sha(policy_path) != expected:
        raise ValueError("Current research policy artifact integrity failure")
    inputs["current_research_forecasts"] = sha(policy_path)
    frozen = pd.read_parquet(
        policy_path,
        columns=["market", "point_admitted", "point_family", "probability_mode"],
    )
    current_policy = {}
    for market, g in frozen.groupby("market"):
        if len(g.drop_duplicates()) != 1:
            raise ValueError("Ambiguous current market policy")
        r = g.iloc[0]
        current_policy[market] = {
            "point": r.point_family if r.point_admitted else "baseline",
            "probability": "research_empirical"
            if r.probability_mode == "empirical"
            else "champion_normal"
            if r.probability_mode == "original_normal"
            else None,
        }
    import importlib.metadata

    from selection_learning.engine import digest

    runtime = {
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ["numpy", "pandas", "scikit-learn", "pyarrow"]
        },
    }
    inputs.update(
        {
            p: sha(ROOT / p)
            for p in [
                "stage1b/data.py",
                "weekly_learning/store.py",
                "selection_learning/engine.py",
            ]
        }
    )
    identity = digest(
        {
            "protocol": sha(PROTOCOL),
            "code": sha(Path(__file__)),
            "inputs": inputs,
            "runtime": runtime,
        }
    )[:24]
    store = Store(output)
    existing = store.root / "studies" / identity
    if existing.exists():
        store.validate(existing)
        return existing
    filters = [[("season", "<=", 2025)], [("season", "==", 2026), ("week", "<=", 10)]]
    d = permitted(
        pd.read_parquet(source / "historical_predictions.parquet", filters=filters)
    )
    for col in [
        "prediction_at",
        "available_at",
        "history_available_at",
        "model_fit_before",
        "kickoff_at",
    ]:
        d[col] = pd.to_datetime(d[col], utc=True)
    if not (
        (d.history_available_at < d.prediction_at)
        & (d.model_fit_before < d.prediction_at)
        & (d.prediction_at <= d.kickoff_at - pd.Timedelta(minutes=60))
        & (d.available_at > d.prediction_at)
    ).all():
        raise ValueError("Archived chronological feature/training timing failed")
    point, point_choice, cohort = point_study(d, current_policy)
    probabilities = permitted(
        pd.read_parquet(source / "probability_predictions.parquet", filters=filters)
    )
    scores, probability_choice, reliability = probability_study(
        probabilities, d, current_policy
    )
    summary = {
        "version": policy["version"],
        "identity": identity,
        "runtime": runtime,
        "inputs": inputs,
        "protocol_sha256": sha(PROTOCOL),
        "code_sha256": sha(Path(__file__)),
        "historical_rows": len(d),
        "point_choices": point_choice,
        "current_research_policy": current_policy,
        "probability_choices": probability_choice,
        "promotion": "RETAIN_CHAMPION",
        "reason": "Previously inspected periods; authentic quoted selection/ticket performance unavailable; no independent promotion evidence",
        "genuine_quote_backtest": "NOT_AVAILABLE_IN_THIS_STUDY",
        "ticket_backtest": "NOT_AVAILABLE_IN_THIS_STUDY",
        "timing_caveat": "Reconstructed chronology checked; inherited closing-market publication timing and retrospective roster coverage remain unverified",
    }
    with store.transaction():
        return store.publish(
            "studies",
            identity,
            frames={
                "point_metrics.parquet": pd.DataFrame(point),
                "probability_metrics.parquet": pd.DataFrame(scores),
                "reliability.parquet": pd.DataFrame(reliability),
                "cohorts.parquet": pd.DataFrame(cohort),
            },
            documents={"summary.json": summary, "protocol.json": policy},
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", default="weekly_learning_state/performance_research"
    )
    args = parser.parse_args()
    print(run(args.output))
