"""One preregistered chronological numerical experiment, isolated from releases."""

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd

from weekly_learning.store import ROOT, encoded, sha

from .data import PROTOCOL, collect, player_source, team_panel
from .metrics import attribution, player_metrics, point, selection, team_metrics
from .models import chronological_team
from .players import (
    allocation_folds,
    champion_replay,
    correction_folds,
    innovations,
    player_histories,
)

DEFAULT = ROOT / "experiments/script_adjustment/numerical-20261121-v5"
INPUT = ROOT / "research_inputs/script_adjustment/pbp-20261121-v2"


def run(output=DEFAULT, work=Path("/tmp/script-adjustment-work-v4")):
    output, work = Path(output), Path(work)
    if output.exists():
        raise ValueError("Immutable experiment exists; verify/replay it instead")
    work.mkdir(parents=True, exist_ok=True)
    p = json.loads(PROTOCOL.read_text())
    started = datetime.now(UTC).isoformat()
    collect(INPUT)
    cells = pd.read_parquet(INPUT / "cells.parquet")
    games = pd.read_parquet(INPUT / "games.parquet")
    panel = team_panel(games, cells)
    if (work / "teams.parquet").exists():
        teams = pd.read_parquet(work / "teams.parquet")
        team_models = joblib.load(work / "team_models.joblib")
    else:
        teams, team_models = chronological_team(panel, cells)
        teams.to_parquet(work / "teams.parquet", index=False)
        joblib.dump(team_models, work / "team_models.joblib")
    path, source = player_source()
    if (work / "baseline.parquet").exists():
        baseline = pd.read_parquet(work / "baseline.parquet")
    elif Path("/tmp/script-player-baseline.parquet").exists():
        baseline = pd.read_parquet("/tmp/script-player-baseline.parquet")
        baseline.to_parquet(work / "baseline.parquet", index=False)
    else:
        baseline = champion_replay(source, "/tmp/script-backbone-cache-v1")
        baseline.to_parquet(work / "baseline.parquet", index=False)
    if (work / "player_history.parquet").exists():
        history = pd.read_parquet(work / "player_history.parquet")
    else:
        history = player_histories(
            source, fixtures=panel[["game_id", "team", "season", "week", "kickoff_at"]]
        )
        history.to_parquet(work / "player_history.parquet", index=False)
    allocation, coherence, share_models = allocation_folds(history, teams)
    frame = innovations(baseline, allocation)
    adjusted, correction_models = correction_folds(frame, p)
    metrics, reliability = player_metrics(adjusted)
    tm, tr = team_metrics(teams)
    options, chosen = selection(adjusted, p)
    official = source.groupby(["game_id", "team"], as_index=False)[
        ["team_total_attempts", "team_total_carries"]
    ].first()
    reconciliation = teams[
        ["game_id", "team", "season", "week", "attempts", "carries"]
    ].merge(official, on=["game_id", "team"], validate="one_to_one")
    reconciliation["attempt_difference"] = (
        reconciliation.attempts - reconciliation.team_total_attempts
    )
    reconciliation["carry_difference"] = (
        reconciliation.carries - reconciliation.team_total_carries
    )
    cohorts = []
    for (market, year, pos), g in adjusted.groupby(["market", "season", "position"]):
        cohorts.append(
            {
                "market": market,
                "season": int(year),
                "position": pos,
                "n": len(g),
                "baseline_mae": point(g.y, g.baseline)["mae"],
                "adjusted_mae": point(g.y, g.adjusted)["mae"],
            }
        )
    opp = []
    for (year, cat), g in allocation.groupby(["season", "category"]):
        scored = g[
            g.stats_observed.eq(True)
            & g.offense_pct.gt(0)
            & g.actual_opportunities.notna()
        ]
        opp.append(
            {
                "season": int(year),
                "category": cat,
                "n": len(scored),
                "baseline": point(
                    scored.actual_opportunities, scored.prior_opportunities
                ),
                "allocated": point(
                    scored.actual_opportunities, scored.allocated_opportunities
                ),
            }
        )
    report = {
        "schema": 1,
        "protocol_version": p["version"],
        "activation": False,
        "champion_retained": True,
        "promotion_passed": False,
        "promotion_reasons": [
            "No genuinely untouched final period has been evaluated; 2025 and2026w1-10 have been inspected previously",
            "Current-year frozen live weights cannot honestly be backtested against their own training games; historical replicas are explicitly distinguished",
            "Original probability/pricing method is unchanged; adjusted player distributions not certified",
        ],
        "selection": chosen,
        "all_scale_tests": options,
        "team_opportunity_reconciliation": {
            "team_games": len(reconciliation),
            "attempt_mismatch": int(reconciliation.attempt_difference.ne(0).sum()),
            "carry_mismatch": int(reconciliation.carry_difference.ne(0).sum()),
            "handling": "No corrections or fabricated opportunities; discrepancies remain explicit",
        },
        "allocation": {
            "max_capacity_excess": float((-coherence.unassigned).clip(lower=0).max()),
            "mean_unassigned_fraction": float(
                (coherence.unassigned / coherence.capacity).mean()
            ),
            "historical_rosters_verified": False,
        },
        "sample": {
            "player_market_rows": len(adjusted),
            "adjusted_rows": int(adjusted.delta.ne(0).sum()),
            "team_games": len(teams),
            "games": int(teams.game_id.nunique()),
            "by_season": {
                str(k): int(v) for k, v in adjusted.groupby("season").size().items()
            },
            "zeros": int(adjusted.y.eq(0).sum()),
        },
        "opportunity_metrics": opp,
        "probability_scope": "Win and clock/score occupancy are genuine probabilistic predictions; player half-line/interval measures are assumption-sensitive constant-scale normal diagnostics only, not bookmaker backtests or certified adjusted pricing",
        "historical_scope": "Current corrected retrospective data,36h availability proxy, no historical publication/roster archive; missing context stays baseline on identical populations",
        "week12_status": "Early team-only preview allowed; player candidate awaits authorised settlement, fresh roster/depth and v2 certification; no stale eligibility reuse",
        "next_validation": "Freeze prospective overlays before T-60 and collect admitted results without selecting/refitting on the sealed benchmark period",
    }
    selection_rows = []
    for market, g in adjusted[adjusted.season.eq(2025)].groupby("market"):
        c = chosen[market]
        pred = g.baseline + c["scale"] * g.delta
        before = point(g.y, g.baseline)
        after = point(g.y, pred)
        risk = after["rmse"] <= before["rmse"] * (
            1 + p["maximum_market_regression"]
        ) and after["mae"] <= before["mae"] * (1 + p["maximum_market_regression"])
        c["error_guard_passed"] = bool(risk)
        probs = metrics[(metrics.market == market) & (metrics.season == 2025)].iloc[0]
        c["unit_scale_probability_guard_passed"] = bool(
            probs.adjusted_brier
            <= probs.baseline_brier * (1 + p["maximum_market_regression"])
            and probs.adjusted_log_loss
            <= probs.baseline_log_loss * (1 + p["maximum_market_regression"])
        )
        c["eligible_scale"] = (
            c["scale"]
            if c["selection_gate_passed"]
            and risk
            and c["unit_scale_probability_guard_passed"]
            else 0
        )
        selection_rows.append(
            {
                "market": market,
                "scale": c["scale"],
                **{"baseline_" + k: v for k, v in before.items()},
                **{"adjusted_" + k: v for k, v in after.items()},
                "eligible_scale": c["eligible_scale"],
            }
        )
    report["retrospective_markets_passing_selection"] = [
        m for m, c in chosen.items() if c["eligible_scale"] > 0
    ]
    report["promotion_reasons"] += [
        "Selected scale for failed markets is zero; raw unit-scale adjustments remain experimental for full reporting"
    ]
    ablations = []
    for name, columns in [
        (
            "team_volume_state_only",
            ["volume_effect", "state_effect", "mobility_effect"],
        ),
        ("player_share_only", ["share_effect"]),
        ("efficiency_only", ["efficiency_effect"]),
    ]:
        comparison, _ = correction_folds(frame, p, columns)
        measures, _ = player_metrics(comparison)
        measures["ablation"] = name
        ablations.append(measures)
    combined_metrics = metrics.copy()
    combined_metrics["ablation"] = "combined"
    ablations.append(combined_metrics)
    final = attribution(adjusted)
    output.mkdir(parents=True)
    frames = {
        "player_replay.parquet": final,
        "team_replay.parquet": teams,
        "metrics.parquet": metrics,
        "player_reliability.parquet": reliability,
        "team_metrics.parquet": tm,
        "team_reliability.parquet": tr,
        "allocation_coherence.parquet": coherence,
        "opportunity_reconciliation.parquet": reconciliation,
        "cohorts.parquet": pd.DataFrame(cohorts),
        "selection_metrics.parquet": pd.DataFrame(selection_rows),
        "ablations.parquet": pd.concat(ablations, ignore_index=True),
        "share_inputs.parquet": history,
        "allocation_predictions.parquet": allocation[
            [
                "game_id",
                "player_id",
                "category",
                "season",
                "predicted_share",
                "allocated_opportunities",
            ]
        ],
    }
    for name, f in frames.items():
        f.to_parquet(output / name, index=False)
    (output / "report.json").write_text(encoded(report))
    joblib.dump(
        {
            "team": team_models[2026],
            "shares": share_models[2026],
            "corrections": {
                m: b for (m, y), b in correction_models.items() if y == 2026
            },
            "protocol": p,
            "selection": chosen,
            "experiment_build_started_at": started,
            "artifact_created_at": datetime.now(UTC).isoformat(),
            "simulated_fit_before": "2026 season opener; all target seasons<=2025",
        },
        output / "challenger.joblib",
    )
    joblib.dump(
        {
            "teams": team_models,
            "shares": share_models,
            "corrections": correction_models,
        },
        output / "replay_models.joblib",
    )
    models_dir = output / "chronological_backbones"
    models_dir.mkdir()
    for file in Path("/tmp/script-backbone-cache-v1").glob("*.joblib"):
        shutil.copyfile(file, models_dir / file.name)
    from .preview import build_previews

    build_previews(output, panel, cells, source)
    from release_utils import MODEL_NAMES, resolve_release, runtime_versions

    champion_data, champion_manifest = resolve_release(ROOT)
    from .validate import REPLAY_POLICY

    manifest = {
        "numerical_replay_policy": REPLAY_POLICY,
        "schema": 1,
        "runtime": runtime_versions(ROOT),
        "champion_release_id": champion_manifest["release_id"],
        "champion_models": {
            m: sha(champion_data / ("model_" + m + ".joblib")) for m in MODEL_NAMES
        },
        "status": "experimental_not_promoted",
        "started_at": started,
        "created_at": datetime.now(UTC).isoformat(),
        "preregistration_commit": "e0fb606",
        "protocol_sha256": sha(PROTOCOL),
        "input_bundle": str(INPUT.relative_to(ROOT)),
        "input_manifest_sha256": sha(INPUT / "manifest.json"),
        "player_source": str(path.relative_to(ROOT)),
        "player_source_sha256": sha(path),
        "source_sha256": {
            str(f.relative_to(ROOT)): sha(f)
            for f in (ROOT / "script_adjustment").glob("*.py")
        },
        "files": {
            str(f.relative_to(output)): sha(f) for f in output.rglob("*") if f.is_file()
        },
        "final_period_sealed": True,
        "models_retrained_in_place": False,
        "production_changed": False,
    }
    (output / "manifest.json").write_text(encoded(manifest))
    print(
        encoded(
            {
                "output": str(output),
                "sample": report["sample"],
                "promotion_passed": False,
                "passing_selection": report["retrospective_markets_passing_selection"],
            }
        ),
        flush=True,
    )
    return output


