"""Research selection admission over immutable, chronologically evaluated forecasts.

No fitting, results retrieval, bookmaker calls, production pointers or ledger writes.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from season_intelligence.data import CERTIFIED, market_data
from season_intelligence.experiment import DEFAULT as EXPERIMENT
from season_intelligence.probability import normal_price, quoted_value
from season_intelligence.validate import validate as validate_experiment
from stage1b.data import MARKETS
from weekly_learning.store import ROOT, encoded, sha

DIRECTORY = ROOT / "research_selection_releases/enhanced-sunday-20261121-v1"


def number(value):
    try:
        return float(value) if np.isfinite(float(value)) else None
    except (TypeError, ValueError):
        return None


def policy():
    return {
        "research_only": True,
        "certified_promotion": False,
        "target_date": "2026-11-22",
        "week_from_verified_schedule": 11,
        "minimum_history": 3,
        "point_admission": "2025 preregistered point gate and positive2026 inspected diagnostic MAE gain",
        "probability_admission": "2025 probability gate, positive2026 Brier/log-loss improvement and positive week-block log-loss lower bound",
        "ordering_weights": {
            "calibration": 0.2,
            "role_stability": 0.2,
            "relative_interval": 0.2,
            "snap_share": 0.2,
            "history_capped20": 0.2,
        },
        "ranking_index_is_not_a_probability_or_confidence_score": True,
        "ordering": [
            "point_and_probability_support",
            "2025 calibration gap",
            "recent role stability",
            "relative outcome interval width",
            "history size",
            "player identity",
        ],
        "no_ev_ranking_without_quote": True,
        "minimum_validated_research_line": 0.5,
        "point_target": "typical outcome (median-like), not a validated distribution mean",
        "no_failed_game_script_adjustment": True,
        "historical_timing": "Retrospective; champion closing-total availability specifically atT-60 is unverified",
    }


def stable_order(frame):
    d = frame.copy()
    if d.empty:
        return d
    markets = (
        d[["market", "calibration_gap"]]
        .drop_duplicates("market")
        .set_index("market")
        .calibration_gap.rank(pct=True)
    )
    d["ordering_calibration"] = d.market.map(markets)
    d["ordering_role"] = d.role_variability.fillna(99).rank(pct=True)
    d["ordering_interval"] = d.relative_width.fillna(float("inf")).rank(pct=True)
    d["ordering_snaps"] = d.recent_snap_share.fillna(0).rank(pct=True, ascending=False)
    d["ordering_history"] = d.history_n.clip(upper=20).rank(pct=True, ascending=False)
    d["priority_order"] = d[
        [
            "ordering_calibration",
            "ordering_role",
            "ordering_interval",
            "ordering_snaps",
            "ordering_history",
        ]
    ].mean(axis=1)
    return d.sort_values(
        ["support_tier", "priority_order", "player", "market"],
        ascending=[False, True, True, True],
        kind="stable",
    )


def eligible_rows(frame, now):
    now = pd.Timestamp(now)
    return frame[
        pd.to_datetime(frame.kickoff_at, utc=True).gt(now + pd.Timedelta(minutes=60))
        & pd.to_datetime(frame.selection_built_at, utc=True).le(now)
    ].copy()


def select(frame, limit=12):
    # Positive recent offensive involvement is evidence, never a same-game filter.
    candidates = frame[
        frame.history_n.ge(3)
        & frame.recent_snap_share.gt(0)
        & frame.recent_opportunities.gt(0)
        & frame.enhanced_projection.notna()
    ].copy()
    ranked = stable_order(candidates)
    top = ranked.drop_duplicates("player_id").head(limit).copy()
    top["research_rank"] = np.arange(1, len(top) + 1)
    two = (
        ranked.drop_duplicates(["game_id", "player_id"])
        .groupby("game_id", sort=False)
        .head(2)
        .copy()
    )
    two["game_rank"] = two.groupby("game_id").cumcount() + 1
    return top, two


def explain(r):
    _, _, opportunity, _ = MARKETS[r["market"]]
    label = {"attempts": "pass attempts", "carries": "carries", "targets": "targets"}[
        opportunity
    ]
    units = {
        "passing_yards": "passing yards",
        "rushing_yards": "rushing yards",
        "qb_rushing_yards": "rushing yards",
        "receiving_yards": "receiving yards",
        "passing_attempts": "pass attempts",
        "qb_rushing_attempts": "carries",
        "rushing_attempts": "carries",
        "receptions": "catches",
        "completions": "completions",
    }[r["market"]]
    recent = number(r.get("last3"))
    five = number(r.get("last5"))
    work = number(r.get("recent_opportunities"))
    season = number(r.get("season_mean"))
    snaps = number(r.get("recent_snap_share"))
    sentences = []
    if recent is not None:
        sentences.append(
            f"{r['player']} averaged {recent:.1f} {units} in his last three appearances"
            + (
                f", compared with {five:.1f} over his last five"
                if five is not None
                else ""
            )
            + "."
        )
    usage = []
    if work is not None:
        usage.append(f"{work:.1f} {label} per game")
    if snaps is not None:
        usage.append(f"{snaps:.0%} of the offensive snaps")
    if usage:
        trend = ""
        old = number(r.get("workload5"))
        if old is not None and work is not None and abs(work - old) >= 0.5:
            trend = f"; that workload is {'up' if work > old else 'down'} from {old:.1f} {label} over five games"
        sentences.append("His recent workload is " + " and ".join(usage) + trend + ".")
    allowed = number(
        r.get(
            "opponent_carries_allowed"
            if opportunity == "carries"
            else "opponent_attempts_allowed"
        )
    )
    kind = "carries" if opportunity == "carries" else "pass attempts"
    own = number(r.get("team_recent_plays"))
    if allowed is not None:
        sentences.append(
            f"{r['opponent']} faced {allowed:.1f} opponent {kind} per game over the available prior eight games"
            + (
                f", while {r['team']} averaged {own:.1f} offensive plays"
                if own is not None
                else ""
            )
            + "."
        )
    sentences.append(
        f"The {'updated research' if r['point_admitted'] else 'retained baseline'} projection is {r['enhanced_projection']:.1f} {units}"
        + (
            f", versus {r['baseline']:.1f} originally"
            if r["point_admitted"]
            else "; the alternative did not earn a point-forecast upgrade"
        )
        + "."
    )
    risk = []
    cv = number(r.get("role_variability"))
    if cv is not None and cv >= 0.5:
        risk.append("His recent workload has varied substantially")
    if r.get("probability_mode") == "unavailable":
        risk.append(
            "the improved point forecast has not established a reliable new over/under price"
        )
    if opportunity in ["attempts", "targets"]:
        risk.append(
            "a lead could reduce passing work; that game script is not established"
        )
    else:
        risk.append(
            "falling behind could reduce carries; that game script is not established"
        )
    if (
        season is not None
        and recent is not None
        and abs(recent - season) > max(1, abs(season) * 0.2)
    ):
        risk.append(f"his {season:.1f} season average differs from the recent run")
    return " ".join(sentences), " · ".join(risk) + "."


def positive_line_evidence(predictions):
    """Price-domain robustness: no credit from trivial negative illustrative lines."""
    selected = predictions[predictions.hypothetical_line.ge(0.5)]
    rows = []
    for (market, year), g in selected.groupby(["market", "season"]):
        a = g[g.method.eq("champion_normal")]
        b = g[g.method.eq("research_empirical")]
        aw = a.groupby("week").log_loss.mean()
        bw = b.groupby("week").log_loss.mean()
        diff = (aw - bw).dropna().to_numpy()
        blocks = np.array([diff[i : i + 2].mean() for i in range(0, len(diff), 2)])
        rng = np.random.default_rng(221126)
        draws = rng.choice(blocks, (1000, len(blocks)), replace=True).mean(axis=1)

        def gap(d):
            bands = pd.cut(d.p_over, np.linspace(0, 1, 11), include_lowest=True)
            table = d.groupby(bands, observed=True).agg(
                p=("p_over", "mean"), y=("observed_over", "mean"), n=("p_over", "size")
            )
            return float((abs(table.p - table.y) * table.n).sum() / table.n.sum())

        rows.append(
            {
                "market": market,
                "season": int(year),
                "positive_line_observations": len(b),
                "baseline_log_loss": float(a.log_loss.mean()),
                "research_log_loss": float(b.log_loss.mean()),
                "log_loss_gain": float(1 - b.log_loss.mean() / a.log_loss.mean()),
                "baseline_brier": float(a.brier.mean()),
                "research_brier": float(b.brier.mean()),
                "baseline_calibration_gap": gap(a),
                "research_calibration_gap": gap(b),
                "weekly_log_loss_improvement_low95": float(np.quantile(draws, 0.025)),
                "weekly_log_loss_improvement_high95": float(np.quantile(draws, 0.975)),
                "scope": "positive hypothetical lines only; inspected retrospective evidence, not bookmaker ROI",
            }
        )
    return pd.DataFrame(rows)


def build(output=DIRECTORY):
    output = Path(output)
    if output.exists():
        raise ValueError("Immutable research selection bundle exists")
    validate_experiment(EXPERIMENT, replay=True)
    original = json.loads((CERTIFIED / "manifest.json").read_text())
    choices = json.loads((EXPERIMENT / "selection.json").read_text())
    frame = pd.read_parquet(EXPERIMENT / "sunday_forecasts.parquet")
    states = pd.read_parquet(EXPERIMENT / "sunday_feature_states.parquet")
    fitted = joblib.load(EXPERIMENT / "sunday_models.joblib")
    point = pd.read_csv(EXPERIMENT / "point_metrics.csv")
    positive = positive_line_evidence(
        pd.read_parquet(EXPERIMENT / "probability_predictions.parquet")
    )
    original_slate = pd.read_parquet(CERTIFIED / "slate.parquet")
    from scripts.build_slate import MARKETS as LABELS

    original_slate["market"] = original_slate.market.map(
        {v: k for k, v in LABELS.items()}
    )
    sigma = original_slate[["game_id", "player_id", "market", "resid_std"]]
    frame = frame.merge(
        sigma, on=["game_id", "player_id", "market"], validate="one_to_one"
    )
    now = pd.Timestamp(datetime.now(UTC))
    rows = []
    sensitivities = []
    for market, g in frame.groupby("market", sort=False):
        c = choices[market]
        p = point[point.market.eq(market) & point.season.eq(2026)].set_index("method")
        method = c["research_point_method"]
        point_gain = float(1 - p.loc[method, "mae"] / p.loc["baseline", "mae"])
        admitted = bool(c["retrospective_point_gate"] and point_gain > 0)
        evidence = positive[positive.market.eq(market)].set_index("season")
        prior = evidence.loc[2025]
        later = evidence.loc[2026]
        prob = bool(
            c["retrospective_probability_gate"]
            and prior.log_loss_gain >= 0.02
            and prior.research_brier <= prior.baseline_brier
            and later.log_loss_gain > 0
            and later.research_brier < later.baseline_brier
            and later.weekly_log_loss_improvement_low95 > 0
        )
        mode = "empirical" if prob else "unavailable" if admitted else "original_normal"
        gap = float(
            prior.research_calibration_gap if prob else prior.baseline_calibration_gap
        )
        state = market_data(states, market)
        x = g[["game_id", "player_id"]].merge(
            state, on=["game_id", "player_id"], validate="one_to_one"
        )
        model = fitted["points"][market]
        candidate = model.predict(x)
        np.testing.assert_allclose(candidate, g.enhanced_candidate, rtol=0, atol=1e-10)
        medians = (
            dict(zip(model.columns, model.model.steps[0][1].statistics_))
            if hasattr(model, "model")
            else {}
        )
        groups = {
            "recent production and workload": [
                a
                for a in model.columns
                if any(s in a for s in ["_last3", "_last5", "_career", "_season"])
                and "share" not in a
                and not a.startswith("offense_pct")
            ],
            "playing time and workload share": [
                a
                for a in model.columns
                if "share" in a or "snap" in a or a.startswith("offense_pct")
            ],
            "opponent opportunity history": [
                a for a in model.columns if a.startswith("opp_")
            ],
            "team volume and pace": [a for a in model.columns if a.startswith("own_")],
            "recent efficiency": [
                a for a in model.columns if a.startswith("efficiency")
            ],
        }
        changes = {}
        for group, cols in groups.items():
            cols = [a for a in cols if a in medians]
            if not cols or not admitted:
                continue
            changed = x.copy()
            for a in cols:
                changed[a] = medians[a]
            changes[group] = candidate - model.predict(changed)
        opportunity = MARKETS[market][2]
        for i, (_, r) in enumerate(g.iterrows()):
            d = r.to_dict()
            s = x.iloc[i]
            d.update(
                enhanced_projection=float(candidate[i])
                if admitted
                else float(r.baseline),
                point_admitted=admitted,
                probability_mode=mode,
                probability_supported=prob,
                calibration_gap=gap,
                diagnostic_mae=float(p.loc[method, "mae"]),
                diagnostic_n=int(p.loc[method, "n"]),
                diagnostic_mae_gain=point_gain,
                history_n=float(s.history_n),
                workload5=number(s[opportunity + "_last5"]),
                role_variability=number(s[opportunity + "_sd5"])
                / max(float(s[opportunity + "_last5"]), 1)
                if number(s[opportunity + "_sd5"]) is not None
                and number(s[opportunity + "_last5"]) is not None
                else float("nan"),
                selection_built_at=now.isoformat(),
                support_tier=2 if admitted and prob else 1 if admitted or prob else 0,
                certified=False,
                classification="ENHANCED MODEL RESEARCH"
                if admitted
                else "BASELINE RETAINED — MODEL RESEARCH",
            )
            d["projection_change"] = d["enhanced_projection"] - d["baseline"]
            d["relative_width"] = (d["q95"] - d["q05"]) / max(
                abs(d["enhanced_projection"]), 1
            )
            d["confidence_label"] = (
                "Retrospective point and probability support"
                if admitted and prob
                else "Retrospective point support; pricing uncertain"
                if admitted
                else "Baseline retained; probability research supported"
                if prob
                else "Baseline retained; limited enhancement evidence"
            )
            d["why_pick"], d["principal_risk"] = explain(d)
            rows.append(d)
            for group, delta in changes.items():
                sensitivities.append(
                    {
                        "game_id": d["game_id"],
                        "player_id": d["player_id"],
                        "market": market,
                        "input_group": group,
                        "change_vs_training_median_reference": float(delta[i]),
                        "interpretation": "Model sensitivity, not causal attribution; correlated inputs held fixed",
                    }
                )
    forecasts = pd.DataFrame(rows)
    forecasts = eligible_rows(forecasts, now)
    top, two = select(forecasts)
    schedule = pd.read_parquet(
        CERTIFIED / "schedule.parquet",
        columns=["game_id", "season", "week", "gameday", "home_team", "away_team"],
    )
    fixtures = schedule[schedule.game_id.isin(original["game_kickoffs"])].copy()
    fixtures["kickoff_at"] = fixtures.game_id.map(original["game_kickoffs"])
    fixtures["research_candidates"] = (
        fixtures.game_id.map(two.groupby("game_id").size()).fillna(0).astype(int)
    )
    fixtures["coverage_status"] = np.where(
        fixtures.research_candidates.gt(0),
        "Enhanced research available",
        np.where(
            fixtures.game_id.eq("2026_11_TEN_DAL"),
            "Excluded: unresolved roof scenarios",
            "Outside Sunday research bundle; certified baseline remains available",
        ),
    )
    output.mkdir(parents=True)
    positive.to_csv(output / "positive_line_evidence.csv", index=False)
    forecasts.to_parquet(output / "forecasts.parquet", index=False)
    top.to_csv(output / "top_picks.csv", index=False)
    two.to_csv(output / "top2.csv", index=False)
    fixtures.to_csv(output / "fixtures.csv", index=False)
    pd.DataFrame(sensitivities).to_csv(output / "sensitivity.csv", index=False)
    m = {
        "schema": 1,
        "release_type": "enhanced_research_selection_v1",
        "created_at": now.isoformat(),
        "parent_release": original["release_id"],
        "parent_manifest_sha256": sha(CERTIFIED / "manifest.json"),
        "experiment_manifest_sha256": sha(EXPERIMENT / "manifest.json"),
        "source_models_sha256": sha(EXPERIMENT / "sunday_models.joblib"),
        "probability_uncertainty_sha256": sha(
            ROOT / "docs/season-intelligence-probability-uncertainty.csv"
        ),
        "policy": policy(),
        "production_changed": False,
        "seal_lifted": False,
        "engine_sha256": sha(Path(__file__)),
        "files": {p.name: sha(p) for p in output.iterdir()},
    }
    (output / "manifest.json").write_text(encoded(m))
    return {
        "forecasts": len(forecasts),
        "top_picks": len(top),
        "top2": len(two),
        "fixtures_with_picks": int(two.game_id.nunique()),
    }


def load(directory=DIRECTORY, now=None):
    directory = Path(directory)
    m = json.loads((directory / "manifest.json").read_text())
    if m["policy"] != policy() or m["production_changed"] or m["seal_lifted"]:
        raise ValueError("Enhanced research policy mismatch")
    if (
        sha(Path(__file__)) != m["engine_sha256"]
        or sha(EXPERIMENT / "manifest.json") != m["experiment_manifest_sha256"]
    ):
        raise ValueError("Enhanced research source mismatch")
    if (
        sha(CERTIFIED / "manifest.json") != m["parent_manifest_sha256"]
        or sha(EXPERIMENT / "sunday_models.joblib") != m["source_models_sha256"]
    ):
        raise ValueError("Enhanced research model/parent mismatch")
    if (
        sha(ROOT / "docs/season-intelligence-probability-uncertainty.csv")
        != m["probability_uncertainty_sha256"]
    ):
        raise ValueError("Enhanced probability evidence changed")
    for name, h in m["files"].items():
        p = (directory / name).resolve()
        p.relative_to(directory.resolve())
        if sha(p) != h:
            raise ValueError("Enhanced research artifact mismatch")
    validate_experiment(EXPERIMENT)
    frame = pd.read_parquet(directory / "forecasts.parquet")
    if frame.certified.any() or frame.prices_verified.any():
        raise ValueError("Research cannot claim certification or verified prices")
    if now is not None:
        frame = eligible_rows(frame, now)
    top, two = select(frame)
    return frame, top, two, pd.read_csv(directory / "fixtures.csv"), m


def price(row, line, odds=None, side="over", refund=False):
    try:
        line = float(line)
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a finite numerical bookmaker line") from error
    if not np.isfinite(line):
        raise ValueError("Enter a finite numerical bookmaker line")
    if line < 0.5:
        return {
            "unavailable": "This line is outside the positive-line validation domain; no enhanced research EV is calculated."
        }
    if row["probability_mode"] == "unavailable":
        return {
            "unavailable": "The enhanced point forecast has not established reliable pricing; the unchanged certified comparison remains below."
        }
    if row["probability_mode"] == "original_normal":
        if float(line).is_integer():
            return {
                "unavailable": "Original normal pricing does not support validated integer pushes; no integer-line EV is calculated."
            }
        p = normal_price(row["baseline"], row["resid_std"], line)
        p.update(
            fair_over=1 / p["over"] if p["over"] else None,
            fair_under=1 / p["under"] if p["under"] else None,
        )
    else:
        bundle = joblib.load(EXPERIMENT / "sunday_models.joblib")
        p = bundle["laws"][row["market"]].price(
            row["enhanced_projection"],
            row["position"],
            MARKETS[row["market"]][3],
            float(line),
        )
    if odds is not None:
        if float(line).is_integer() and not refund:
            raise ValueError("Confirm full-stake refund rules before integer-line EV")
        p.update(quoted_value(p, float(odds), side))
    return p


if __name__ == "__main__":
    print(build())
