"""Immutable captures, evidence-labelled reconciliation and guarded weekly learning."""

import hashlib
import itertools
import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import norm

from research_platform.inference_release import (
    resolve_research_release,
    validate_inference,
)
from stage1b.data import MARKETS

from .sources import permitted
from .store import ROOT, encoded, sha

POLICY = Path(__file__).with_name("policy.json")


def metrics(frame, prediction="projection"):
    e = frame[prediction] - frame.actual
    return {
        "n": len(frame),
        "mae": float(e.abs().mean()),
        "rmse": float(np.sqrt((e**2).mean())),
        "bias": float(e.mean()),
        "zero_outcomes": int(frame.actual.eq(0).sum()),
    }


def capture(store):
    now = pd.Timestamp(datetime.now(UTC))
    directory, release = resolve_research_release(ROOT)
    name = release["release_id"]
    target = store.root / "captures" / name
    if target.exists():
        store.validate(target)
        return target
    slate = pd.read_parquet(directory / "slate.parquet")
    when = pd.to_datetime(slate.prediction_at, utc=True)
    deadlines = slate.game_id.map(
        lambda g: pd.Timestamp(release["game_kickoffs"][g]) - pd.Timedelta(minutes=60)
    )
    if (when > now).any() or (now >= deadlines).any():
        raise ValueError(
            "Cannot claim genuine predecision capture: prediction future or cutoff passed"
        )
    document = {
        "release_id": name,
        "frozen_at": now.isoformat(),
        "capture_tier": "genuine_predecision_capture",
        "source_manifest_sha256": sha(directory / "manifest.json"),
        "models": release["models"],
        "game_kickoffs": release["game_kickoffs"],
        "complete_rows": int(slate.projection_status.eq("complete").sum()),
        "source_path": str(directory.relative_to(ROOT)),
    }
    context = ROOT / "experiments/sunday_script/20261120-v1/sunday_experimental.parquet"
    extra = {}
    context_manifest = context.parent / "manifest.json"
    if context.exists() and context_manifest.exists():
        cm = json.loads(context_manifest.read_text())
        report = json.loads((context.parent / "report.json").read_text())
        if report["source_release"] == name and cm["files"].get(context.name) == sha(
            context
        ):
            extra["experimental_context.parquet"] = context
            document["context_scope"] = (
                "Separate pregame experimental context; not a structural input to champion forecasts"
            )
    with store.transaction():
        return store.publish(
            "captures",
            name,
            copies={
                "forecasts.parquet": directory / "slate.parquet",
                "top_picks.parquet": directory / "top_picks.parquet",
                "release_manifest.json": directory / "manifest.json",
                **extra,
            },
            documents={"capture.json": document},
        )