def assemble_checkpoint(previous, output=DEFAULT):
    """Reuse frozen fitted weights after integration/replay portability changes.

    This is a new experimental build, never an edit of a certified release.
    Statistical model/input drift requires a genuine rebuilt experiment instead.
    Validator changes require explicit policy metadata and full numerical replay;
    this never changes the original release validator or fitted payload.
    """
    previous, output = Path(previous), Path(output)
    old = json.loads((previous / "manifest.json").read_text())
    permitted_changes = {
        "script_adjustment/runner.py",
        "script_adjustment/weekly.py",
        "script_adjustment/validate.py",
    }
    for name, digest in old["source_sha256"].items():
        if name not in permitted_changes and sha(ROOT / name) != digest:
            raise ValueError("Statistical source changed; rebuild required: " + name)
    if old["protocol_sha256"] != sha(PROTOCOL):
        raise ValueError("Protocol changed; checkpoint cannot be reused")
    from .validate import replay_payload

    replay_payload(previous)
    from .validate import REPLAY_POLICY

    old["numerical_replay_policy"] = REPLAY_POLICY
    if output.exists():
        raise ValueError("Immutable assembled output already exists")
    shutil.copytree(previous, output)
    old["assembled_from_manifest_sha256"] = sha(previous / "manifest.json")
    old["assembly_note"] = (
        "Unchanged fitted numerical payload; explicit absolute-only 1e-10 CPU-portable experimental replay policy. Artifact and model bytes remain identical to parent; original champion baseline copied bitwise. No refit, retuning or new evaluation period."
    )
    old["created_at"] = datetime.now(UTC).isoformat()
    old["source_sha256"] = {
        str(f.relative_to(ROOT)): sha(f)
        for f in (ROOT / "script_adjustment").glob("*.py")
    }
    (output / "manifest.json").write_text(encoded(old))
    from .validate import validate

    return validate(output, replay=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT)
    parser.add_argument(
        "--work", type=Path, default=Path("/tmp/script-adjustment-work-v4")
    )
    args = parser.parse_args()
    run(args.output, args.work)
