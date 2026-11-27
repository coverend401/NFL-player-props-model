"""One bounded chronological experiment and immutable Sunday research overlay."""

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from script_adjustment.metrics import point
from stage1b.data import MARKETS
from weekly_learning.store import ROOT, encoded, sha

from .data import (
    KEYS,
    champion_baselines,
    load_panel,
    market_data,
    reconciled_source,
)
from .models import PointModel
from .probability import HurdleEmpirical, normal_price

PROTOCOL = ROOT / "season_intelligence/protocol.json"
DEFAULT = ROOT / "experiments/season_intelligence/sunday-20261121-v1"
PARENT = ROOT / "experiments/script_adjustment/numerical-20261121-v5"
FAMILIES = json.loads(PROTOCOL.read_text())["families"]


def paired(d, a, b, seed=221126):
    g = (
        d.assign(diff=np.abs(d[a] - d.y) - np.abs(d[b] - d.y))
        .groupby("week")["diff"]
        .mean()
        .to_numpy()
    )
    # Weeks, not individual player observations, are the resampling units.
    blocks = np.array([g[i : i + 2].mean() for i in range(0, len(g), 2)])
    rng = np.random.default_rng(seed)
    draws = rng.choice(blocks, (1000, len(blocks)), replace=True).mean(axis=1)
    return {
        "low95": float(np.quantile(draws, 0.025)),
        "high95": float(np.quantile(draws, 0.975)),
        "p": float((1 + (draws <= 0).sum()) / 1001),
        "weeks": len(g),
    }


def holm(rows):
    ordered = sorted(rows, key=lambda x: x["p"])
    previous = 0
    for i, r in enumerate(ordered):
        previous = max(previous, min(1, r["p"] * (len(rows) - i)))
        r["holm_p"] = previous


def forecast_folds(panel, baseline, work):
    frames = []
    models = {}
    for market, (target, positions, _, _) in MARKETS.items():
        cache = work / (market + ".joblib")
        if cache.exists():
            obj = joblib.load(cache)
            if obj["protocol_hash"] != sha(PROTOCOL):
                raise ValueError("Stale model cache")
            frames.append(obj["predictions"])
            models.update(obj["models"])
            continue
        d = market_data(panel[panel.position.isin(positions)], market)
        d["available_at"] = pd.concat(
            [
                pd.to_datetime(d.completed_at, utc=True),
                d.kickoff_at + pd.Timedelta(hours=36),
            ],
            axis=1,
        ).max(axis=1)
        valid = (
            d.offense_pct.gt(0)
            & d.stats_observed.eq(True)
            & d[target].notna()
            & d.history_n.ge(3)
        )
        own = []
        fitted = {}
        for year in [2022, 2023, 2024, 2025, 2026]:
            base = baseline[(baseline.market == market) & (baseline.season == year)]
            if base.empty:
                continue
            e = base[
                ["game_id", "player_id", "market", "baseline", "champion_sigma", "y"]
            ].merge(d, on=KEYS, validate="one_to_one")
            if len(e) != len(base):
                raise ValueError("Eligible evaluation population changed")
            fit = d[
                valid & d.season.lt(year) & d.available_at.lt(e.prediction_at.min())
            ]
            if len(fit) < 100:
                raise ValueError("Insufficient earlier training")
            for family in FAMILIES:
                m = PointModel(market, family).fit(fit)
                e[family] = m.predict(e)
                fitted[(market, year, family)] = m
            e["model_fit_before"] = fit.available_at.max().isoformat()
            keep = list(
                dict.fromkeys(
                    [
                        "game_id",
                        "player_id",
                        "player_display_name",
                        "market",
                        "team",
                        "opponent_team",
                        "position",
                        "season",
                        "week",
                        "prediction_at",
                        "kickoff_at",
                        "available_at",
                        "history_available_at",
                        "model_fit_before",
                        "baseline",
                        "champion_sigma",
                        "y",
                    ]
                    + [
                        c
                        for family in FAMILIES
                        for c in PointModel(market, family).columns
                    ]
                    + FAMILIES
                )
            )
            own.append(e[keep])
        predictions = pd.concat(own, ignore_index=True)
        joblib.dump(
            {
                "protocol_hash": sha(PROTOCOL),
                "predictions": predictions,
                "models": fitted,
            },
            cache,
        )
        frames.append(predictions)
        models.update(fitted)
        print("POINT", market, len(predictions), flush=True)
    return pd.concat(frames, ignore_index=True), models


