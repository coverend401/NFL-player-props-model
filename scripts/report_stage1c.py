"""Review C0–C2 ablations without changing any fitted or selected model."""

import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import nbinom
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stage1c.artifacts import validate
from stage1c.context import states, attach, volume_cdf
from stage1c.models import point_predict
from stage1c.runner import load
from stage1b.data import MARKETS, market_panel
from stage1b.metrics import week_block_interval
from stage1b.probability import inverse_cdf
import joblib


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
    audit = validate(path, ROOT)
    manifest = json.loads((path / "manifest.json").read_text())
    p, base, bm, inp, games, rates, ctx, panel = load(ROOT)
    a = pd.read_csv(path / "accuracy.csv")
    prob = pd.read_csv(path / "probability_metrics.csv")
    delta = pd.read_csv(path / "paired_accuracy.csv")
    q = pd.read_parquet(path / "probes.parquet")
    f = pd.read_parquet(path / "forecasts.parquet")
    reliability = pd.read_csv(path / "reliability.csv")
    dest = ROOT / "docs"
    prefix = "stage1c-c0-c2"
    grouping = ["row_id", "market", "version", "evaluation_tier", "season", "week"]
    avg = q.groupby(grouping, as_index=False)[["brier", "log_loss"]].mean()
    pdiff = []
    for ref in ["stage1b1", "player_control"]:
        old = avg[avg.version.eq(ref)].drop(columns="version")
        for version in p["families"]:
            if version == ref:
                continue
            new = avg[avg.version.eq(version)].drop(columns="version")
            z = new.merge(
                old,
                on=[c for c in grouping if c != "version"],
                suffixes=("_new", "_ref"),
                validate="one_to_one",
            )
            for (market, tier), g in z.groupby(["market", "evaluation_tier"]):
                for metric in ["brier", "log_loss"]:
                    g = g.copy()
                    g["delta"] = g[metric + "_new"] - g[metric + "_ref"]
                    low, high = week_block_interval(g, "delta")
                    pdiff.append(
                        dict(
                            market=market,
                            evaluation_tier=tier,
                            version=version,
                            reference=ref,
                            metric=metric,
                            n=len(g),
                            delta=float(g.delta.mean()),
                            low=low,
                            high=high,
                        )
                    )
    pd.DataFrame(pdiff).to_csv(
        dest / (prefix + "-paired-probabilities.csv"), index=False
    )
    # Team-level volume and script diagnostics are not bookmaker forecasts.
    c = ctx[ctx.kind.eq("pass")].merge(
        games, on=["game_id", "team"], suffixes=("", "_outcome"), validate="one_to_one"
    )
    c = c[c.season.ge(2022)].copy()
    intermediate = []
    for year, g in [
        ("development", c[c.season.lt(2026)]),
        ("monitoring", c[c.season.eq(2026)]),
    ]:
        weights = g[["script_trailing", "script_close", "script_leading"]].to_numpy()
        labels = np.where(g.margin.lt(-7), 0, np.where(g.margin.gt(7), 2, 1))
        league = g[
            ["league_script_trailing", "league_script_close", "league_script_leading"]
        ].to_numpy()
        row = dict(
            period=year,
            n_team_games=len(g),
            plays_mae=float(abs(g.expected_plays - g.plays).mean()),
            own_prior_plays_mae=float(abs(g.own_prior_plays - g.plays).mean()),
            dropbacks_mae=float(abs(g.expected_dropbacks - g.dropbacks).mean()),
            own_prior_dropbacks_mae=float(
                abs(g.own_prior_dropbacks - g.dropbacks).mean()
            ),
            dropback_share_mae=float(
                abs(g.expected_dropback_share - g.dropbacks / g.plays).mean()
            ),
            script_brier=float(
                np.mean(np.sum((weights - np.eye(3)[labels]) ** 2, axis=1))
            ),
            league_script_brier=float(
                np.mean(np.sum((league - np.eye(3)[labels]) ** 2, axis=1))
            ),
            script_log_loss=float(-np.log(weights[np.arange(len(g)), labels]).mean()),
            league_script_log_loss=float(
                -np.log(league[np.arange(len(g)), labels]).mean()
            ),
        )
        for metric, values in [
            (
                "script_brier_delta",
                np.sum((weights - np.eye(3)[labels]) ** 2, axis=1)
                - np.sum((league - np.eye(3)[labels]) ** 2, axis=1),
            ),
            (
                "script_log_loss_delta",
                -np.log(weights[np.arange(len(g)), labels])
                + np.log(league[np.arange(len(g)), labels]),
            ),
            (
                "plays_mae_delta",
                abs(g.expected_plays - g.plays) - abs(g.own_prior_plays - g.plays),
            ),
        ]:
            z = g[["season", "week"]].copy()
            z["delta"] = np.asarray(values)
            low, high = week_block_interval(z, "delta")
            row[metric] = float(np.mean(values))
            row[metric + "_low"] = low
            row[metric + "_high"] = high
        for quantity in ["plays", "dropbacks"]:
            cdf = volume_cdf(g, quantity)
            lo = inverse_cdf(cdf, len(g), 0.05)
            hi = inverse_cdf(cdf, len(g), 0.95)
            means = g[
                [quantity + "_" + s + "_mean" for s in ["trailing", "close", "leading"]]
            ].to_numpy()
            size = 1 / g.volume_alpha.to_numpy()
            ll = logsumexp(
                np.log(weights)
                + nbinom.logpmf(
                    g[quantity].to_numpy()[:, None],
                    size[:, None],
                    size[:, None] / (size[:, None] + means),
                ),
                axis=1,
            )
            row[quantity + "_count_log_loss"] = float(-ll.mean())
            row[quantity + "_coverage90"] = float(
                ((g[quantity] >= lo) & (g[quantity] <= hi)).mean()
            )
            row[quantity + "_width90"] = float(np.mean(hi - lo))
        intermediate.append(row)
    pd.DataFrame(intermediate).to_csv(
        dest / (prefix + "-team-diagnostics.csv"), index=False
    )
    coverage = (
        rates.groupby("kind")
        .agg(
            team_groups=("game_id", "size"),
            known_complete=("known_complete", "sum"),
            unknown_players=("unknown_players", "sum"),
        )
        .reset_index()
    )
    coverage["complete_fraction"] = coverage.known_complete / coverage.team_groups
    coverage.to_csv(dest / (prefix + "-input-coverage.csv"), index=False)
    # Frozen-model lag stress; never retrain/reselect based on these outcomes.
    sensitivity = []
    for lag in [8, 72]:
        altered = states(games, rates, lag_hours=lag)
        for market in MARKETS:
            d = attach(market_panel(panel, market), altered, market)
            for year in p["evaluation_seasons"]:
                e = d[d.season.eq(year) & d.feature_complete & d.scorable]
                orig = f[
                    (f.market == market) & (f.season == year) & (f.version == "c1_c2")
                ].set_index("row_id")
                b = joblib.load(path / "models" / f"{market}-{year}-c1_c2.joblib")
                mu = point_predict(b, e)
                ids = market + "|" + e.player_id + "|" + e.game_id
                original = orig.loc[ids, "projection"].to_numpy()
                sensitivity.append(
                    dict(
                        lag_hours=lag,
                        market=market,
                        season=year,
                        n=len(e),
                        mae=float(abs(mu - e.y.to_numpy()).mean()),
                        baseline36h_mae=float(abs(original - e.y.to_numpy()).mean()),
                        mean_abs_forecast_change=float(abs(mu - original).mean()),
                    )
                )
    pd.DataFrame(sensitivity).to_csv(dest / (prefix + "-lag-stress.csv"), index=False)
    cohorts = []
    for (market, tier, version), g in f.groupby(
        ["market", "evaluation_tier", "version"]
    ):
        for name, mask in [
            ("returning_gap21plus", g.returning),
            ("history3to7", g.games_played_prior.lt(8)),
            ("history8plus", g.games_played_prior.ge(8)),
            ("observed_zero_descriptive", g.y.eq(0)),
        ]:
            z = g[mask]
            if not z.empty:
                cohorts.append(
                    dict(
                        market=market,
                        evaluation_tier=tier,
                        version=version,
                        cohort=name,
                        n=len(z),
                        mae=float(abs(z.projection - z.y).mean()),
                        bias=float((z.projection - z.y).mean()),
                    )
                )
    pd.DataFrame(cohorts).to_csv(dest / (prefix + "-cohorts.csv"), index=False)
    dev = a[(a.season == "all") & (a.evaluation_tier == "development_oos")]
    ds = prob[(prob.season == "all") & (prob.evaluation_tier == "development_oos")]
    pointrows = []
    order = ["stage1b1", *p["families"]]
    for version in order:
        x = dev[(dev.market == "passing_yards") & (dev.version == version)].iloc[0]
        z = ds[(ds.market == "passing_yards") & (ds.version == version)].iloc[0]
        pointrows.append(
            [
                version,
                f"{x.mae:.3f}",
                f"{x.rmse:.3f}",
                f"{x.bias:+.3f}",
                f"{z.brier:.6f}",
                f"{z.log_loss:.6f}",
                f"{100 * x.coverage90:.2f}%",
                f"{x.width90:.2f}",
                f"{x.interval_score90:.2f}",
            ]
        )
    allrows = []
    for market, g in dev.groupby("market"):
        vals = {r.version: r.mae for r in g.itertuples()}
        allrows.append([market] + [f"{vals[v]:.3f}" for v in order])
    cirows = []
    for r in delta[
        (delta.market == "passing_yards")
        & (delta.evaluation_tier == "development_oos")
        & (delta.metric == "mae")
    ].itertuples():
        cirows.append(
            [
                r.version,
                r.reference,
                f"{r.delta:+.3f}",
                f"[{r.low:+.3f}, {r.high:+.3f}]",
            ]
        )
    years = []
    for year, g in a[(a.market == "passing_yards") & (a.season != "all")].groupby(
        "season"
    ):
        vals = {r.version: r for r in g.itertuples()}
        years.append(
            [year, vals["stage1b1"].n]
            + [
                f"{vals[v].mae:.3f}"
                for v in ["stage1b1", "player_control", "c1_schedule", "c1_c2"]
            ]
        )
    ece = []
    for (market, version), g in reliability[
        reliability.evaluation_tier.eq("development_oos")
    ].groupby(["market", "version"]):
        ece.append(
            dict(
                market=market,
                version=version,
                ece=float(
                    np.average(abs(g.observed - g.mean_probability), weights=g.n_probes)
                ),
            )
        )
    pd.DataFrame(ece).to_csv(dest / (prefix + "-ece.csv"), index=False)
    probrows = []
    intervalrows = []
    for market, g in ds.groupby("market"):
        b = g[g.version == "stage1b1"].iloc[0]
        n = g[g.version == "c1_c2"].iloc[0]
        probrows.append(
            [
                market,
                f"{b.brier:.6f}",
                f"{n.brier:.6f}",
                f"{b.log_loss:.6f}",
                f"{n.log_loss:.6f}",
            ]
        )
        z = dev[dev.market == market]
        b = z[z.version == "stage1b1"].iloc[0]
        n = z[z.version == "c1_c2"].iloc[0]
        intervalrows.append(
            [
                market,
                f"{100 * b.coverage90:.2f}% → {100 * n.coverage90:.2f}%",
                f"{b.width90:.2f} → {n.width90:.2f}",
                f"{b.interval_score90:.2f} → {n.interval_score90:.2f}",
            ]
        )
    summary = dict(
        experiment=manifest["experiment_id"],
        source_commit=manifest["source_commit"],
        audit=audit,
        unique_player_market_games=55303,
        development_n=49034,
        monitoring_n=6269,
        unique_team_games=len(games),
        genuine_quotes=0,
        betting_profit=None,
        final_sealed=True,
        evidence_tier="retrospective",
        primary_passing_yards=dev[dev.market.eq("passing_yards")].to_dict("records"),
        team_diagnostics=intermediate,
        retention="Retain C0 research infrastructure; do not promote any contextual variant; primary gate not met.",
        source_completeness=coverage.to_dict("records"),
    )
    (dest / (prefix + "-summary.json")).write_text(json.dumps(summary, indent=2) + "\n")
    text = (
        f"""# Stage 1C C0–C2 results

Research experiment `{manifest["experiment_id"]}`, scientific source commit
`{manifest["source_commit"]}`. **No primary passing-yard improvement over Stage
1B.1 was established. Do not promote any new model or probabilities.** Keep the
C0 contracts/replay and the failed contextual candidates as research evidence.
No parameter, feature family or method was retuned after this full experiment.

## Evidence and sample

270 fitted market/year/family bundles; seven versions including the exact frozen
Stage 1B.1 comparator. Every variant scores the same **55,303 player-market games**:
49,034 development (2022–25; 6,709 observed zeros) and 6,269 already-viewed 2026
monitoring observations (903 zeros). No sample reduction or zero fabrication.
There are 387,121 forecast rows and 1,161,363 hypothetical pricing probes.
These previously inspected periods are NOT a new independent test. The **2026
week-11 onward final period remains sealed**, with no final outcome inspection.

All additional inputs are **retrospective corrected statistics**. Thirty-six-hour
context availability is a proxy, not an authenticated publication archive. There
are **zero genuinely verified historical pre-decision context records** in this
experiment. No historical prop quotes, genuine bets, realised profit or ROI exist.
PBP original-byte hashes and small immutable aggregates are preserved for replay,
not presented as independent proof of historical publication.

## Passing yards: primary outcome

"""
        + table(
            [
                "Version",
                "MAE",
                "RMSE",
                "Bias",
                "Brier",
                "Log loss",
                "90% coverage",
                "Width",
                "Interval score",
            ],
            pointrows,
        )
        + """

Combined C1–C2 MAE is **68.226 vs Stage 1B.1 68.140** (+0.085 yards, +0.13%).
Against the common player control it improves **68.455 → 68.226** (−0.230,
−0.34%), below the registered 1% practical gate with an interval crossing zero.
The schedule-adjusted variant improves the common control by 0.291 yards (0.43%),
but is still 0.023 worse than Stage 1B.1 and its control-comparison band includes
zero. **No contextual passing-yard variant meets the primary retention criterion.**

Paired four-observed-week bootstrap MAE differences, conditional on fitted folds:

"""
        + table(["Version", "Reference", "Delta yards", "95% exploratory band"], cirows)
        + """

The new control uses a common small candidate budget, not a reconstruction of the
Stage 1B.1 point recipe. Its MAE is itself worse than Stage 1B.1. Therefore changes
against Stage 1B.1 include a backbone/probability-wrapper change; only comparisons
to `player_control` isolate adding context under the common recipe. A small gain
against a weaker control does not justify replacing the frozen stronger model.
These results do not prove that all matchup features are intrinsically useless.

Bias is reduced in the combined model (+7.195 → +5.464), and interval score is
lower (350.25 → 343.92), but probability Brier/log loss worsen materially. Do not
select the favourable metrics while disregarding the primary and pricing failures.

Per-season primary MAE, including already-viewed monitoring:

"""
        + table(["Season", "N", "Stage 1B.1", "Control", "C1 schedule", "C1+C2"], years)
        + """

Monitoring combined MAE **67.119 → 68.032** is a regression. The primary point
findings are not stable enough to support retention or production activation.

## All nine point markets

Mean absolute error, development only; units are each market's yards/counts:

"""
        + table(["Market", *order], allrows)
        + """

Tiny RB-market point gains in isolated variants do not satisfy the registered
practical gate or establish broad improvement. QB rushing often retains career
mean after prior validation, so identical MAE is expected rather than evidence
that a context learner improved. No winner is selected retrospectively per season.
All per-season MAE/RMSE/bias/counts are in the archive `accuracy.csv`; paired point
and interval differences are in `paired_accuracy.csv`. Cohorts are provided in
`stage1c-c0-c2-cohorts.csv`; returning is a >21-day prior participation gap,
including offseason, not retrospective injury knowledge.

## Probabilities and intervals

Combined context versus the archived benchmark:

"""
        + table(
            ["Market", "1B.1 Brier", "C1+C2 Brier", "1B.1 log loss", "C1+C2 log loss"],
            probrows,
        )
        + """

All family/season scores are in `probability_metrics.csv`; paired Brier/log-loss
bands against BOTH references are in `stage1c-c0-c2-paired-probabilities.csv`.
These are three dependent career-mean half-line probes per player-game, not
bookmaker lines. Their per-game scores are averaged for inference. The control
and context share a newly trained CDF/calibration recipe; archived calibration
was not reused under new point models. Comparisons against Stage 1B.1 therefore
do not isolate a fixture effect. No probability method should be promoted here.

Nominal 90% predictive interval quality:

"""
        + table(
            ["Market", "Coverage: 1B.1 → C1+C2", "Width", "Interval score"],
            intervalrows,
        )
        + """

Reliability by band, sample size and dependent-week intervals is in the immutable
`reliability.csv`; descriptive ECE is in `stage1c-c0-c2-ece.csv`. Assess proper
scores with reliability, not ECE alone. Predictive sets need not match selected
CDF quantiles, and temporal conformal coverage is not guaranteed. These direct
models are separate marginals: joint player allocation/coherence is out of scope.

## C0 data quality and C1 limitations

"""
        + table(
            ["Category", "Team groups", "Known complete", "Complete fraction"],
            [
                [
                    r.kind,
                    int(r.team_groups),
                    int(r.known_complete),
                    f"{100 * r.complete_fraction:.1f}%",
                ]
                for r in coverage.itertuples()
            ],
        )
        + """

Official passing totals have complete coverage in the selected team games.
Positional aggregates are frequently incomplete because players with snap records
have no observed box-score outcomes. They are marked unknown and skipped, with
state decay and source-completeness features; they are NEVER assigned zero. The
absence of eight QB-rushing groups is not invented as eight zero totals. Missingness
is nonrandom (role/rotation/recording), so rates based on complete groups can still
be biased. This is a major reason not to claim validated positional intelligence.

Historical aliases were normalised before grouping, preventing OAK/LV fragments
from duplicating the same fixture side. Team/player identity still inherits the
benchmark's retrospective role and participation limitations. The effective-dated
identity contract exists, but no historical live roster archive was fabricated.
Schedule adjustment is a first-order entering-offence residual, not a fully
identified simultaneous attack/defence or causal rating. Denominator uncertainty,
missingness and simplistic shrinkage may mask or distort matchup signals.

## C2 intermediate quality and availability sensitivity

See `stage1c-c0-c2-team-diagnostics.csv` for competitive-play/dropback MAE,
count-distribution log loss and 90% width/coverage; script multiclass Brier/log loss
are compared with prior league frequencies. These intermediate diagnostics do not
substitute for improved player forecasts. Development scenario Brier improves
0.62271 → 0.60617 versus prior league frequencies, and log loss 1.03647 → 1.00267.
Play-volume MAE improves only 6.632 → 6.604, while dropback MAE worsens slightly
6.429 → 6.436. Nominal 90% dropback intervals cover only **85.83%**. These are
mixed intermediate findings, not evidence for a new player model. Paired week-block
bands are in the diagnostics CSV. Competitive plays and dropbacks differ
from official carries and pass attempts; the model never supplies actual future
play counts or score paths as predictors.

Script categories refer to final-margin scenarios (±7 points), not a full temporal
score simulator. Student margin and NB2 volume-mixture assumptions are provisional;
team distributions are uncalibrated context, not bookmaker probabilities. Pace is
a possession/game-clock proxy. There is no spread/total branch because timestamped
market data is unavailable, and no fake historical closing-line substitution.

`stage1c-c0-c2-lag-stress.csv` records frozen combined-model forecasts with +8h/
+72h source proxies. No model was refit or chosen on those results. This stress
test cannot establish actual historical publication times. Thirty-six-hour feeds
are still unsuitable for a genuinely verified live deployment until observed
source receipt/publication archives exist.

## Retention and next decision

- **Retain C0 as research infrastructure:** canonical/effective identity contracts,
  explicit evidence tiers, sealed predicates, as-of fixture states, incomplete-data
  checks, fixed-population comparisons, immutable inputs and full replay.
- **Keep C1 candidates archived, not promoted.** Passing-yard effects are small and
  uncertain; missing positional totals and first-order schedule adjustment limit
  interpretation. Do not represent them as validated defensive strengths.
- **Keep C2 experimental, not promoted.** The market-free baseline and diagnostics
  are useful, but no downstream primary gain is demonstrated. Do not turn its
  scenario probabilities into live betting probabilities.
- A future separately scoped experiment could preserve the stronger archived point
  recipe while adding context, improve completeness/reconciliation and investigate
  source-timing evidence. Preregister it; do not keep rerunning these viewed data
  until they appear positive. No C3–C6 work, paid source or dashboard is begun.
- No production model/probability change is recommended. Stage 1A remains active;
  the research PR requires owner approval to merge and cannot deploy anything.

## Reproduction and evidence

Scientific source was committed before the full run. `stage1c/protocol.json` and
`STAGE1C_C0_C2_PROTOCOL.md` fix families, phases, candidate budget and assumptions.
Hashes bind code, exact 69-package runtime, input aggregates, baseline and outputs.
Validation checks identical outcomes/IDs, source timing, model matrix, hypothetical
probe thresholds/scores and preserved frozen comparators. Every fitted model and
its forecast/probability outputs are replayed. No production database or settings
were accessed. Raw data are attributed to **nflverse contributors / NFL play-by-play**
and the selected project's frozen player-stat snapshot; source URLs/hashes are in
the input manifest. Upstream publication/retention conditions remain relevant.

```sh
python -m stage1c.artifacts experiments/stage1c/c0-c2-20261113-v1 --replay
python scripts/report_stage1c.py
python -m unittest discover -s tests -v
```

Re-fitting requires a NEW immutable experiment ID and the pinned Python 3.14
runtime. No production entry point imports `stage1c`. Full baseline limitations,
source availability and the approved proposal remain in the companion documents.
"""
    )
    (dest / "STAGE1C_C0_C2_RESULTS.md").write_text(text)
    print(
        json.dumps(
            {
                "audit": audit,
                "primary": summary["primary_passing_yards"],
                "team_diagnostics": intermediate,
            }
        )
    )


if __name__ == "__main__":
    report(
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "experiments/stage1c/c0-c2-20261113-v1"
    )
