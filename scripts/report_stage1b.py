"""Regenerate the human/machine Stage 1B report from validated research artifacts."""

from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stage1b.artifacts import validate, validate_results
from stage1b.metrics import week_block_interval


def table(headers, rows):
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def report(path):
    path = Path(path)
    manifest = validate(path, ROOT)
    audit = validate_results(path)
    protocol = json.loads((path / "protocol.json").read_text())
    m = pd.read_csv(path / "probability_metrics.csv")
    a = pd.read_csv(path / "accuracy.csv")
    d = pd.read_csv(path / "paired_differences.csv")
    r = pd.read_csv(path / "reliability.csv")
    f = pd.read_parquet(path / "forecasts.parquet")
    p = pd.read_parquet(path / "probes.parquet")
    dev = m[m.evaluation_tier.eq("development_oos") & m.season.astype(str).eq("all")]
    aggregate = {}
    for tier in ["development_oos", "monitoring"]:
        g = m[m.evaluation_tier.eq(tier) & m.season.astype(str).eq("all")]
        aggregate[tier] = {
            v: {
                "n": int(h.n.sum()),
                "brier": float(np.average(h.brier, weights=h.n)),
                "log_loss": float(np.average(h.log_loss, weights=h.n)),
                "equal_market_brier": float(h.brier.mean()),
                "equal_market_log_loss": float(h.log_loss.mean()),
            }
            for v, h in g.groupby("version")
        }
    rows = []
    for market, g in dev.groupby("market"):
        baseline = g[g.version.eq("stage1a_normal_rule")].iloc[0]
        selected = g[g.version.eq("selected_stage1b")].iloc[0]
        delta = d[d.market.eq(market) & d.evaluation_tier.eq("development_oos")].iloc[0]
        rows.append(
            [
                market,
                f"{int(selected.n):,}",
                f"{baseline.brier:.5f}",
                f"{selected.brier:.5f}",
                f"{delta.delta_brier:+.5f}",
                f"[{delta.delta_brier_low:+.5f}, {delta.delta_brier_high:+.5f}]",
                f"{baseline.log_loss:.5f}",
                f"{selected.log_loss:.5f}",
            ]
        )
    point = a[a.season.eq("all_development") & a.cohort.eq("all")]
    pointrows = [
        [
            x.market,
            f"{x.mae:.3f}",
            f"{x.naive_mae:.3f}",
            f"{x.rmse:.3f}",
            f"{x.bias:+.3f}",
            f"{100 * x.interval90_coverage:.1f}%",
            f"{x.interval90_width:.2f}",
        ]
        for x in point.itertuples()
    ]
    calrows = []
    for market, g in r[r.evaluation_tier.eq("development_oos")].groupby("market"):
        ece = {
            v: float(
                np.average((h.observed - h.mean_probability).abs(), weights=h.n_probes)
            )
            for v, h in g.groupby("version")
        }
        calrows.append(
            [
                market,
                f"{100 * ece['stage1a_normal_rule']:.2f}%",
                f"{100 * ece['selected_stage1b']:.2f}%",
            ]
        )
    probability = (
        p[p.evaluation_tier.eq("development_oos")]
        .groupby(["version", "row_id", "season", "week"], as_index=False)
        .brier.mean()
    )
    baseline = probability[probability.version.eq("stage1a_normal_rule")].drop(
        columns="version"
    )
    selected = probability[probability.version.eq("selected_stage1b")].drop(
        columns="version"
    )
    joined = baseline.merge(
        selected,
        on=["row_id", "season", "week"],
        suffixes=("_baseline", "_selected"),
        validate="one_to_one",
    )
    joined["delta"] = joined.brier_selected - joined.brier_baseline
    interval = week_block_interval(
        joined,
        "delta",
        reps=protocol["bootstrap_replicates"],
        block=protocol["bootstrap_week_block"],
    )
    baseline = aggregate["development_oos"]["stage1a_normal_rule"]
    selected = aggregate["development_oos"]["selected_stage1b"]
    brier_gain = 100 * (baseline["brier"] - selected["brier"]) / baseline["brier"]
    ll_gain = 100 * (baseline["log_loss"] - selected["log_loss"]) / baseline["log_loss"]
    zeros = int(f[f.evaluation_tier.eq("development_oos")].y.eq(0).sum())
    strata = (
        p[p.evaluation_tier.eq("development_oos")]
        .groupby(["probe_multiplier", "version"])[["brier", "log_loss"]]
        .mean()
        .reset_index()
    )
    probe_rows = []
    for multiplier, g in strata.groupby("probe_multiplier"):
        b = g[g.version.eq("stage1a_normal_rule")].iloc[0]
        q = g[g.version.eq("selected_stage1b")].iloc[0]
        probe_rows.append(
            [
                str(multiplier),
                f"{b.brier:.6f}",
                f"{q.brier:.6f}",
                f"{b.log_loss:.6f}",
                f"{q.log_loss:.6f}",
            ]
        )
    summary = {
        "experiment": manifest["experiment_id"],
        "source_commit": manifest["source_commit"],
        "audit": audit,
        "aggregate": aggregate,
        "development_probe_strata": strata.to_dict("records"),
        "paired_development_brier_delta_95_block_interval": interval,
        "development_zero_outcomes_retained": zeros,
        "per_market_differences": d.to_dict("records"),
        "final_period_sealed": True,
        "final_period_start": protocol["final_start"],
        "genuine_historical_quote_count": 0,
        "genuine_bet_count": 0,
        "realised_profit": None,
        "production_replacement_recommended": False,
        "comparison_warning": "Common safe-feature point engine; legacy normal probability rule only, not historical production pickles or bookmaker prices.",
    }
    (ROOT / "docs/stage1b-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    text = (
        f"""# Stage 1B measured results — research, not a production replacement

Experiment **`{manifest["experiment_id"]}`**, scientific source commit
`{manifest["source_commit"]}`. Python {manifest["runtime"]["python"]}, Arrow 24.0.0.
All payload/source/input hashes and semantic time guards passed. The archive has
**45 independently loadable market-season bundles**, **{audit["player_market_games"]:,}
scored player-market games** and **{audit["hypothetical_probes"]:,} paired probes**.
No production models, data, secrets, ledger or bankroll settings were changed.

## What the comparison means

The comparator reproduces Stage 1A's continuous-normal probability rule and
in-sample residual scale on the SAME pregame-safe point engine and games. It is
not the historical production model: current production pickles contain later
outcomes, and historical closing-context capture times are unavailable. Both
probability versions share point forecasts, so their point-MAE difference is zero
by construction. The separate career-mean benchmark diagnoses point forecast skill.

2022–2025 are **development OOS**, not an untouched final test. They contain
**{baseline["n"]:,} player-market games**, including **{zeros:,} observed zero
outcomes**. 2026 weeks 1–10 contribute **{aggregate["monitoring"]["selected_stage1b"]["n"]:,}**
monitoring rows, reported separately. All 2026 week-11+ final outcomes remain sealed.

Thresholds are three preregistered pregame historical-mean half-line probes, not
bookmaker lines. Their outcomes are genuine NFL observations; their thresholds
are hypothetical. No price, profit, realised win rate or betting ROI is inferred.

## Probability performance, development OOS

Player-market-weighted Brier: **{baseline["brier"]:.6f} → {selected["brier"]:.6f}**
({brier_gain:.2f}% lower). Log loss: **{baseline["log_loss"]:.6f} → {selected["log_loss"]:.6f}**
({ll_gain:.2f}% lower). Paired Brier delta 95% week-block interval:
**[{interval[0]:+.6f}, {interval[1]:+.6f}]**. These conditional exploratory intervals
hold fitted models/selection fixed, do not cover arbitrary long player dependence,
and are not adjusted for multiple-market research. Receiving markets dominate the
player-market weighting; equal-market means are in the machine summary.

"""
        + table(
            [
                "Market",
                "Games",
                "Normal Brier",
                "Selected Brier",
                "Delta",
                "95% block interval",
                "Normal log loss",
                "Selected log loss",
            ],
            rows,
        )
        + """

Seven markets have lower Brier point estimates; six have paired Brier intervals
below zero. QB rushing attempts has an interval crossing zero. Completions is a
clear regression in these development data; passing attempts is also worse on
point estimates, with an inconclusive Brier interval. No method was reselected on
these evaluation results. Retain these failures in every model review.

## Hypothetical threshold sensitivity

"""
        + table(
            [
                "Career-mean multiplier",
                "Normal Brier",
                "Selected Brier",
                "Normal log loss",
                "Selected log loss",
            ],
            probe_rows,
        )
        + """

These are the three preregistered threshold families. Even the centre (1.0x)
probe is not an authentic offered line. Improvements on easier tail probes cannot
be presented as evidence of value at bookmaker thresholds.

## Point accuracy and interval sharpness

"""
        + table(
            [
                "Market",
                "MAE",
                "Career-mean MAE",
                "RMSE",
                "Bias",
                "90% coverage",
                "90% mean width",
            ],
            pointrows,
        )
        + """

Signed bias is prediction minus outcome; units are each market's yards/counts.
Passing-yards point accuracy is worse than the naive career mean in this replay.
Completions intervals under-cover; several yardage intervals are very wide and
substantially over-cover. High coverage achieved by broad intervals is not good
sharpness or proof of calibrated tails. The probability CDF and point estimator
are separate fitted objects; a displayed point forecast is not asserted to equal
the mean of every candidate CDF. Do not promote the full family automatically.

## Calibration evidence

Fixed ten-band expected absolute calibration error (descriptive, sample-dependent):

"""
        + table(["Market", "Normal-rule ECE", "Selected ECE"], calrows)
        + """

ECE is not a proper score and can improve while log loss worsens, as completions
demonstrates. Use Brier/log loss, band gaps, sample sizes and interval sharpness
together. Probability-band tables include dependent-week block intervals and
calibration-gap intervals; sparse bands can have no interval. Wilson bands are
secondary descriptive summaries, not individual-probability confidence intervals.

## Authentic betting results and risk

**Authentic historical prop quotes: 0. Genuine historical strategy bets: 0.
Realised profit/ROI: unavailable.** The repository contains no authenticated price
archive. Unit-test prices and profits are synthetic fixtures and excluded from
all experiment reports. Provider historical-event APIs exist, but access/licence,
NFL-market coverage, exact price availability and historical rules need review.

The implemented backtest requires hash-bound original provider responses,
reviewed extractions, archived rules available before decision, explicit timezone
and availability timing, exact-line as-of forecasts and observed action/outcomes.
It accounts for pushes, verified voids, vig through actual quoted odds, reserved
concurrent stakes and an initial bankroll in drawdown. Historical replay timestamps
represent information cutoffs; models were built now, not published in the past.
Even with authentic quotes, returns would be counterfactual strategy results, not
actual placed-bet P/L. Unsupported rules or missing observations stop the backtest.

Fair odds/EV are push-aware. Fractional Kelly and fixed-stake utilities are
experimental; default staking remains zero without separate validation. Model
disagreement is not a statistical probability confidence interval.

## Remaining limitations and decisions

1. Historical stat revisions and missing publication/roster archives prevent a fully
   authenticated point-in-time population replay. Scores condition on observable
   participation and complete history; absent games/players cannot be invented.
2. The source's kickoff+8h availability is a proxy. No historical injury or closing
   market information is used as a known pregame feature in this baseline.
3. Annual refitting is the registered walk-forward design. Weekly model updates
   require new cross-fitted residual/calibration validation, not reuse of this
   mapping under new point models.
4. Completion/attempt regressions, thin QB selection periods, empirical/quantile
   tails and nonstationary role changes need further research. Do not tune using
   final-period outcomes to repair them.
5. Collect prospective raw source/roster/quote/rule snapshots before final-period
   decisions. The capture utility stamps the actual pregame clock and stores no
   outcomes. Final evaluation requires separate approval; no unseal flag exists.
6. Stage 1C must use the frozen protocol, same row IDs/population and proper-score
   comparisons, with timestamped matchup/personnel inputs and paired uncertainty.

## Review and dashboard

Run `streamlit run stage1b_dashboard.py` in the pinned environment to inspect
accuracy/cohorts, coverage, probability bands, versions, uncertainty, genuine-odds
status and provenance. This is a standalone proposal, not the production app.
See [audit/research](STAGE1B_AUDIT_RESEARCH.md) and [protocol/runbook](STAGE1B_PROTOCOL.md).
No Stage 1B merge or deployment is authorised by these results.
"""
    )
    (ROOT / "docs/STAGE1B_RESULTS.md").write_text(text)
    print(
        json.dumps(
            {
                "experiment": manifest["experiment_id"],
                "development": aggregate["development_oos"],
                "brier_relative_reduction_pct": brier_gain,
                "log_loss_relative_reduction_pct": ll_gain,
                "paired_brier_interval": interval,
            }
        )
    )


if __name__ == "__main__":
    report(
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "experiments/stage1b/baseline-20261113-v5"
    )
