"""Reproduce descriptive tables from the locked Stage 1C.1 experiment."""

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stage1c1.artifacts import validate  # noqa: E402


def table(d):
    d = d.copy()
    for c in d.select_dtypes(include="number"):
        d[c] = d[c].map(lambda x: f"{x:.4f}" if pd.notna(x) else "—")
    return "\n".join(
        [
            "| " + " | ".join(d.columns) + " |",
            "| " + " | ".join(["---"] * len(d.columns)) + " |",
        ]
        + [
            "| " + " | ".join(map(str, row)) + " |"
            for row in d.itertuples(index=False, name=None)
        ]
    )


def report(directory, output):
    validate(directory, ROOT)
    directory, output = Path(directory), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    f = pd.read_parquet(directory / "forecasts.parquet")
    a = pd.read_csv(directory / "accuracy.csv", dtype={"season": str})
    p = pd.read_csv(directory / "probability_metrics.csv", dtype={"season": str})
    paired = pd.read_csv(directory / "paired_metrics.csv")
    dev = a[(a.evaluation_tier == "development_oos") & a.season.eq("all")]
    scores = p[(p.evaluation_tier == "development_oos") & p.season.eq("all")]
    combined = dev.merge(
        scores,
        on=["market", "version", "evaluation_tier", "season"],
        suffixes=("", "_prob"),
    )
    combined.to_csv(output / "all_markets.csv", index=False)
    a.merge(
        p, on=["market", "version", "evaluation_tier", "season"], suffixes=("", "_prob")
    ).to_csv(output / "all_seasons.csv", index=False)
    sections = [
        "# Stage 1C.1 — controlled research diagnostics",
        "Research only. No production activation, independent final test, bookmaker quotes or betting returns. All 2022–25 results below are chronological out-of-sample predictions on previously inspected development data; 2026 weeks 1–10 remain a separate monitoring tier. Week 11 onward remains sealed. Inputs are retrospective revised snapshots, not verified historical T−60 publication archives.",
        f"Validated experiment `{directory.name}`; {f.row_id.nunique():,} identical eligible player-market games per version; {len(f):,} forecast rows across nine versions. The frozen Stage 1B.1 reference remains byte-identical. All eight new arms use the same fixed Student-t(5)/penalised sigmoid algorithm and inverse-CDF intervals; this wrapper is a diagnostic control, not a selected production replacement.",
        "## Primary comparison and backbone controls",
    ]
    passing = combined[combined.market.eq("passing_yards")]
    sections.append(
        table(
            passing[
                [
                    "version",
                    "n",
                    "mae",
                    "bias",
                    "brier",
                    "log_loss",
                    "coverage90",
                    "width90",
                    "interval_score90",
                ]
            ]
        )
    )
    primary = paired[
        (paired.market == "passing_yards")
        & paired.evaluation_tier.eq("development_oos")
        & paired.cohort.eq("all")
        & paired.variant.eq("b1_context")
        & paired.reference.eq("b1_none")
        & paired.metric.eq("absolute_error")
    ]
    sections.append(
        "Primary paired delta (candidate minus control; negative is better), with 4/8-week block intervals:\n\n"
        + table(primary[["week_block", "n", "delta", "low", "high"]])
    )
    gain = (
        1
        - passing.set_index("version").loc["b1_context", "mae"]
        / passing.set_index("version").loc["b1_none", "mae"]
    )
    clears = bool(gain >= 0.01 and primary.high.lt(0).all())
    sections.append(
        f"Relative passing MAE gain: {100 * gain:.3f}%. Preregistered minimum 1% gain plus both interval upper bounds below zero: **{'cleared statistically; harm gates still apply' if clears else 'NOT cleared'}**. This is not fresh independent confirmation."
    )
    contrasts = paired[
        paired.market.eq("passing_yards")
        & paired.evaluation_tier.eq("development_oos")
        & paired.cohort.eq("all")
        & paired.metric.eq("absolute_error")
        & paired.week_block.eq(4)
    ]
    sections.append(table(contrasts[["variant", "reference", "delta", "low", "high"]]))
    sections.append(
        "`c0_none−b1_none` isolates the point-backbone change; context comparisons within each backbone isolate added context under the common probability wrapper. `b1_context−b1_context_legacy` isolates reconciled positional data; `b1_context−b1_context_fixed` measures model-choice adaptation. The difference-in-differences row is a backbone/context interaction, not an additional independent experiment. `b1_none−frozen_b1` isolates the probability/interval wrapper because point predictions are identical."
    )
    sections.append(
        "## All nine markets: common-wrapper baseline versus combined context"
    )
    view = combined[combined.version.isin(["b1_none", "b1_context"])]
    sections.append(
        table(
            view[
                [
                    "market",
                    "version",
                    "n",
                    "mae",
                    "bias",
                    "brier",
                    "log_loss",
                    "coverage90",
                    "width90",
                    "interval_score90",
                ]
            ]
        )
    )
    sections.append(
        "Full nine-version metrics, RMSE, zero counts and all season-level metrics (including monitoring) are in `all_markets.csv` and `all_seasons.csv`; exhaustive position/history/returning-gap/zero cohorts are in `all_cohorts_seasons.csv`. Probability-band reliability and paired 4/8-week uncertainty remain in the immutable experiment. Three hypothetical pregame half-lines per game are correlated probes, not bookmaker quotes or three independent bets."
    )
    sections.append("## Prespecified RB receiving-yards subgroup")
    rb = f[(f.market == "receiving_yards") & f.position.eq("RB") & f.season.lt(2026)]
    rb_scores = []
    q = pd.read_parquet(directory / "probes.parquet")
    # Descriptive cohorts are reported exhaustively, never used to select a fit.
    per_game = q.groupby(["row_id", "version"])[["brier", "log_loss"]].mean()
    scored = f.join(per_game, on=["row_id", "version"])
    cohort_rows = []
    for (market, version, season), g in scored.groupby(["market", "version", "season"]):
        cohorts = [
            ("all", g),
            ("limited_history", g[g.games_played_prior < 8]),
            ("established", g[g.games_played_prior >= 8]),
            ("returning_gap_21d_not_injury", g[g.returning]),
            ("observed_zero", g[g.y.eq(0)]),
        ]
        cohorts += [("position_" + str(pos), z) for pos, z in g.groupby("position")]
        for cohort, z in cohorts:
            if z.empty:
                continue
            error = z.projection - z.y
            cohort_rows.append(
                dict(
                    market=market,
                    version=version,
                    season=season,
                    cohort=cohort,
                    n=len(z),
                    mae=abs(error).mean(),
                    rmse=(error.pow(2).mean()) ** 0.5,
                    bias=error.mean(),
                    brier=z.brier.mean(),
                    log_loss=z.log_loss.mean(),
                    coverage90=((z.y >= z.lower90) & (z.y <= z.upper90)).mean(),
                    width90=(z.upper90 - z.lower90).mean(),
                    interval_score90=z.interval_score.mean(),
                )
            )
    pd.DataFrame(cohort_rows).to_csv(output / "all_cohorts_seasons.csv", index=False)
    for (version, season), g in rb.groupby(["version", "season"]):
        qq = q[q.version.eq(version) & q.row_id.isin(g.row_id)]
        rb_scores.append(
            dict(
                version=version,
                season=season,
                n=len(g),
                mae=float(abs(g.projection - g.y).mean()),
                bias=float((g.projection - g.y).mean()),
                brier=float(qq.brier.mean()),
                log_loss=float(qq.log_loss.mean()),
                coverage90=float(((g.y >= g.lower90) & (g.y <= g.upper90)).mean()),
                width90=float((g.upper90 - g.lower90).mean()),
            )
        )
    rb_frame = pd.DataFrame(rb_scores)
    rb_frame.to_csv(output / "rb_receiving_seasons.csv", index=False)
    rr = paired[
        paired.market.eq("receiving_yards")
        & paired.evaluation_tier.eq("development_oos")
        & paired.cohort.eq("RB_prespecified")
        & paired.variant.eq("b1_context")
        & paired.reference.eq("b1_none")
    ]
    sections.append(table(rr[["metric", "week_block", "n", "delta", "low", "high"]]))
    sections.append(
        "This subgroup was preregistered after its promise was observed previously. It is not an untouched replication. Fits remain pooled; no segment-specific tuning, weighting or deployment was performed. Season-level subgroup results are supplied without selecting favourable seasons."
    )
    sections.append("## Feature stability, redundancy and effective information")
    perm = pd.read_csv(directory / "inner_permutation.csv")
    pp = perm.groupby(["market", "variant", "block"], as_index=False).agg(
        mean_delta=("delta_mae", "mean"),
        minimum=("delta_mae", "min"),
        maximum=("delta_mae", "max"),
        context_used_fraction=("context_used", "mean"),
    )
    pp.to_csv(output / "inner_sensitivity_summary.csv", index=False)
    fold_sensitivity = perm.groupby(
        ["market", "variant", "season", "block"], as_index=False
    ).agg(mean_delta=("delta_mae", "mean"), used=("context_used", "first"))
    fold_sensitivity.to_csv(output / "inner_sensitivity_by_fold.csv", index=False)
    weights = pd.read_csv(directory / "training_weights.csv")
    context_weights = weights[weights.is_context]
    stability = context_weights.groupby(
        ["market", "variant", "feature"], as_index=False
    ).agg(
        folds=("season", "nunique"),
        available_linear_folds=("coefficient_available", "sum"),
        median_training_std=("training_std", "median"),
        minimum_training_std=("training_std", "min"),
        mean_standardized_coefficient=("standardized_coefficient", "mean"),
        minimum_coefficient=("standardized_coefficient", "min"),
        maximum_coefficient=("standardized_coefficient", "max"),
    )
    stability.to_csv(output / "context_stability.csv", index=False)

    sections.append(table(pp[pp.variant.eq("b1_context")]))
    sections.append(
        "Permutation diagnostics use only the prior year's weeks 11–18, moving whole fixture-side blocks within week and position kind. Positive delta means worse error after permutation, not proof of causality. Correlated features, few independent team games and distribution shift limit interpretation. A career/lag fallback ignores context entirely; zero sensitivity is then structural, not evidence that the feature is intrinsically useless."
    )
    red = pd.read_csv(directory / "training_redundancy.csv")
    sections.append(
        f"{len(red):,} training-only feature-pair records have |correlation| ≥ .95 (repeated across folds/arms, not distinct independent findings). Standardised linear coefficients and feature standard deviations are archived; tree models do not receive invented coefficients."
    )
    ess_rows = []
    for source in ["legacy", "reconciled"]:
        es = pd.read_parquet(directory / f"effective_samples_{source}.parquet")
        es = es[pd.to_datetime(es.prediction_at, utc=True).dt.year.ge(2022)]
        for kind, g in es.groupby("kind"):
            ess_rows.append(
                dict(
                    source=source,
                    kind=kind,
                    median_kish_games=g.kish_game_ess.median(),
                    p10_kish_games=g.kish_game_ess.quantile(0.1),
                    median_weighted_opportunities=g.weighted_opportunities.median(),
                    median_staleness_days=g.days_since_valid.median(),
                )
            )
    ess = pd.DataFrame(ess_rows)
    ess.to_csv(output / "effective_information.csv", index=False)
    sections.append(table(ess))
    sections.append(
        "Kish ESS counts decayed games, not independent plays or players. Better coverage cannot create verified publication timestamps. C2 team-volume inputs are unchanged by positional reconciliation."
    )
    sections.append(
        "## Hindsight-only team-volume / player-share / efficiency error accounting"
    )
    oracle = pd.read_parquet(directory / "oracle_diagnostics.parquet")
    oracle = oracle[oracle.eligible & oracle.season.lt(2026)]
    rows = []
    for market, g in oracle.groupby("market"):
        rows.append(
            dict(
                market=market,
                n=len(g),
                base_mae=abs(g.corner_0 - g.y).mean(),
                team_opportunity_mae=abs(g.T_hat - g.T_actual).mean(),
                individual_opportunity_mae=abs(g.T_hat * g.S_hat - g.N_actual).mean(),
                actual_team_individual_opportunity_mae=abs(
                    g.T_actual * g.S_hat - g.N_actual
                ).mean(),
                actual_share_individual_opportunity_mae=abs(
                    g.T_hat * g.S_actual - g.N_actual
                ).mean(),
                oracle_team_only_mae=abs(g.corner_1 - g.y).mean(),
                oracle_share_only_mae=abs(g.corner_2 - g.y).mean(),
                oracle_efficiency_only_mae=abs(g.corner_4 - g.y).mean(),
                team_shapley=g.shapley_team_error_reduction.mean(),
                share_shapley=g.shapley_share_error_reduction.mean(),
                efficiency_shapley=g.shapley_efficiency_error_reduction.mean(),
                exceptional_shapley=g.shapley_exception_error_reduction.mean(),
                full_oracle_mae=abs(g.corner_15 - g.y).mean(),
                zero_opportunities=int(g.zero_opportunity.sum()),
                incoherent_shares=int(g.actual_share_incoherent.sum()),
            )
        )
    oracle_summary = pd.DataFrame(rows)
    oracle_summary.to_csv(output / "hindsight_only_accounting.csv", index=False)
    sections.append(table(oracle_summary))
    sections.append(
        "These are explicit hindsight substitutions in an unfitted five-game ratio strawman, NOT improvements to the fitted Stage 1B.1/C1 models and NOT forecasts available to a bettor. Four-factor Shapley accounting averages all 24 orders and reconciles the reduction in absolute error, including exceptional zero-opportunity lateral production. When opportunities are zero, efficiency is unobserved and stays at its feasible estimate. Share is similarly unobserved when team opportunities are zero. No oracle enters model selection, probabilities or a deployment bundle. Oracle headroom is not evidence that a feasible allocation model can realise it."
    )
    sections.append("## Scope and next decision")
    sections.append(
        "Retain data contracts, reconciliation and diagnostics as research infrastructure. Do not activate the combined context or diagnostic probability wrapper based on these inspected development results. Resolve residual stat-credit inconsistencies and obtain reproducible pre-decision roster/usage provenance before any allocation feature is labelled live-valid. If separately approved, a bounded C3 feasibility experiment should compare team-volume-only versus player-share-only versus their combination on identical rows, with prior-window selection and the final period sealed. Current oracle accounting can prioritise that question but cannot answer it. No C3–C6 implementation, paid odds provider or dashboard hosting is included."
    )
    (output / "RESULTS.md").write_text("\n\n".join(sections) + "\n")
    print(output / "RESULTS.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/stage1c1-results")
    args = parser.parse_args()
    report(args.directory, args.output)