def point_reports(frame):
    rows = []
    for (market, year), g in frame.groupby(["market", "season"]):
        for family in ["baseline"] + FAMILIES:
            rows.append(
                {
                    "market": market,
                    "season": int(year),
                    "method": family,
                    **point(g.y, g[family]),
                }
            )
    metrics = pd.DataFrame(rows)
    trials = []
    for market, g in frame[frame.season.eq(2025)].groupby("market"):
        baseline = point(g.y, g.baseline)["mae"]
        for family in FAMILIES:
            trials.append(
                {
                    "market": market,
                    "family": family,
                    "gain": 1 - point(g.y, g[family])["mae"] / baseline,
                    **paired(g, "baseline", family),
                }
            )
    holm(trials)
    choices = {}
    for market in MARKETS:
        r = max([r for r in trials if r["market"] == market], key=lambda r: r["gain"])
        r = dict(r)
        r["retrospective_point_gate"] = bool(
            r["gain"] >= 0.02 and r["low95"] > 0 and r["holm_p"] <= 0.05
        )
        r["research_point_method"] = (
            r["family"] if r["retrospective_point_gate"] else "baseline"
        )
        r["certified_or_promoted"] = False
        choices[market] = r
    return metrics, pd.DataFrame(trials), choices


def probability_rows(frame, choices, work):
    rows = []
    laws = {}
    for market in MARKETS:
        path = work / ("prob-" + market + ".joblib")
        if path.exists():
            obj = joblib.load(path)
            if obj["choices"] != choices[market]:
                raise ValueError("Distribution cache choice mismatch")
            rows.extend(obj["rows"])
            laws.update(obj["laws"])
            continue
        market_rows = []
        market_laws = {}
        for year in [2025, 2026]:
            g = frame[(frame.market == market) & (frame.season == year)]
            prior = frame[(frame.market == market) & (frame.season < year)]
            method = choices[market]["research_point_method"]
            law = HurdleEmpirical().fit(prior[method], prior.y, prior.position)
            # Matched baseline points isolate probability-law effects.
            base_law = HurdleEmpirical().fit(prior.baseline, prior.y, prior.position)
            market_laws[(market, year)] = law
            count = MARKETS[market][3]
            for r in g.itertuples():
                for name, mu, dist in [
                    ("champion_normal", r.baseline, None),
                    ("baseline_empirical", r.baseline, base_law),
                    ("research_empirical", getattr(r, method), law),
                ]:
                    values, w = (
                        (None, None)
                        if dist is None
                        else dist.samples(mu, r.position, count)
                    )
                    cumulative = None if w is None else np.cumsum(w)
                    lo = (
                        mu - 1.6448536269514722 * r.champion_sigma
                        if dist is None
                        else values[
                            min(np.searchsorted(cumulative, 0.05), len(values) - 1)
                        ]
                    )
                    hi = (
                        mu + 1.6448536269514722 * r.champion_sigma
                        if dist is None
                        else values[
                            min(np.searchsorted(cumulative, 0.95), len(values) - 1)
                        ]
                    )
                    for offset in [-0.5, 0, 0.5]:
                        line = float(
                            np.floor(r.baseline + offset * r.champion_sigma) + 0.5
                        )
                        p = (
                            normal_price(mu, r.champion_sigma, line)["over"]
                            if dist is None
                            else float(w[values > line].sum())
                        )
                        p = float(np.clip(p, 1e-6, 1 - 1e-6))
                        y = float(r.y > line)
                        market_rows.append(
                            {
                                "game_id": r.game_id,
                                "player_id": r.player_id,
                                "position": r.position,
                                "market": market,
                                "season": year,
                                "week": r.week,
                                "method": name,
                                "offset": offset,
                                "hypothetical_line": line,
                                "p_over": p,
                                "observed_over": y,
                                "brier": (p - y) ** 2,
                                "log_loss": -y * np.log(p) - (1 - y) * np.log1p(-p),
                                "covered90": bool(lo <= r.y <= hi),
                                "width90": float(hi - lo),
                                "interval_score90": float(
                                    hi
                                    - lo
                                    + 20 * max(lo - r.y, 0)
                                    + 20 * max(r.y - hi, 0)
                                ),
                            }
                        )
        joblib.dump(
            {"choices": choices[market], "rows": market_rows, "laws": market_laws}, path
        )
        rows.extend(market_rows)
        laws.update(market_laws)
        print("PROB", market, len(market_rows), flush=True)
    return pd.DataFrame(rows), laws


