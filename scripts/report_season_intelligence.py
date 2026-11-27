"""Read-only statistical report; no fitting, network, sealed results or activation."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from season_intelligence.experiment import DEFAULT
from season_intelligence.validate import validate
from stage1b.data import MARKETS
from weekly_learning.store import ROOT, encoded, sha


def block_ci(values, seed=221126):
    values = np.asarray(values, float)
    b = np.array([values[i : i + 2].mean() for i in range(0, len(values), 2)])
    rng = np.random.default_rng(seed)
    draws = rng.choice(b, (1000, len(b)), replace=True).mean(axis=1)
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def main():
    validate(DEFAULT)
    frame = pd.read_parquet(DEFAULT / "historical_predictions.parquet")
    probs = pd.read_parquet(DEFAULT / "probability_predictions.parquet")
    metrics = pd.read_csv(DEFAULT / "point_metrics.csv")
    pm = pd.read_csv(DEFAULT / "probability_metrics.csv")
    choices = json.loads((DEFAULT / "selection.json").read_text())
    models = joblib.load(DEFAULT / "research_models.joblib")
    pushrows = []
    uncertainty = []
    for market in MARKETS:
        for year in [2025, 2026]:
            g = frame[frame.market.eq(market) & frame.season.eq(year)]
            law = models["laws"][(market, year)]
            method = choices[market]["research_point_method"]
            for r in g.itertuples():
                line = float(np.floor(r.baseline))
                p = law.price(getattr(r, method), r.position, MARKETS[market][3], line)
                actual = np.array([r.y > line, r.y < line, r.y == line], float)
                predictions = np.array([p["over"], p["under"], p["push"]])
                pushrows.append(
                    {
                        "market": market,
                        "season": year,
                        "week": r.week,
                        "player_id": r.player_id,
                        "position": r.position,
                        "line": line,
                        "p_push": p["push"],
                        "observed_push": r.y == line,
                        "ternary_brier": float(((predictions - actual) ** 2).sum()),
                        "ternary_log_loss": float(
                            -np.log(max(predictions[np.argmax(actual)], 1e-6))
                        ),
                    }
                )
            p = probs[probs.market.eq(market) & probs.season.eq(year)]
            a = (
                p[p.method.eq("champion_normal")]
                .groupby("week")[["brier", "log_loss"]]
                .mean()
            )
            b = (
                p[p.method.eq("research_empirical")]
                .groupby("week")[["brier", "log_loss"]]
                .mean()
            )
            for score in ["brier", "log_loss"]:
                low, high = block_ci(a[score] - b[score])
                uncertainty.append(
                    {
                        "market": market,
                        "season": year,
                        "metric": score,
                        "mean_weekly_improvement": float((a[score] - b[score]).mean()),
                        "low95": low,
                        "high95": high,
                        "weeks": len(a),
                        "scope": "paired two-week blocks; hypothetical lines averaged within week; not an independent final test",
                    }
                )
    pushes = pd.DataFrame(pushrows)
    pushreport = pushes.groupby(["market", "season"], as_index=False).agg(
        n=("p_push", "size"),
        predicted_push=("p_push", "mean"),
        observed_push=("observed_push", "mean"),
        ternary_brier=("ternary_brier", "mean"),
        ternary_log_loss=("ternary_log_loss", "mean"),
    )
    docs = ROOT / "docs"
    pushreport.to_csv(docs / "season-intelligence-push-diagnostics.csv", index=False)
    pd.DataFrame(uncertainty).to_csv(
        docs / "season-intelligence-probability-uncertainty.csv", index=False
    )
    points = []
    for market, c in choices.items():
        for year in [2025, 2026]:
            g = metrics[metrics.market.eq(market) & metrics.season.eq(year)].set_index(
                "method"
            )
            b = g.loc["baseline"]
            a = g.loc[c["research_point_method"]]
            points.append(
                {
                    "market": market,
                    "season": year,
                    "n": int(b.n),
                    "method": c["research_point_method"],
                    **{
                        prefix + "_" + metric: float(row[metric])
                        for prefix, row in [("baseline", b), ("research", a)]
                        for metric in ["mae", "rmse", "bias"]
                    },
                    "mae_gain": float(1 - a.mae / b.mae),
                }
            )
    pd.DataFrame(points).to_csv(
        docs / "season-intelligence-selected-point-metrics.csv", index=False
    )
    position_rows = []
    for (market, year, position), g in frame.groupby(["market", "season", "position"]):
        for name, column in [
            ("baseline", "baseline"),
            ("research", choices[market]["research_point_method"]),
        ]:
            error = g[column] - g.y
            position_rows.append(
                {
                    "market": market,
                    "season": int(year),
                    "position": position,
                    "method": name,
                    "n": len(g),
                    "mae": float(error.abs().mean()),
                    "rmse": float(np.sqrt((error**2).mean())),
                    "bias": float(error.mean()),
                }
            )
    pd.DataFrame(position_rows).to_csv(
        docs / "season-intelligence-position-point-metrics.csv", index=False
    )
    lines = [
        "# Sunday 22 November 2026 — player intelligence research",
        "",
        "**Research only. No model, probability, slate or betting recommendation has been promoted. No profitability claim.**",
        "",
        "## Evidence and data corrections",
        "",
        "55,782 matched player-market observations / 1,237 games / 7,622 genuine zeros. 2022–24 annual-origin development; 2025 method selection; 6,856 observations in previously inspected 2026 Weeks1–10 diagnostics. All fits use earlier available outcomes, with the inherited36-hour historical publication proxy. The final period remains sealed.Each2026 replay fit uses only pre-season outcomes; pregame histories update each game. The weights were actually fitted on21November, not historically before the season. The fit_before/model_fit_before fields denote training-outcome availability cutoffs, not actual file creation timestamps; actual build timestamps are recorded separately. This is annual rolling-origin replay, not weekly re-estimation.",
        "",
        "The original research PBP/player snapshot contained only one Week10 game. The certified20November features provide the remainder. Some refreshed2026 stored legacy history counts reset despite2019–25 raw history being present. The research copy now rebuilds entering-game features with the unchanged shared calculators, preserving cross-season history and matching all compared populations. Older observed data may fill a missing refresh field only when canonical player/game/team identity agrees; no observed box records required this recovery. No missing outcome becomes zero. OAK/LV and other existing C0 aliases use the established canonical mapping. Neither source file nor any certified forecast was edited. A preliminary incomplete-history comparison was discarded before inspecting error metrics.",
        "",
        "Five preregistered point families: recent workload shrinkage; player-only ridge; role/share/efficiency ridge; opponent/team ridge; robust nonlinear context tree. Same-backbone ridge ablations isolate feature-family effects. Tree gains combine backbone and feature effects and cannot establish that matchup variables caused improvement. Grouped permutation diagnostics are within2026week/position, exploratory and affected by feature correlation. No current teammate participation list is inferred from actual participants. Historical active-roster, injury, route and defensive personnel publication evidence remains unavailable.",
        "",
        "## Fixed selection and inspected2026 results",
        "",
        "| Market |2026 n| Baseline MAE | Research MAE | Gain |2025 point gate|",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in [r for r in points if r["season"] == 2026]:
        lines.append(
            f"|{r['market']}|{r['n']}|{r['baseline_mae']:.3f}|{r['research_mae']:.3f}|{100 * r['mae_gain']:+.2f}%|{choices[r['market']]['retrospective_point_gate']}|"
        )
    lines += [
        "",
        "The point gate requires≥2% selection MAE gain, paired week-block uncertainty and Holm correction across45 comparisons. Five markets pass those retrospective point gates. Passing yards, attempts and both QB rushing point markets retain baseline estimates; the better-looking2026 QB-carry alternative was not selected retrospectively. No independent final evidence or automatic promotion is claimed. Raw failed candidates remain visible only as experimental comparisons.",
        "",
        "## Probability evidence",
        "",
        "The research CDF uses shrinking conditional empirical nonzero errors, an explicit observed zero atom, and integer support (negative yardage allowed; negative counts excluded). It is fitted on annual out-of-sample residuals from strictly earlier seasons. Count/yardage distributions are not assumed normal. Zero mass is conditional on established participation, not an invented probability of inactivity. Injury, no-play and bookmaker void conditions still require source/settlement evidence. Sunday point models are refitted using permitted completed history; their newer weights have not themselves received fresh independent testing. Sunday CDFs remain fitted on2022–25 OOF data, not2026 diagnostics.",
        "",
        "| Market |2026 normal log loss| Research log loss| Normal Brier| Research Brier|2025 probability gate|",
        "|---|---:|---:|---:|---:|---|",
    ]
    for market, c in choices.items():
        g = pm[pm.market.eq(market) & pm.season.eq(2026)].set_index("method")
        a = g.loc["champion_normal"]
        b = g.loc["research_empirical"]
        lines.append(
            f"|{market}|{a.log_loss:.4f}|{b.log_loss:.4f}|{a.brier:.4f}|{b.brier:.4f}|{c['retrospective_probability_gate']}|"
        )
    lines += [
        "",
        "Primary probability scores use three predeclared illustrative half-lines around the champion projection, never historical bookmaker quotes. Six markets meet the2025 probability rule (≥2% log-loss reduction without Brier deterioration); passing yards/attempts and QB carries do not. Only that retrospective rule is reported, not full promotion. Probability uncertainty, bands, both sides and positions are saved separately; repeated lines are not treated as independent games. Receiving-yard2025 ECE is1.20 percentage points, best among these research markets. The shortlist therefore concentrates on receiving yards; cross-market Brier alone must not be interpreted as proof of betting quality.",
        "",
        "2026 90% interval coverage remains conservative for low count markets (receptions about95.8%, QB carries95.5%). Passing-yard intervals widen to restore coverage; a narrower interval is not automatically better. Integer-line diagnostics evaluate actual pushes and three-way probabilities separately; they do not validate any real bookmaker rule or price. Conditional refund-push fair odds are(1−P(push))/P(win). Experimental EV at a user-supplied decimal quote isP(win)×(odds−1)−P(loss). No integer-line selection or real-money recommendation is automated.",
        "",
        "## Sunday research shortlist",
        "",
        "522 eligible forecasts /10Sunday fixtures /20Top2 entries. TEN–DAL unresolved roof scenarios are excluded; the Monday-night fixture is not relabelled Sunday. The original618-row release,568complete forecasts,50roof scenarios and22baseline Top Picks are untouched. Eligibility uses the dated20November certificate, not live injury news. These new build timestamps do not pretend the source evidence was refreshed today. All opportunities stop being current atT−60.",
        "",
        "| Player |Market| Original | Candidate | Hypothetical line | Research over probability |",
        "|---|---|---:|---:|---:|---:|",
    ]
    short = pd.read_csv(DEFAULT / "sunday_shortlist.csv")
    for r in short.itertuples():
        lines.append(
            f"|{r.player}|{r.market}|{r.baseline:.1f}|{r.enhanced_candidate:.1f}|{r.hypothetical_line:.1f}|{r.p_over:.1%}|"
        )
    lines += [
        "",
        "**The lines above are illustrative, not available bookmaker lines. These are player-prop research priorities, not Over/Under bets or positive-EV claims.** The empirical distribution is asymmetric, so its median/over probability need not agree with a regression point forecast; the latter is not claimed to be the CDF mean. Unpassed probability families are displayed as explicitly experimental, not selected methods.",
        "",
        "## Access and safeguards",
        "",
        "Existing research app → Game Intelligence → Sunday player-workload and probability research. Expand the supplied-line calculator to enter a real quote; prices start empty. Integer EV requires owner-confirmed full-stake refund rules. All output is experimental and isolated from production pricing/ledger/recommendations. Original nine model hashes and baseline projections are checked unchanged. The historical model and Sunday model numerical replay tolerance is absolute1e−10, relative zero; file/source/model hashes and original baseline copies remain exact.",
        "",
        "No SportsGameOdds calls, quota edits, credentials, production/main changes, new services, billing or schedules. Existing free runtime/dependencies only. No historical sportsbook ROI is calculable from these inputs.",
        "",
    ]
    (docs / "SUNDAY_SEASON_INTELLIGENCE.md").write_text("\n".join(lines))
    audit = {
        "experiment_manifest_sha256": sha(DEFAULT / "manifest.json"),
        "research_model_sha256": sha(DEFAULT / "research_models.joblib"),
        "report_script_sha256": sha(Path(__file__)),
        "push_diagnostics_sha256": sha(
            docs / "season-intelligence-push-diagnostics.csv"
        ),
        "uncertainty_sha256": sha(
            docs / "season-intelligence-probability-uncertainty.csv"
        ),
        "scope": "Read-only supplemental diagnostics; no refit, selection or sealed outcomes",
    }
    (docs / "season-intelligence-report-provenance.json").write_text(encoded(audit))
    print(encoded(audit), flush=True)


if __name__ == "__main__":
    main()