def reconcile(forecasts, players, schedule, teams, as_of):
    as_of = pd.Timestamp(as_of)
    if (
        players.duplicated(["game_id", "player_id"]).any()
        or teams.duplicated(["game_id", "team"]).any()
    ):
        raise ValueError("Ambiguous outcome identity")
    lookup = players.set_index(["game_id", "player_id"])
    games = schedule.set_index("game_id")
    teamdata = teams.set_index(["game_id", "team"])
    rows = []
    forecast_lookup = {
        (r["game_id"], r["player_id"], r["market"]): r["projection"]
        for r in forecasts.to_dict("records")
    }
    for f in forecasts.to_dict("records"):
        r = {
            **f,
            "actual": np.nan,
            "error": np.nan,
            "status": "missing_player_observation",
            "evidence": [],
            "hypotheses": [],
            "attribution": "associative diagnostics; multiple explanations may apply",
            "team_context_scope": "Separate experimental benchmark, not proof of the champion's internal team expectation",
        }
        if f["game_id"] not in games.index:
            r["status"] = "missing_game"
            rows.append(r)
            continue
        game = games.loc[f["game_id"]]
        if pd.isna(game.completed_at) or pd.Timestamp(game.completed_at) >= as_of:
            r["status"] = "game_not_available"
            rows.append(r)
            continue
        if pd.Timestamp(f["prediction_at"]) >= pd.Timestamp(game.kickoff_at):
            raise ValueError("Forecast not before kickoff")
        r["actual_home_score"] = game.home_score
        r["actual_away_score"] = game.away_score
        r["completed_at"] = game.completed_at
        key = (f["game_id"], f["player_id"])
        if key not in lookup.index:
            rows.append(r)
            continue
        actual = lookup.loc[key]
        snap = actual.get("offense_pct", np.nan)
        r["actual_snap_share"] = snap
        for k in ["attempts", "carries", "targets", "receptions"]:
            r["actual_" + k] = actual.get(k, np.nan)
        if pd.isna(snap):
            r["status"] = "participation_unknown"
            rows.append(r)
            continue
        if snap <= 0:
            r["status"] = "no_offensive_snaps_not_proof_of_inactive_or_void"
            rows.append(r)
            continue
        if not bool(actual.get("stats_observed", False)):
            r["status"] = "missing_box_confirmed_participation"
            rows.append(r)
            continue
        target = MARKETS[f["market"]][0]
        outcome = actual.get(target, np.nan)
        if pd.isna(outcome):
            r["status"] = "missing_stat"
            rows.append(r)
            continue
        r.update(
            actual=float(outcome),
            error=float(f["projection"] - outcome),
            status="scored",
        )
        r["evidence"].append(
            "Observed offensive participation and recorded outcome; zero outcomes retained"
        )
        if (f["game_id"], f["team"]) in teamdata.index:
            t = teamdata.loc[(f["game_id"], f["team"])]
            for k in [
                "offensive_plays",
                "attempts",
                "carries",
                "receptions",
                "dropbacks",
                "lead_snap_fraction",
                "trail_snap_fraction",
            ]:
                r["actual_team_" + k] = t.get(k, np.nan)
            if np.isfinite(f.get("expected_attempts", np.nan)) and np.isfinite(
                f.get("expected_carries", np.nan)
            ):
                expected_pass = f["expected_attempts"]
                expected_run = f["expected_carries"]
                actual_pass = t.get("attempts", np.nan)
                actual_run = t.get("carries", np.nan)
                if (
                    np.isfinite([actual_pass, actual_run]).all()
                    and expected_pass + expected_run > 0
                    and actual_pass + actual_run > 0
                ):
                    r["pass_share_error"] = float(
                        actual_pass / (actual_pass + actual_run)
                        - expected_pass / (expected_pass + expected_run)
                    )
                    if abs(r["pass_share_error"]) > 0.1:
                        r["hypotheses"].append(
                            "Run/pass balance differed by more than 10 percentage points; not proof of a single cause"
                        )
                quantity = (
                    "carries"
                    if "rushing" in f["market"]
                    else "attempts"
                    if f["market"]
                    in ["passing_attempts", "completions", "passing_yards"]
                    else None
                )
                expected = expected_run if quantity == "carries" else expected_pass
                observed = t.get(quantity, np.nan) if quantity else np.nan
                if quantity and np.isfinite(observed) and expected > 0:
                    r["team_opportunity_relative_error"] = float(
                        observed / expected - 1
                    )
                    if abs(r["team_opportunity_relative_error"]) > 0.2:
                        r["hypotheses"].append(
                            "Team opportunity volume differed by more than 20%; pace/plays and balance may both contribute"
                        )
                    if f["market"] in [
                        "rushing_attempts",
                        "qb_rushing_attempts",
                        "passing_attempts",
                    ]:
                        implied_share = f["projection"] / expected
                        r["team_volume_component_actual_minus_forecast"] = float(
                            (observed - expected) * implied_share
                        )
                        r["player_share_component_actual_minus_forecast"] = float(
                            outcome - observed * implied_share
                        )
                        if (
                            observed > 0
                            and abs(outcome / observed - implied_share) > 0.1
                        ):
                            r["hypotheses"].append(
                                "Observed player share differed from the forecast-implied share; roster/role causes are unverified"
                            )
            if np.isfinite(f.get("expected_plays", np.nan)) and np.isfinite(
                t.get("offensive_plays", np.nan)
            ):
                r["team_play_count_error"] = float(
                    t.offensive_plays - f["expected_plays"]
                )
        if (
            np.isfinite(f.get("expected_snap_share", np.nan))
            and abs(snap - f["expected_snap_share"]) > 0.25
        ):
            r["hypotheses"].append(
                "Observed playing time changed materially; injury, coaching or availability cause is not established"
            )
        if all(k in f for k in ["p_trailing", "p_close", "p_leading"]):
            home = game.home_team == f["team"]
            margin = float(game.home_score - game.away_score) * (1 if home else -1)
            actual_state = 0 if margin < -7 else 2 if margin > 7 else 1
            probabilities = [f["p_trailing"], f["p_close"], f["p_leading"]]
            r["final_margin_state_brier"] = float(
                sum((probabilities[i] - int(i == actual_state)) ** 2 for i in range(3))
            )
            if int(np.argmax(probabilities)) != actual_state:
                r["hypotheses"].append(
                    "Experimental final-margin scenario missed; this is not a measured in-game state forecast"
                )
        usage = (
            "attempts"
            if f["market"] in ["passing_yards", "completions", "passing_attempts"]
            else "carries"
            if "rushing" in f["market"]
            else "receptions"
        )
        count_market = (
            "passing_attempts"
            if usage == "attempts"
            else (
                "qb_rushing_attempts"
                if f["market"].startswith("qb_")
                else "rushing_attempts"
            )
            if usage == "carries"
            else "receptions"
        )
        expected_count = forecast_lookup.get(
            (f["game_id"], f["player_id"], count_market)
        )
        observed_count = actual.get(usage, np.nan)
        if (
            expected_count is not None
            and expected_count > 0
            and np.isfinite(observed_count)
        ):
            efficiency = f["projection"] / expected_count
            r["opportunity_unit"] = usage
            r["opportunity_component_actual_minus_forecast"] = float(
                (observed_count - expected_count) * efficiency
            )
            r["efficiency_component_actual_minus_forecast"] = float(
                outcome - observed_count * efficiency
            )
            if abs(observed_count - expected_count) / expected_count > 0.25:
                r["hypotheses"].append(
                    "Player workload differed from the companion count forecast; team volume and player share can both explain it"
                )
        r["unattributed_statistical_error"] = r["error"]
        r["evidence"].append(
            "Error not explained causally; efficiency, sampling variation and missing context remain possible"
        )
        rows.append(r)
    frame = pd.DataFrame(rows)
    for c in ["evidence", "hypotheses"]:
        frame[c] = frame[c].map(lambda x: json.dumps(x))
    return frame