def probability_reports(rows, choices):
    fields = ["brier", "log_loss", "covered90", "width90", "interval_score90"]
    metrics = rows.groupby(["market", "season", "method"], as_index=False).agg(
        **{c: (c, "mean") for c in fields}, line_observations=("brier", "size")
    )
    bands = rows.assign(
        band=pd.cut(rows.p_over, np.linspace(0, 1, 11), include_lowest=True).astype(str)
    )
    reliability = bands.groupby(
        ["market", "season", "method", "band"], as_index=False
    ).agg(
        predicted=("p_over", "mean"),
        observed=("observed_over", "mean"),
        n=("p_over", "size"),
    )
    cohorts = rows.groupby(
        ["market", "season", "method", "position"], as_index=False
    ).agg(
        brier=("brier", "mean"),
        log_loss=("log_loss", "mean"),
        line_observations=("brier", "size"),
    )
    sides = []
    for side in ["over", "under"]:
        c = rows.copy()
        c["side"] = side
        c["probability"] = c.p_over if side == "over" else 1 - c.p_over
        c["observed"] = c.observed_over if side == "over" else 1 - c.observed_over
        c["band"] = pd.cut(
            c.probability, np.linspace(0, 1, 11), include_lowest=True
        ).astype(str)
        sides.append(
            c.groupby(
                ["market", "season", "method", "side", "band"], as_index=False
            ).agg(
                predicted=("probability", "mean"),
                observed=("observed", "mean"),
                n=("probability", "size"),
            )
        )
    for market in MARKETS:
        v = metrics[(metrics.market == market) & metrics.season.eq(2025)].set_index(
            "method"
        )
        c = choices[market]
        c["probability_log_loss_gain"] = float(
            1
            - v.loc["research_empirical", "log_loss"]
            / v.loc["champion_normal", "log_loss"]
        )
        c["retrospective_probability_gate"] = bool(
            c["probability_log_loss_gain"] >= 0.02
            and v.loc["research_empirical", "brier"]
            <= v.loc["champion_normal", "brier"]
        )
        c["selected_research_probability"] = (
            "research_empirical"
            if c["retrospective_probability_gate"]
            else "champion_normal"
        )
    return metrics, reliability, cohorts, pd.concat(sides, ignore_index=True)


def feature_diagnostics(frame, models):
    rows = []
    rng = np.random.default_rng(221126)
    for market, g in frame[frame.season.eq(2026)].groupby("market"):
        model = models[(market, 2026, "opponent_ridge")]
        base = np.mean(abs(model.predict(g) - g.y))
        target, _, opp, _ = MARKETS[market]
        groups = {
            "production_and_workload": [
                c
                for c in model.columns
                if c.startswith(target + "_") or c in [opp + "_last3", opp + "_last5"]
            ],
            "shares_and_snaps": [
                c
                for c in model.columns
                if "share" in c or "snap" in c or c.startswith("offense_pct")
            ],
            "efficiency": [c for c in model.columns if c.startswith("efficiency")],
            "opponent": [c for c in model.columns if c.startswith("opp_")],
            "team_pace_and_volume": [c for c in model.columns if c.startswith("own_")],
            "home_rest_continuity": [
                c
                for c in model.columns
                if c in ["is_home", "days_rest", "known_team_continuity"]
            ],
        }
        for family, cols in groups.items():
            if not cols:
                continue
            d = g.copy()
            for ix in d.groupby(["week", "position"]).groups.values():
                shuffled = rng.permutation(ix)
                d.loc[ix, cols] = g.loc[shuffled, cols].to_numpy()
            perm = np.mean(abs(model.predict(d) - g.y))
            rows.append(
                {
                    "market": market,
                    "season": 2026,
                    "family": family,
                    "n": len(g),
                    "permuted_mae_minus_original": float(perm - base),
                    "scope": "inspected diagnostic; correlated features and artificial combinations limit causal interpretation",
                }
            )
    return pd.DataFrame(rows)


