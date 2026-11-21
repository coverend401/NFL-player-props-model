"""Bounded individual-variable/interaction diagnostics; never fit or choose methods."""

import json

import joblib
import numpy as np
import pandas as pd

from season_intelligence.experiment import DEFAULT
from season_intelligence.validate import validate
from stage1b.data import MARKETS
from weekly_learning.store import ROOT, encoded, sha


def shuffled(frame, columns, seed):
    rng = np.random.default_rng(seed)
    d = frame.copy()
    for ix in frame.groupby(["week", "position"]).groups.values():
        draw = rng.permutation(ix)
        d.loc[ix, columns] = frame.loc[draw, columns].to_numpy()
    return d


def main():
    validate(DEFAULT)
    frame = pd.read_parquet(DEFAULT / "historical_predictions.parquet")
    models = joblib.load(DEFAULT / "research_models.joblib")["models"]
    choices = json.loads((DEFAULT / "selection.json").read_text())
    rows = []
    interaction = []
    weekly = []
    cohorts = []
    for (market, year), g in frame[frame.season.isin([2025, 2026])].groupby(
        ["market", "season"]
    ):
        g = g.reset_index(drop=True)
        model = models[(market, int(year), "opponent_ridge")]
        base = model.predict(g)
        error = np.mean(abs(base - g.y))
        for col in model.columns:
            changes = []
            for seed in [221126, 221127, 221128]:
                candidate = model.predict(shuffled(g, [col], seed))
                changes.append(float(np.mean(abs(candidate - g.y)) - error))
            rows.append(
                {
                    "market": market,
                    "season": int(year),
                    "feature": col,
                    "n": len(g),
                    "mean_permuted_mae_increase": float(np.mean(changes)),
                    "permutation_std_3_draws": float(np.std(changes)),
                    "scope": "controlled ridge, within-week/position; inspected diagnostic, correlation-sensitive; not causal",
                }
            )
        tree = models[(market, int(year), "context_tree")]
        original = tree.predict(g)
        groups = {
            "production": [
                c
                for c in tree.columns
                if any(t in c for t in ["_last3", "_last5", "_career", "_season"])
                and "share" not in c
                and not c.startswith("offense_pct")
            ],
            "role": [
                c
                for c in tree.columns
                if "share" in c or "snap" in c or c.startswith("offense_pct")
            ],
            "opponent": [c for c in tree.columns if c.startswith("opp_")],
            "team": [c for c in tree.columns if c.startswith("own_")],
        }
        for left, right in [
            ("production", "role"),
            ("production", "opponent"),
            ("production", "team"),
        ]:
            a, b = groups[left], groups[right]
            if not a or not b:
                continue
            both = list(dict.fromkeys(a + b))
            contrasts = []
            losses = []
            for seed in [221126, 221127, 221128]:
                pa = tree.predict(shuffled(g, a, seed))
                pb = tree.predict(shuffled(g, b, seed))
                pab = tree.predict(shuffled(g, both, seed))
                contrasts.append(float(np.mean(abs(pab - pa - pb + original))))
                losses.append(
                    float(np.mean(abs(pab - g.y)) - np.mean(abs(original - g.y)))
                )
            interaction.append(
                {
                    "market": market,
                    "season": int(year),
                    "groups": left + " + " + right,
                    "n": len(g),
                    "mean_absolute_nonadditive_response": float(np.mean(contrasts)),
                    "joint_permutation_mae_increase": float(np.mean(losses)),
                    "scope": "nonlinear tree response, not proof of causal interaction or incremental OOS benefit",
                }
            )
        method = choices[market]["research_point_method"]
        for week, h in g.groupby("week"):
            for name, col in [("baseline", "baseline"), ("research", method)]:
                e = h[col] - h.y
                weekly.append(
                    {
                        "market": market,
                        "season": int(year),
                        "week": int(week),
                        "method": name,
                        "n": len(h),
                        "mae": float(e.abs().mean()),
                        "rmse": float(np.sqrt((e**2).mean())),
                        "bias": float(e.mean()),
                    }
                )
        opp = MARKETS[market][2]
        band = pd.cut(
            g[opp + "_last3"],
            [-np.inf, 5, 15, np.inf],
            right=False,
            labels=["under5", "5to15", "15plus"],
        )
        for value in ["under5", "5to15", "15plus"]:
            h = g[band.eq(value)]
            if h.empty:
                continue
            cohorts.append(
                {
                    "market": market,
                    "season": int(year),
                    "workload_band": value,
                    "n": len(h),
                    "baseline_mae": float(abs(h.baseline - h.y).mean()),
                    "research_mae": float(abs(h[method] - h.y).mean()),
                }
            )
    path = ROOT / "docs"
    outputs = {
        "enhanced-individual-variable-diagnostics.csv": pd.DataFrame(rows),
        "enhanced-interaction-diagnostics.csv": pd.DataFrame(interaction),
        "enhanced-weekly-errors.csv": pd.DataFrame(weekly),
        "enhanced-workload-cohorts.csv": pd.DataFrame(cohorts),
    }
    for name, data in outputs.items():
        data.to_csv(path / name, index=False)
    stable = pd.DataFrame(rows).pivot(
        index=["market", "feature"],
        columns="season",
        values="mean_permuted_mae_increase",
    )
    stable["positive_both_inspected_years"] = stable[2025].gt(0) & stable[2026].gt(0)
    stable.to_csv(path / "enhanced-variable-stability.csv")
    m = {
        "experiment_manifest_sha256": sha(DEFAULT / "manifest.json"),
        "script_sha256": sha(ROOT / "scripts/diagnose_enhanced_variables.py"),
        "no_fitting": True,
        "no_method_selection": True,
        "final_period_accessed": False,
        "files": {
            name: sha(path / name)
            for name in list(outputs) + ["enhanced-variable-stability.csv"]
        },
    }
    (path / "enhanced-variable-provenance.json").write_text(encoded(m))
    print(
        encoded(
            {
                "individual_rows": len(rows),
                "interaction_rows": len(interaction),
                "no_refit": True,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