def summaries(frame):
    scored = frame[frame.status.eq("scored")]
    result = []
    for group in ["market", "team", "position"]:
        for value, g in scored.groupby(group):
            result.append({"group": group, "value": str(value), **metrics(g)})
    return result


def evaluate_candidate(store, policy):
    # Frozen previously inspected OOS data: diagnostic evidence, never fresh holdout.
    inputs = {
        str(path.relative_to(ROOT)): sha(path)
        for path in [
            ROOT / "experiments/stage1b/baseline-20261113-v5/forecasts.parquet",
            ROOT / "experiments/sunday_script/20261120-v1/player_replay.parquet",
            *sorted(
                (ROOT / "experiments/stage1b/baseline-20261113-v5/models").glob(
                    "*-2026.joblib"
                )
            ),
        ]
    }
    plan_sha = hashlib.sha256(
        (sha(POLICY) + sha(Path(__file__)) + encoded(inputs)).encode()
    ).hexdigest()
    block = store.reserve_holdout(policy["holdout"], plan_sha, fresh=False)
    saved = store.root / "candidates" / plan_sha[:20]
    if block["replay_only"]:
        if not saved.exists():
            raise ValueError(
                "Holdout already reserved without complete candidate record; manual recovery required"
            )
        store.validate(saved)
        result = json.loads((saved / "decision.json").read_text())
        result["holdout"]["replay_only"] = True
        return result
    archived = pd.read_parquet(
        ROOT / "experiments/stage1b/baseline-20261113-v5/forecasts.parquet"
    )
    held = pd.read_parquet(
        ROOT / "experiments/sunday_script/20261120-v1/player_replay.parquet"
    )
    if not held.season.eq(2026).all() or not held.week.between(1, 10).all():
        raise ValueError("Sealed or incorrect holdout")
    fit = archived[archived.season.isin(policy["fit_seasons"])]
    corrections = (fit.y - fit.projection).groupby(fit.market).mean() * 0.5
    out = []
    rng = np.random.default_rng(policy["seed"])
    for market, g in held.groupby("market"):
        g = g.copy()
        delta = float(corrections[market])
        g["candidate"] = g.projection + delta
        if MARKETS[market][3]:
            g["candidate"] = g.candidate.clip(lower=0)
        g["actual"] = g.y
        weekly = (
            g.assign(difference=(g.candidate - g.y).abs() - (g.projection - g.y).abs())
            .groupby("week")
            .difference.agg(["sum", "count"])
        )
        draw = rng.integers(
            0, len(weekly), (policy["bootstrap_replicates"], len(weekly))
        )
        samples = weekly["sum"].to_numpy()[draw].sum(axis=1) / weekly[
            "count"
        ].to_numpy()[draw].sum(axis=1)
        low, high = np.quantile(samples, [0.025, 0.975])
        signs = np.array(list(itertools.product([-1, 1], repeat=len(weekly))))
        null = signs @ weekly["sum"].to_numpy() / weekly["count"].sum()
        observed = weekly["sum"].sum() / weekly["count"].sum()
        pvalue = float(np.mean(null <= observed + 1e-12))
        model = joblib.load(
            ROOT
            / f"experiments/stage1b/baseline-20261113-v5/models/{market}-2026.joblib"
        )
        if (
            pd.Timestamp(model["model_information_available_at"])
            >= pd.to_datetime(g.prediction_at, utc=True).min()
        ):
            raise ValueError("Historical baseline availability failure")
        sigma = float(model["distributions"]["stage1a_normal"].in_sample_scale)
        line = np.floor(np.maximum(g.projection, 0)) + 0.5
        truth = g.y.gt(line).astype(int).to_numpy()
        scores = {}
        for label, mu in [("baseline", g.projection), ("candidate", g.candidate)]:
            prob = np.clip(norm.sf(line, mu, sigma), 1e-6, 1 - 1e-6)
            scores[label] = {
                "brier": float(np.mean((prob - truth) ** 2)),
                "log_loss": float(
                    np.mean(-truth * np.log(prob) - (1 - truth) * np.log1p(-prob))
                ),
            }
        before = metrics(g)
        after = metrics(g, "candidate")
        out.append(
            {
                "market": market,
                "correction": delta,
                "baseline": before,
                "candidate": after,
                "relative_mae_gain": 1 - after["mae"] / before["mae"],
                "paired_week_bootstrap95": [float(low), float(high)],
                "one_sided_bootstrap_p": pvalue,
                "weeks": int(g.week.nunique()),
                "probability_scores": scores,
                "probability_scope": "Hypothetical half-lines; normal-tail diagnostic with pre-2026 residual scale, not bookmaker returns or validated calibration",
            }
        )
    active = True
    for rank, row in enumerate(sorted(out, key=lambda r: r["one_sided_bootstrap_p"])):
        passed = row["one_sided_bootstrap_p"] <= policy["familywise_alpha"] / (
            len(out) - rank
        )
        active = active and passed
        row["holm_rejects_no_improvement"] = bool(active)
    primary = next(r for r in out if r["market"] == "passing_yards")
    probability_gate = all(
        r["probability_scores"]["candidate"]["brier"]
        <= r["probability_scores"]["baseline"]["brier"]
        and r["probability_scores"]["candidate"]["log_loss"]
        <= r["probability_scores"]["baseline"]["log_loss"]
        for r in out
    )
    statistical = (
        probability_gate
        and primary["paired_week_bootstrap95"][1] < 0
        and (
            primary["relative_mae_gain"] >= policy["minimum_mae_gain"]
            and primary["holm_rejects_no_improvement"]
            and all(
                r["relative_mae_gain"] >= -policy["maximum_market_mae_regression"]
                and r["candidate"]["rmse"]
                <= r["baseline"]["rmse"] * (1 + policy["maximum_market_mae_regression"])
                for r in out
            )
            and all(
                r["weeks"] >= policy["minimum_holdout_weeks"]
                and r["baseline"]["n"] >= policy["minimum_market_rows"]
                for r in out
            )
        )
    )
    result = {
        "candidate": policy["candidate"],
        "fit_seasons": policy["fit_seasons"],
        "holdout": block,
        "markets": out,
        "statistical_gate": bool(statistical),
        "probability_gate": bool(probability_gate),
        "accepted": False,
        "decision": "RETAIN_CHAMPION",
        "reasons": [
            "Previously inspected holdout is not fresh independent evidence",
            "Historical baseline is an archived chronological proxy, not the live frozen champion weights",
            "No certified compatible challenger release or exact-replay promotion certificate",
        ],
        "fresh_holdout_required": True,
        "plan_sha256": plan_sha,
        "inputs": inputs,
        "sign_test_assumptions": "Paired week-cluster sign randomisation; requires exchangeable signs across weeks. Temporal dependence and reused development data preclude confirmatory interpretation.",
    }
    store.publish("candidates", plan_sha[:20], documents={"decision.json": result})
    return result