def run(output=DEFAULT, work=Path("/tmp/season-intelligence-v1")):
    output = Path(output)
    work = Path(work)
    if output.exists():
        raise ValueError("Immutable experiment already exists")
    work.mkdir(parents=True, exist_ok=True)
    from .data import CERTIFIED

    input_token = (
        sha(PROTOCOL)
        + sha(ROOT / "season_intelligence/data.py")
        + sha(ROOT / "season_intelligence/models.py")
        + sha(CERTIFIED / "features.parquet")
    )
    marker = work / "input-token.txt"
    if marker.exists() and marker.read_text() != input_token:
        raise ValueError("Experiment cache source changed; use a new work directory")
    marker.write_text(input_token)
    if (work / "prepared_panel.parquet").exists():
        panel = pd.read_parquet(work / "prepared_panel.parquet")
        baseline = pd.read_parquet(work / "prepared_baseline.parquet")
        source_audit = json.loads((work / "source-audit.json").read_text())
        source = CERTIFIED / "features.parquet"
    else:
        source, panel = load_panel()
        raw, source_audit = reconciled_source()
        baseline = champion_baselines(raw)
        panel.to_parquet(work / "prepared_panel.parquet", index=False)
        baseline.to_parquet(work / "prepared_baseline.parquet", index=False)
        (work / "source-audit.json").write_text(encoded(source_audit))
    print("DATA", len(panel), len(baseline), source_audit, flush=True)
    frame, models = forecast_folds(panel, baseline, work)
    pointmetrics, trials, choices = point_reports(frame)
    prows, laws = probability_rows(frame, choices, work)
    pm, rel, cohort, sides = probability_reports(prows, choices)
    diagnostics = feature_diagnostics(frame, models)
    output.mkdir(parents=True)
    import shutil

    if (work / "cache-equivalence.json").exists():
        shutil.copyfile(
            work / "cache-equivalence.json", output / "cache_equivalence.json"
        )
    frame.to_parquet(output / "historical_predictions.parquet", index=False)
    pointmetrics.to_csv(output / "point_metrics.csv", index=False)
    trials.to_csv(output / "point_selection_trials.csv", index=False)
    prows.to_parquet(output / "probability_predictions.parquet", index=False)
    pm.to_csv(output / "probability_metrics.csv", index=False)
    rel.to_csv(output / "reliability.csv", index=False)
    cohort.to_csv(output / "position_probability_metrics.csv", index=False)
    sides.to_csv(output / "side_reliability.csv", index=False)
    diagnostics.to_csv(output / "feature_diagnostics.csv", index=False)
    (output / "selection.json").write_text(encoded(choices))
    joblib.dump(
        {
            "models": models,
            "laws": laws,
        },
        output / "research_models.joblib",
    )
    from .sunday import build

    sunday, shortlist, top2 = build(panel, models, laws, choices, output)
    from release_utils import runtime_versions

    report = {
        "runtime": runtime_versions(ROOT),
        "status": "experimental_not_promoted",
        "activation": False,
        "final_period_accessed": False,
        "protocol_sha256": sha(PROTOCOL),
        "preregistration_commit": "4670fab",
        "player_source": str(source.relative_to(ROOT)),
        "player_source_sha256": sha(source),
        "created_at": datetime.now(UTC).isoformat(),
        "source_reconciliation": source_audit,
        "sample": {
            "player_market_observations": len(frame),
            "2026_observations": int(frame.season.eq(2026).sum()),
            "zero_outcomes": int(frame.y.eq(0).sum()),
            "games": int(frame.game_id.nunique()),
        },
        "sunday": {
            "forecasts": len(sunday),
            "shortlist": len(shortlist),
            "top2": len(top2),
            "fixtures": int(sunday.game_id.nunique()),
            "certified": False,
            "original_release_changed": False,
        },
        "limitations": [
            "2025 and2026w1-10 are already inspected, not independent holdouts",
            "Historical roster publication and source revision vintages unverified; no invented inactives or routes",
            "Zero mass is conditional on established participation; no assumed DNP probability",
            "Probability scoring uses hypothetical half-lines, not historical bookmaker returns",
            "Sunday roster evidence is inherited from certified20November snapshot, not live injury news",
        ],
        "files": {},
        "source_sha256": {
            str(p.relative_to(ROOT)): sha(p)
            for p in (ROOT / "season_intelligence").glob("*.py")
        },
    }
    report["files"] = {
        str(p.relative_to(output)): sha(p) for p in output.rglob("*") if p.is_file()
    }
    (output / "manifest.json").write_text(encoded(report))
    print(
        encoded(
            {
                "output": str(output),
                "sample": report["sample"],
                "sunday": report["sunday"],
            }
        ),
        flush=True,
    )
    return output


if __name__ == "__main__":
    run()
