"""Produce a review report from the immutable Stage 1B.1 experiment, no refitting."""

import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stage1b1.artifacts import validate_results, validate
from stage1b.metrics import week_block_interval


def table(headers, rows):
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        + ["| " + " | ".join(map(str, r)) + " |" for r in rows]
    )


def report(path):
    path = Path(path)
    manifest = validate(path, ROOT)
    audit = validate_results(path, ROOT)
    a = pd.read_csv(path / "accuracy.csv")
    scores = pd.read_csv(path / "probability_metrics.csv")
    f = pd.read_parquet(path / "forecasts.parquet")
    q = pd.read_parquet(path / "probes.parquet")
    fold = json.loads((path / "folds.json").read_text())
    paired = pd.read_csv(path / "paired_probability_differences.csv")
    old = ROOT / manifest["baseline_path"]
    dev = a[(a.evaluation_tier == "development_oos") & (a.season == "all")]
    ds = scores[
        (scores.evaluation_tier == "development_oos") & (scores.season == "all")
    ]
    pointrows = []
    intervalrows = []
    probrows = []
    for market, g in dev.groupby("market"):
        b = g[g.version == "stage1b"].iloc[0]
        n = g[g.version == "stage1b1"].iloc[0]
        pointrows.append(
            [
                market,
                int(n.n),
                f"{b.mae:.3f}",
                f"{n.mae:.3f}",
                f"{n.naive_mae:.3f}",
                f"{n.rmse:.3f}",
                f"{n.bias:+.3f}",
            ]
        )
        intervalrows.append(
            [
                market,
                f"{100 * b.coverage90:.2f}% → {100 * n.coverage90:.2f}%",
                f"{b.width90:.2f} → {n.width90:.2f}",
                f"{b.interval_score90:.2f} → {n.interval_score90:.2f}",
            ]
        )
    for market, g in ds.groupby("market"):
        b = g[g.version == "stage1b"].iloc[0]
        n = g[g.version == "stage1b1"].iloc[0]
        r = paired[
            (paired.market == market) & (paired.evaluation_tier == "development_oos")
        ].iloc[0]
        probrows.append(
            [
                market,
                f"{b.brier:.6f} → {n.brier:.6f}",
                f"{b.log_loss:.6f} → {n.log_loss:.6f}",
                f"[{r.delta_brier_low:+.6f}, {r.delta_brier_high:+.6f}]",
            ]
        )
    point = f[(f.market == "passing_yards") & (f.season < 2026)].copy()
    point["delta"] = abs(point.projection - point.y) - abs(point.naive - point.y)
    naive_delta = {
        "delta": float(point.delta.mean()),
        "interval": list(week_block_interval(point, "delta")),
    }
    aggregates = {}
    for tier, g in scores[scores.season == "all"].groupby("evaluation_tier"):
        aggregates[tier] = {
            v: {
                "brier": float(np.average(z.brier, weights=z.n)),
                "log_loss": float(np.average(z.log_loss, weights=z.n)),
                "n": int(z.n.sum()),
            }
            for v, z in g.groupby("version")
        }
    # Log-loss paired intervals are supplementary to the runner's Brier intervals.
    grouped = q.groupby(
        ["row_id", "market", "version", "evaluation_tier", "season", "week"],
        as_index=False,
    )[["brier", "log_loss"]].mean()
    left = grouped[grouped.version == "stage1b"].drop(columns="version")
    right = grouped[grouped.version == "stage1b1"].drop(columns="version")
    pairs = left.merge(
        right,
        on=["row_id", "market", "evaluation_tier", "season", "week"],
        suffixes=("_old", "_new"),
        validate="one_to_one",
    )
    logloss_rows = []
    for (market, tier), g in pairs.groupby(["market", "evaluation_tier"]):
        g = g.copy()
        g["delta"] = g.log_loss_new - g.log_loss_old
        low, high = week_block_interval(g, "delta")
        logloss_rows.append(
            dict(
                market=market,
                evaluation_tier=tier,
                delta=float(g.delta.mean()),
                low=low,
                high=high,
            )
        )
    pd.DataFrame(logloss_rows).to_csv(
        ROOT / "docs/stage1b1-logloss-intervals.csv", index=False
    )
    threshold = q.groupby(
        ["market", "evaluation_tier", "version", "probe_multiplier"], as_index=False
    ).agg(
        n_probes=("event", "size"),
        brier=("brier", "mean"),
        log_loss=("log_loss", "mean"),
    )
    threshold.to_csv(ROOT / "docs/stage1b1-threshold-sensitivity.csv", index=False)
    cohorts = []
    for (market, tier), d in f.groupby(["market", "evaluation_tier"]):
        for name, mask in [
            ("returning", d.returning),
            ("nonreturning", ~d.returning),
            ("history3to7", d.games_played_prior < 8),
            ("history8plus", d.games_played_prior >= 8),
            ("zero_outcome_descriptive", d.y.eq(0)),
        ]:
            g = d[mask]
            if g.empty:
                continue
            for v, col in [
                ("stage1b", "stage1b_projection"),
                ("stage1b1", "projection"),
            ]:
                cohorts.append(
                    dict(
                        market=market,
                        evaluation_tier=tier,
                        cohort=name,
                        version=v,
                        n=len(g),
                        mae=float(abs(g[col] - g.y).mean()),
                        bias=float((g[col] - g.y).mean()),
                    )
                )
    pd.DataFrame(cohorts).to_csv(ROOT / "docs/stage1b1-cohorts.csv", index=False)
    # Tail failures are observations, not an attribution experiment.
    tails = []
    for (market, version), g in q[q.season < 2026].groupby(["market", "version"]):
        bad = ((g.probability < 0.001) & g.event.eq(1)) | (
            (g.probability > 0.999) & g.event.eq(0)
        )
        tails.append(
            dict(
                market=market,
                version=version,
                n_wrong_extreme=int(bad.sum()),
                n_probes=len(g),
                logloss_share=float(g.loc[bad, "log_loss"].sum() / g.log_loss.sum()),
            )
        )
    selections = []
    for b in fold:
        oldb = joblib.load(old / "models" / f"{b['market']}-{b['season']}.joblib")
        selections.append(
            dict(
                market=b["market"],
                season=b["season"],
                old_kind=oldb["selected_kind"],
                old_calibration=getattr(
                    oldb["selected_calibration"], "method", "identity"
                ),
                new_point=b["point_method"],
                new_probability=b["probability_method"],
                new_interval=b["interval_method"],
            )
        )
    summary = {
        "experiment_id": manifest["experiment_id"],
        "source_commit": manifest["source_commit"],
        "manifest_sha256": __import__("hashlib")
        .sha256((path / "manifest.json").read_bytes())
        .hexdigest(),
        "audit": audit,
        "coverage": f.groupby("evaluation_tier")
        .agg(n=("y", "size"), zeros=("y", lambda x: int(x.eq(0).sum())))
        .reset_index()
        .to_dict("records"),
        "aggregates": aggregates,
        "passing_yards_vs_naive": naive_delta,
        "tail_diagnostics": tails,
        "selections": selections,
        "genuine_quotes": 0,
        "betting_profit": None,
        "provider_selected": False,
        "production_release": "stage1a-20261113-py314-arrow24-r2",
        "final_period_sealed": True,
    }
    (ROOT / "docs/stage1b1-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    cal = pd.read_csv(path / "reliability.csv")
    calrows = []
    for market, g in cal[cal.evaluation_tier == "development_oos"].groupby("market"):
        values = {
            v: float(
                np.average(abs(z.observed - z.mean_probability), weights=z.n_probes)
            )
            for v, z in g.groupby("version")
        }
        calrows.append(
            [
                market,
                f"{100 * values['stage1b']:.2f}%",
                f"{100 * values['stage1b1']:.2f}%",
            ]
        )
    years = a[(a.market == "passing_yards") & (a.season != "all")]
    yearrows = []
    for year, g in years.groupby("season"):
        b = g[g.version == "stage1b"].iloc[0]
        n = g[g.version == "stage1b1"].iloc[0]
        yearrows.append(
            [
                year,
                int(n.n),
                f"{b.mae:.3f}",
                f"{n.mae:.3f}",
                f"{n.naive_mae:.3f}",
                f"{100 * n.coverage90:.2f}%",
            ]
        )
    text = (
        f"""# Stage 1B.1 results and review

Immutable experiment: `{manifest["experiment_id"]}`. Scientific source commit:
`{manifest["source_commit"]}`. This is a research comparison, not a production
release or approval for live betting. Stage 1B was merged as `15a4028`; Stage 1A
release `stage1a-20261113-py314-arrow24-r2` remains active and unmodified.
No dashboard has been hosted or modified by Stage 1B.1.

## Population, validation and final holdout

45 annual market/year bundles; **49,034 development player-market games (2022–25,
6,709 observed zero outcomes)** and **6,269 monitoring games (2026 weeks 1–10,
903 zero outcomes)**. All row IDs, outcomes and old point/probability comparators
match the frozen benchmark exactly. There are 331,818 paired half-line probes,
with the three dependent thresholds averaged per player-game for inference.
No missing/zero-outcome substitution or selective removal of hard games occurred.

The final **2026 week 11 onward remains sealed**, including all future seasons.
No final outcomes were materialised. These previously inspected development and
monitoring seasons are NOT untouched final tests for this follow-up. The original
retrospective-data/participation limits still apply. All fitted/selection labels
precede outer decisions. Chronological phases are documented in
[the protocol](STAGE1B1_PROTOCOL.md). No methods were changed after this full run.

## Point accuracy

"""
        + table(
            [
                "Market",
                "N dev",
                "Stage 1B MAE",
                "1B.1 MAE",
                "Naive MAE",
                "1B.1 RMSE",
                "1B.1 bias",
            ],
            pointrows,
        )
        + f"""

Passing yards: MAE **73.068 → 68.140** (6.74% lower), versus career mean **69.922**
(2.55% lower). Paired week-block difference against Stage 1B is −4.928 yards,
95% exploratory band **[−10.845, −0.689]**; against naive −1.782,
**[{naive_delta["interval"][0]:.3f}, {naive_delta["interval"][1]:.3f}]**.
RMSE 92.328 → 86.338, but signed bias worsens −0.644 → **+7.195 yards**.
The aggregate gain is heavily influenced by repairing the weak 2024 point model.
It is not uniform across seasons or proof of future superiority:

"""
        + table(
            [
                "Season",
                "N",
                "Stage 1B MAE",
                "1B.1 MAE",
                "Naive MAE",
                "1B.1 interval coverage",
            ],
            yearrows,
        )
        + """

2023 and 2025 MAE regress against Stage 1B. In 2026 monitoring, MAE
**66.994 → 67.119** is a small regression, although below naive 70.317.
2025 coverage is only 86.38%, 2026 87.89%. Do not hide these failures behind the
pooled average. Eight other point models remain exactly unchanged. Cohort
comparisons (returning, nonreturning, short/long prior history and descriptive zero
outcomes) are saved in `stage1b1-cohorts.csv`; groups overlap and are not selection
criteria. Returning means a prior participation gap >21 days, including offseason;
it does not establish an injury return. Per-season metrics are in the immutable archive.

## Probability scores and investigation of previous regressions

Lower Brier and log loss are better. Bands below are paired week-block Brier
differences (1B.1 minus 1B), conditional on fitted fold decisions, not independent
observations or multiplicity-adjusted significance claims.

"""
        + table(
            [
                "Market",
                "Brier: 1B → 1B.1",
                "Log loss: 1B → 1B.1",
                "95% Brier delta band",
            ],
            probrows,
        )
        + """

Completions improves both scores; its paired Brier band excludes zero. Passing
attempts and passing yards improve the pooled point estimates, but their Brier
bands include zero. Six other markets' probability arrays are exactly unchanged.
The changed passing-yard point engine contributes to its probability comparison;
this is not an isolated calibration attribution study. Across all markets weighted
Brier/log-loss aggregates are in `stage1b1-summary.json`; the small QB population
means aggregates can obscure those markets.

The normal reference is now eligible. Bounded empirical/quantile tails, flexible
calibration on small QB samples, and a four-week method-selection bootstrap were
credible failure mechanisms. New disjoint windows, positive-slope shrinkage and an
explicit tail anchor address them together; this experiment is **not an ablation**
proving their separate causal contributions. In development completions, 17 of
6,864 old probes were wrong with >99.9% confidence (11.26% of old total log loss);
new probes have zero such cases at these three thresholds. Tail probability
accuracy elsewhere is still unproven. Passing attempts has 2 such old cases,
passing yards 9; the new versions have none. Selection details and old/new
families are recorded in the machine summary/fold archive. Completion NB thinning
was researched and evaluated as a candidate, not forced into the selected result.

Relative to the ORIGINAL Stage 1B normal-rule comparator, development completions
Brier is 0.132333 vs 0.132735 and log loss 0.408868 vs 0.409734; these small gains
do not prove superiority. Passing-attempt Brier remains slightly worse (0.130842
vs 0.130604), despite log loss 0.401765 vs 0.402175. The regression is reduced,
not universally resolved against every benchmark. Original comparator uses the
same point model for attempts/completions and is not a historical production replay.

Supplementary paired log-loss bands are in `stage1b1-logloss-intervals.csv`.
Threshold-level scores are in `stage1b1-threshold-sensitivity.csv`; they are
hypothetical half-lines, NEVER observed book lines. In 2026 monitoring,
completions Brier 0.138116 → 0.136226; attempts 0.132051 → 0.127978; yards
0.143001 → 0.140612. These small, already viewed samples are not final evidence.

## Reliability

Fixed ten-band weighted absolute calibration gaps (descriptive ECE):

"""
        + table(["Market", "Stage 1B", "1B.1"], calrows)
        + """

Completions ECE worsens 2.25% → 2.31%, and attempts 2.71% → 3.18%, despite
better proper scores. Calibration has not improved uniformly. Do not describe the
entire probability family as demonstrably calibrated.

Full reliability bands, player-game/probe counts and dependent-week gap intervals
are in `reliability.csv`. ECE is not a proper score or an individual probability
confidence bound. Sparse bands and threshold transfer remain concerns.

## Interval sharpness and calibration

Nominal 90%; widths in market units; lower interval score is better:

"""
        + table(
            ["Market", "Coverage: 1B → 1B.1", "Mean width", "Mean interval score"],
            intervalrows,
        )
        + """

Yardage intervals are substantially narrower with pooled coverage closer to 90%.
Passing-yard width falls 39.77%, receiving-yard width 72.06%. Completions widens
to repair prior undercoverage. Receptions, RB attempts and QB attempts score worse
and/or widen; **do not promote the interval family indiscriminately**. The prior
selection rule is frozen and those outer regressions are retained. Independent
CQR sets need not equal selected pricing-CDF quantiles. Temporal role changes
invalidate any unqualified exchangeable conformal coverage guarantee. Per-season
and 2026 undercoverage remain important, particularly the QB markets.

## Authentic bookmaker evidence and operational blockers

**Genuine quotes: 0. Genuine historical bets: 0. Realised profit/ROI: unavailable.**
The owner confirmed no provider yet. A tested manual collector now preserves raw
future-event quote bytes, actual capture/quote/kickoff times, decimal odds, lines,
requested markets, hashes and raw settlement-rule documents. It refuses failed,
empty, backdated or post-kickoff substitutes and marks all captures unreviewed.
It stores no credential in metadata; no keys, paid requests or jobs are configured.
See [activation requirements](STAGE1B1_ODDS_CAPTURE.md).

Provider/licence/coverage, a privately configured key, approved domain, private
durable archive, capture schedule, event/player crosswalks and reviewed rule/price
availability remain prerequisites. Prepared tooling does **not** mean collection
is operational. Raw observations alone do not prove executable prices or valid
settlement. Existing evidence-bound replay and staking protections remain intact.

## Recommendation and next work

Review/merge Stage 1B.1 only as research infrastructure, with no app/probability
activation or dashboard hosting. Do not ship these experimental probabilities or
intervals to live betting on the strength of development scores.

1. Select/license an odds provider and establish approved private prospective
   quote/rule/model-decision evidence capture before claiming betting value.
2. Freeze the prospective protocol and retain the sealed final period until a
   separately approved, one-time evaluation. Do not retune against its outcomes.
3. Investigate passing-yard positive bias, 2023/2025 reversals and 2026 monitoring
   regression; validate weekly cross-fitted updates and naive baselines prospectively.
4. Investigate count interval regressions/conditional undercoverage, probability–
   interval coherence and joint attempts/completions consistency. Retain per-season
   coverage and proper interval score; assess deeper/longer-block uncertainty.
5. Only then consider a separately reviewed market-by-market production candidate.
   Stage 1C matchup/injury features must preserve authentic timing and the frozen
   baseline. This PR does not begin Stage 1C or alter production risk settings.
"""
    )
    (ROOT / "docs/STAGE1B1_RESULTS.md").write_text(text)
    print(
        json.dumps(
            {
                "experiment": manifest["experiment_id"],
                "aggregate": aggregates,
                "passing_yards_vs_naive": naive_delta,
            }
        )
    )


if __name__ == "__main__":
    report(
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "experiments/stage1b1/improvements-20261113-v1"
    )
