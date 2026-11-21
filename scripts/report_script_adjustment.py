"""Read-only numerical experiment report; writes documentation, never forecasts/models."""

import json

import numpy as np
import pandas as pd

from script_adjustment.runner import DEFAULT
from script_adjustment.validate import validate
from weekly_learning.store import ROOT, encoded


def main():
    validate(DEFAULT)
    report = json.loads((DEFAULT / "report.json").read_text())
    metrics = pd.read_parquet(DEFAULT / "metrics.parquet")
    teams = pd.read_parquet(DEFAULT / "team_replay.parquet")
    allocations = pd.read_parquet(DEFAULT / "allocation_predictions.parquet")
    inputs = pd.read_parquet(DEFAULT / "share_inputs.parquet")
    joined = allocations.merge(
        inputs[["game_id", "player_id", "category", "stats_observed", "offense_pct"]],
        on=["game_id", "player_id", "category"],
        validate="one_to_one",
    )
    unknown = ~joined.stats_observed.eq(True) | ~joined.offense_pct.gt(0)
    fraction = float(
        joined.loc[unknown, "allocated_opportunities"].sum()
        / joined.allocated_opportunities.sum()
    )
    rng = np.random.default_rng(291126)
    uncertainty = []
    for year in [2025, 2026]:
        home = teams[teams.season.eq(year) & teams.is_home.eq(1)].copy()
        home["brier"] = (home.win_probability - home.margin.gt(0)) ** 2
        values = home.groupby("week").brier.mean().to_numpy()
        blocks = np.asarray(
            [values[i : i + 2].mean() for i in range(0, len(values), 2)]
        )
        draws = rng.choice(blocks, size=(1000, len(blocks)), replace=True).mean(axis=1)
        uncertainty.append(
            {
                "season": year,
                "estimator": "week-balanced home-win Brier; two-week nonoverlapping block bootstrap",
                "weeks": len(values),
                "mean": float(blocks.mean()),
                "low95": float(np.quantile(draws, 0.025)),
                "high95": float(np.quantile(draws, 0.975)),
            }
        )
    summary = {
        "experiment": str(DEFAULT.relative_to(ROOT)),
        "sample": report["sample"],
        "promotion_passed": False,
        "all_selected_scales": {
            m: c["eligible_scale"] for m, c in report["selection"].items()
        },
        "unknown_participation_capacity_fraction": fraction,
        "unknown_definition": "No scored current participation/box evidence for that historical candidate, not confirmed inactive and never a fabricated zero",
        "win_uncertainty": uncertainty,
        "status": "research-only; no active forecast/pricing/model changes",
    }
    (ROOT / "docs/script-adjustment-summary.json").write_text(encoded(summary))
    metrics.to_csv(ROOT / "docs/script-adjustment-market-metrics.csv", index=False)
    lines = [
        "# Numerical game-script engine — final research results",
        "",
        f"Final bundle: `{DEFAULT.relative_to(ROOT)}`. **Promotion failed; champion retained.**",
        "",
        "The engine changes player forecasts numerically. It is not activated in Top Picks, Top 2, probabilities, EV or production.",
        "",
        "## What was built",
        "",
        "Pregame win/margin models; 15 clock/score occupancy cells; conditional pass, designed-carry, scramble, kneel and other-action models; team volume forecasts; player opportunity shares with coherent caps and unassigned mass; and a residual adjustment projected off the champion inputs to avoid double-counting. Score/clock outcomes are historical targets or hypothetical integration cells, never the actual upcoming script.",
        "",
        "Historical teammate pools use only earlier observations and last-observed team/position. Absent observations remain unknown, not zero or inactive. Without historical timestamped roster evidence these are membership hypotheses, not verified active lineups. Live overlays use the certified release eligibility. Their transportability from imperfect historical membership is unvalidated.",
        "",
        "## Chronological evidence",
        "",
        f"{report['sample']['player_market_rows']:,} player-market observations, {report['sample']['games']:,} games and {report['sample']['zeros']:,} genuine zeros. Development: 2022–24; method selection: 2025; previously inspected diagnostic replay: 2026 Weeks 1–10. Each fit uses strictly earlier available outcomes. No Week 11 outcomes were read.",
        "",
        "The historical baseline replicates the champion feature lists and ridge/GBR/naive selection recipe at annual origins. The frozen November 2026 weights cannot be honestly scored on their own training history; they are not used for historical predictions. Auxiliary feature publication/model vintages and historical roster archives are not verified, so this is retrospective evidence, not a verified predecision archive.",
        "",
        "### 2025 method-selection errors, unit-scale experimental adjustment",
        "",
        "| Market | n | Baseline MAE | Adjusted MAE | MAE gain |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in metrics[metrics.season.eq(2025)].itertuples():
        lines.append(
            f"| {row.market} | {row.baseline_n} | {row.baseline_mae:.4f} | {row.adjusted_mae:.4f} | {row.mae_gain:+.2%} |"
        )
    lines += [
        "",
        "Positive gain means lower MAE. No market meets the preregistered 2% threshold and all additional paired uncertainty, Holm (27 scale/market comparisons), season consistency and fresh-final gates. The permitted scale is zero for all nine markets. Full season/market RMSE, bias, probability diagnostics, intervals, ablations and cohorts are in the bundle and CSV. Passing-yard bias worsens; small gains do not establish reliability.",
        "",
        "### Game-level performance",
        "",
        "| Season | Games | Home-win Brier | Log loss | Margin MAE | Plays MAE | Pass attempts MAE | Carries MAE | Occupancy RMSE / naive |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    tm = pd.read_parquet(DEFAULT / "team_metrics.parquet")
    for r in tm[tm.season.isin([2025, 2026])].itertuples():
        lines.append(
            f"| {r.season} | {r.games} | {r.win_brier:.4f} | {r.win_log_loss:.4f} | {r.margin_mae:.2f} | {r.plays_mae:.2f} | {r.attempts_mae:.2f} | {r.carries_mae:.2f} | {r.occupancy_share_rmse:.4f} / {r.occupancy_naive_rmse:.4f} |"
        )
    lines += [
        "",
        "Win uncertainty is reported in `script-adjustment-summary.json`. State probabilities describe a random offensive play (leading/tied/trailing), not the probability of leading all game. Occupancy improvements over recent team tendencies are modest. Reliability files report probability bands and game/play sample sizes; plays are correlated. Player Brier/log-loss and 90% interval metrics use fixed-scale champion-normal diagnostics at pregame hypothetical half-lines. They are assumption-sensitive comparisons, not certified adjusted distributions or bookmaker returns.",
        "",
        "## Data-quality and discarded prototypes",
        "",
        "The first development filter omitted `qb_kneel` and `qb_spike` play types; official rush/pass counts now include them. Six historical team-games still disagree with official player-derived attempts/carries (no unsupported corrections). The original participant-based historical pool also used eventual game membership in normalization; its apparent large passing gains were discarded. A regression test now requires future participation changes to leave the pregame teammate pool and allocations identical. Exact projection removes components already explained by champion inputs; numerical projection noise is not rescaled into a signal. These were correctness fixes, not outcome-driven tuning. Only the corrected v4 results are retained as evidence.",
        "",
        f"{fraction:.1%} of assigned historical capacity belongs to potential teammates without scored participation/box evidence for that fixture. This is not an inactive rate. It quantifies unresolved membership and explains why mathematical allocation coherence alone cannot justify promotion. Cold historical roster/inactive availability remains a material blocker to certified player allocation.",
        "",
        "## Numerical demonstration",
        "",
    ]
    view = pd.read_parquet(DEFAULT / "reference_week11_adjustments.parquet")
    for r in view[view.player.str.contains("Hubbard")].itertuples():
        lines.append(
            f"- Chuba Hubbard {r.market}: **{r.baseline:.2f} → {r.adjusted:.2f} ({r.delta:+.2f})**, experimental only."
        )
    lines += [
        "",
        "These are a separate overlay of the 568 complete certified Week 11 forecasts, not a replacement release. All 618 original rows, 50 labelled TEN–DAL roof scenarios, 22 baseline Top Picks, original model hashes and training timestamps remain untouched. Roof scenarios are not adjusted/priced/recommended. The new overlay was genuinely frozen before kickoff; it is not backdated to the original forecast.",
        "",
        "## Week12 and weekly operation",
        "",
        "The bundle contains an early 16-fixture / 32-team Week12 preview from the existing timestamped fixture plan and permitted history through Week10. **No Week12 player candidate has been generated, certified or selected.** It awaits the authorised 24 November12:00 UTC settlement gate, confirmed finals, fresh roster/depth evidence and original v2 inference certification. No stale Week11 player eligibility is reused.",
        "",
        "The existing weekly CLI now creates a separate experimental capture after champion certification, before T−60, and evaluates it only against admitted completed results. It records game-state/team-volume accuracy and workload/efficiency error identities separately; missing results are not zeros. If no predecision challenger capture exists, it never reconstructs one after results. Data/model failures preserve the champion and record an experimental blocker. No automatic promotion, fitting on the sealed benchmark, schedule activation or real-money action is added.",
        "",
        "After the authorised cutoff, use the existing operational command:",
        "",
        "```sh",
        "python -m weekly_learning.cli cycle --mode auto --id UNIQUE-CYCLE-ID",
        "python -m script_adjustment.validate --replay",
        "```",
        "",
        "The optional current-season play-by-play refresh is one bounded free nflverse download per new admitted snapshot, with no retries; cached immutable packs are reused. All protected games must match admission and official opportunity totals. It never calls SportsGameOdds or changes quota. Tuesday/Friday/Sunday default-branch scheduling still needs the previously documented separate approval.",
        "",
        "## Access, rollback and cost",
        "",
        "In the existing password-protected research app choose **Game Intelligence → Numerical game-script research**. Expand the forecast comparison and select a fixture/player. **Weekly Learning → Numerical challenger: weekly monitoring** shows prospective reports once games have settled. Current Top Picks and Top 2 remain champion-only.",
        "",
        "No new account, paid service, API subscription, hosting, database, dependency or billing feature was introduced. No bookmaker requests were made. Public nflverse sources and existing infrastructure were used. Original release/rollback pointers, production, main, Supabase, authentication and bankroll settings are unchanged. Rollback is the prior research code commit `7dd469e`; original certified bundles never need alteration.",
        "",
    ]
    (ROOT / "docs/NUMERICAL_GAME_SCRIPT.md").write_text("\n".join(lines))
    print(encoded(summary))


if __name__ == "__main__":
    main()