def next_slate(store, policy, target_week=None):
    if target_week is not None:
        try:
            permitted(2026, target_week - 1, policy)
        except ValueError as e:
            return {
                "status": "blocked",
                "target_week": target_week,
                "reason": str(e),
                "champion_retained": True,
            }
    directory, release = resolve_research_release(ROOT)
    now = pd.Timestamp.now(tz="UTC")
    week = release["fixture_slate"]["week"]
    if target_week is not None and week != target_week:
        return {
            "status": "blocked",
            "target_week": target_week,
            "reason": "No certified current bundle for requested week; never relabel a stale slate",
            "champion_retained": True,
        }
    if not any(
        now < pd.Timestamp(t) - pd.Timedelta(minutes=60)
        for t in release["game_kickoffs"].values()
    ):
        return {
            "status": "blocked",
            "reason": "Certified slate has no upcoming predecision fixtures",
            "champion_retained": True,
        }
    check = validate_inference(directory, ROOT, replay=True)
    from research_platform.slate import model_candidates, top_two

    slate = pd.read_parquet(directory / "slate.parquet")
    models = model_candidates(slate, release, now)
    pairs = top_two([], models, release)
    return {
        "status": "certified_existing_bundle_replayed",
        "week": week,
        "release_id": release["release_id"],
        "new_forecasts_generated": False,
        "checks": check,
        "top_two_rows": sum(len(v) for v in pairs.values()),
        "manifest_sha256": sha(directory / "manifest.json"),
        "source_path": str(directory.relative_to(ROOT)),
        "champion_retained": True,
    }


def dry_run(store, week=9, cycle_id="2026-w09-dryrun-v1"):
    policy = json.loads(POLICY.read_text())
    permitted(2026, week, policy)
    existing = store.root / "cycles" / cycle_id
    if existing.exists():
        store.validate(existing)
        return existing
    directory, release = resolve_research_release(ROOT)
    features = pd.read_parquet(
        directory / "features.parquet",
        filters=[("season", "==", 2026), ("week", "<=", 10)],
    )
    from scripts.forecast_features import schedule_times

    schedule = schedule_times(
        pd.read_parquet(
            directory / "schedule.parquet",
            filters=[("season", "==", 2026), ("week", "<=", 10)],
        )
    )
    history = pd.read_parquet(
        ROOT / "experiments/sunday_script/20261120-v1/player_replay.parquet"
    )
    forecasts = history[history.week.eq(week)].drop(columns=["y", "adjusted"]).copy()
    identity = features[
        ["player_id", "game_id", "position", "offense_pct_last3_avg"]
    ].rename(columns={"offense_pct_last3_avg": "expected_snap_share"})
    forecasts = forecasts.merge(
        identity, on=["player_id", "game_id"], validate="many_to_one"
    )
    forecasts["capture_tier"] = "retrospective_archived_predictions_NOT_prospective"
    forecasts["baseline_version"] = "stage1b-chronological-2026"
    teams = (
        features.groupby(["game_id", "team"], as_index=False)[
            ["team_total_attempts", "team_total_carries", "team_total_receptions"]
        ]
        .first()
        .rename(
            columns={
                "team_total_attempts": "attempts",
                "team_total_carries": "carries",
                "team_total_receptions": "receptions",
            }
        )
    )
    recorded = pd.read_parquet(
        ROOT / "research_inputs/stage1c/public-20261113-v3/team_games.parquet"
    )
    teams = teams.merge(
        recorded[["game_id", "team", "plays", "dropbacks"]],
        on=["game_id", "team"],
        how="left",
        validate="one_to_one",
    ).rename(columns={"plays": "offensive_plays"})
    pbp = Path("/tmp/sunday-research/pbp2026.parquet")
    pbp_source = None
    if pbp.exists():
        play = pd.read_parquet(
            pbp,
            columns=["game_id", "posteam", "play_type", "score_differential"],
            filters=[("season", "==", 2026), ("week", "==", week)],
        )
        play = play[
            play.play_type.isin(["run", "pass"])
            & play.posteam.notna()
            & play.score_differential.notna()
        ].copy()
        play["lead_snap_fraction"] = play.score_differential.gt(0).astype(float)
        play["trail_snap_fraction"] = play.score_differential.lt(0).astype(float)
        state = (
            play.groupby(["game_id", "posteam"], as_index=False)[
                ["lead_snap_fraction", "trail_snap_fraction"]
            ]
            .mean()
            .rename(columns={"posteam": "team"})
        )
        teams = teams.merge(
            state, on=["game_id", "team"], how="left", validate="one_to_one"
        )
        pbp_source = {
            "tier": "retrospective locally cached public PBP; original retrieval time not established",
            "sha256": sha(pbp),
        }
    # Original player forecast capture and reconciliation stay separate forever.
    with store.transaction():
        archived = store.root / "historical_captures" / f"2026-w{week:02d}"
        if not archived.exists():
            store.publish(
                "historical_captures",
                f"2026-w{week:02d}",
                frames={
                    "forecasts.parquet": forecasts,
                    "team_results.parquet": teams[
                        teams.game_id.isin(forecasts.game_id)
                    ],
                },
                documents={
                    "capture.json": {
                        "tier": "retrospective_replay_NOT_genuine_predecision",
                        "archived_source_sha256": sha(
                            ROOT
                            / "experiments/sunday_script/20261120-v1/player_replay.parquet"
                        ),
                        "created_at": datetime.now(UTC).isoformat(),
                        "observed_game_state_source": pbp_source,
                    }
                },
            )
        reconciled = reconcile(
            forecasts, features, schedule, teams, pd.Timestamp.now(tz="UTC")
        )
        decision = evaluate_candidate(store, policy)
        prepared = next_slate(store, policy)
        next12 = next_slate(store, policy, target_week=12)
        report = {
            "schema": 1,
            "cycle_id": cycle_id,
            "completed_at": datetime.now(UTC).isoformat(),
            "mode": "historical_dry_run",
            "week": week,
            "champion_release": release["model_parent"]["release_id"],
            "champion_models": release["models"],
            "forecast_capture_tier": "retrospective_replay_not_genuine_predecision",
            "status_counts": reconciled.status.value_counts().to_dict(),
            "metrics": summaries(reconciled),
            "candidate": decision,
            "next_slate": prepared,
            "week12_readiness": next12,
            "game_script_scope": "Experimental final-margin category Brier, not in-game lead/trail occupancy",
            "game_script_brier": float(
                reconciled.drop_duplicates(
                    ["game_id", "team"]
                ).final_margin_state_brier.mean()
            ),
            "source_manifest_sha256": sha(directory / "manifest.json"),
            "forecast_sha256": sha(archived / "forecasts.parquet"),
            "code_sha256": {
                str(p.relative_to(ROOT)): sha(p)
                for p in sorted(Path(__file__).parent.glob("*.py"))
            },
            "data_gaps": [
                "Injury cause and game-day inactive/void status are not inferred from snap absence",
                "At-snap states are recorded where cached PBP is available; final-margin scenario probabilities target a different outcome",
                "Team/script expectations are separate experimental context, not champion structural inputs",
                "Historical source publication timestamps and archived pregame roster availability unverified",
            ],
        }
        result = store.publish(
            "cycles",
            cycle_id,
            frames={"reconciled.parquet": reconciled},
            documents={"report.json": report, "policy.json": policy},
        )
    return result
