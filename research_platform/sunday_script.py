"""Bounded chronological final-margin experiment. Never reads Week 11 outcomes."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from scripts.forecast_features import schedule_times

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/sunday_script/20261120-v1"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def team_inputs(directory, cutoff):
    # Predicate filters precede any materialisation of outcomes.
    filters = [[("season", "<", 2026)], [("season", "==", 2026), ("week", "<", 11)]]
    f = pd.read_parquet(directory / "features.parquet", filters=filters)
    s = schedule_times(pd.read_parquet(directory / "schedule.parquet", filters=filters))
    s = s[s.game_type.eq("REG") & s.completed_at.lt(pd.Timestamp(cutoff))]
    totals = f.groupby(["team", "season", "week"], as_index=False)[
        ["team_total_attempts", "team_total_carries"]
    ].first()
    pieces = []
    for side, other, home in [("home", "away", 1), ("away", "home", -1)]:
        d = s[
            [
                "game_id",
                "season",
                "week",
                "kickoff_at",
                "completed_at",
                side + "_team",
                other + "_team",
                side + "_score",
                other + "_score",
            ]
        ].copy()
        d = d.rename(columns={side + "_team": "team", other + "_team": "opponent"})
        d["margin"] = d[side + "_score"] - d[other + "_score"]
        d["home"] = home
        pieces.append(d.drop(columns=[side + "_score", other + "_score"]))
    d = pd.concat(pieces).merge(
        totals, on=["team", "season", "week"], how="left", validate="one_to_one"
    )
    d = d.rename(
        columns={"team_total_attempts": "attempts", "team_total_carries": "carries"}
    )
    d["available_at"] = pd.concat(
        [d.completed_at, d.kickoff_at + pd.Timedelta(hours=36)], axis=1
    ).max(axis=1)
    d = d.dropna(subset=["margin"]).sort_values(["kickoff_at", "game_id", "team"])
    if (
        d.duplicated(["game_id", "team"]).any()
        or ((d.season == 2026) & (d.week >= 11)).any()
    ):
        raise ValueError("Duplicate or sealed team outcomes")
    counts = d.groupby("game_id").size()
    if not counts.eq(2).all():
        raise ValueError("Incomplete team-game counterpart")
    return d.reset_index(drop=True)


def walk(games, fixtures, p):
    """Fit only labels available before each T-60 decision; OOS residual CDF only."""
    if (games.season > 2026).any() or (
        (games.season == 2026) & (games.week >= 11)
    ).any():
        raise ValueError("Sealed outcomes forbidden")
    all_requests = pd.concat(
        [
            games[
                ["game_id", "team", "opponent", "season", "week", "kickoff_at", "home"]
            ],
            fixtures,
        ],
        ignore_index=True,
    )
    all_requests = all_requests.drop_duplicates(["game_id", "team"]).sort_values(
        ["kickoff_at", "team"]
    )
    all_requests["prediction_at"] = all_requests.kickoff_at - pd.Timedelta(minutes=60)
    updates = list(games.sort_values("available_at").to_dict("records"))
    idx = 0
    histories = defaultdict(list)
    known = []
    predicted = {}
    residuals = []
    out = []
    for decision, batch in all_requests.groupby("prediction_at", sort=True):
        while idx < len(updates) and updates[idx]["available_at"] < decision:
            r = updates[idx]
            idx += 1
            histories[r["team"]].append(r)
            old = predicted.get((r["game_id"], r["team"]))
            if old is not None:
                known.append((old["x"], r["margin"]))
                if np.isfinite(old["expected_margin"]):
                    residuals.append(r["margin"] - old["expected_margin"])
        model = None
        if len(known) >= 200:
            model = Ridge(alpha=p["ridge_alpha"], fit_intercept=False).fit(
                np.array([x for x, y in known]), np.array([y for x, y in known])
            )
        for r in batch.to_dict("records"):
            own = histories[r["team"]][-p["history_games"] :]
            opp = histories[r["opponent"]][-p["history_games"] :]
            if len(own) < 4 or len(opp) < 4:
                continue
            a = pd.DataFrame(own)
            b = pd.DataFrame(opp)
            x = np.array([a.margin.mean() - b.margin.mean(), r["home"]])
            mu = float(model.predict(x[None])[0]) if model is not None else np.nan
            result = {
                **r,
                "x": x,
                "expected_margin": mu,
                "history_available_at": max(a.available_at.max(), b.available_at.max()),
                "fit_n": len(known),
                "cdf_n": len(residuals),
                "own_attempts": a.attempts.mean(),
                "own_carries": a.carries.mean(),
            }
            predicted[(r["game_id"], r["team"])] = result
            if not np.isfinite(mu) or len(residuals) < 100:
                continue
            z = np.asarray(residuals)
            c0 = float(np.mean(mu + z < -7))
            c1 = float(np.mean(mu + z <= 7))
            probs = [c0, c1 - c0, 1 - c1]
            result.update(
                win_probability=float(np.mean(mu + z > 0)),
                p_trailing=probs[0],
                p_close=probs[1],
                p_leading=probs[2],
            )
            for quantity in ["attempts", "carries"]:
                values = []
                for bucket, mask in [
                    ("trailing", a.margin.lt(-7)),
                    ("close", a.margin.between(-7, 7)),
                    ("leading", a.margin.gt(7)),
                ]:
                    usable = mask & a[quantity].notna()
                    value = float(
                        (a.loc[usable, quantity].sum() + 4 * a[quantity].mean())
                        / (usable.sum() + 4)
                    )
                    result[f"{quantity}_{bucket}"] = value
                    values.append(value)
                result["expected_" + quantity] = float(np.dot(probs, values))
            out.append({k: v for k, v in result.items() if k != "x"})
    return pd.DataFrame(out)


def adjustment_features(d):
    return np.column_stack(
        [
            d.projection * (d.expected_attempts / d.own_attempts - 1),
            d.projection * (d.expected_carries / d.own_carries - 1),
            d.projection * d.p_trailing,
            d.projection * d.p_leading,
        ]
    )


def apply_adjustment(base, delta, weight, count):
    result = base + weight * delta
    return result.clip(lower=0) if count else result


def errors(y, pred):
    e = np.asarray(pred) - np.asarray(y)
    return {
        "n": len(e),
        "mae": float(abs(e).mean()),
        "rmse": float(np.sqrt((e**2).mean())),
        "bias": float(e.mean()),
    }


def uncertainty(d, seed):
    # Paired game-cluster bootstrap keeps teammates and markets together.
    q = (
        d.assign(delta=abs(d.adjusted - d.y) - abs(d.projection - d.y))
        .groupby("game_id")
        .delta.agg(["sum", "count"])
    )
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(q), (500, len(q)))
    values = q["sum"].to_numpy()[i].sum(axis=1) / q["count"].to_numpy()[i].sum(axis=1)
    return np.quantile(values, [0.025, 0.975]).tolist()


def run():
    from stage1b.data import MARKETS, market_panel, prepare_panel

    pointer = json.loads((ROOT / "research_active_inference.json").read_text())
    directory = ROOT / pointer["path"]
    manifest = json.loads((directory / "manifest.json").read_text())
    p = json.loads((OUT / "protocol.json").read_text())
    games = team_inputs(directory, manifest["feature_data_cutoff"])
    slate = pd.read_parquet(directory / "slate.parquet")
    fixture_rows = []
    for gid, kickoff in manifest["game_kickoffs"].items():
        away, home = gid.split("_")[-2:]
        for team, opponent, flag in [(home, away, 1), (away, home, -1)]:
            fixture_rows.append(
                {
                    "game_id": gid,
                    "team": team,
                    "opponent": opponent,
                    "season": 2026,
                    "week": 11,
                    "kickoff_at": pd.Timestamp(kickoff),
                    "home": flag,
                }
            )
    team = walk(games, pd.DataFrame(fixture_rows), p)
    observed = team.merge(
        games[["game_id", "team", "margin"]],
        on=["game_id", "team"],
        validate="one_to_one",
    )
    observed = observed[(observed.season >= 2022) & (observed.season <= 2026)]
    scored = []
    bands = []
    for season, g in observed[observed.home.eq(1)].groupby("season"):
        prob = np.clip(g.win_probability, 1e-6, 1 - 1e-6)
        truth = g.margin.gt(0).astype(int)
        actual = np.select([g.margin.lt(-7), g.margin.gt(7)], [0, 2], default=1)
        matrix = g[["p_trailing", "p_close", "p_leading"]].to_numpy()
        scored.append(
            dict(
                season=int(season),
                **errors(g.margin, g.expected_margin),
                win_brier=float(np.mean((prob - truth) ** 2)),
                win_log_loss=float(
                    np.mean(-truth * np.log(prob) - (1 - truth) * np.log(1 - prob))
                ),
                scenario_brier=float(
                    np.mean(np.sum((matrix - np.eye(3)[actual]) ** 2, axis=1))
                ),
                scenario_log_loss=float(
                    -np.log(np.clip(matrix[np.arange(len(g)), actual], 1e-6, 1)).mean()
                ),
            )
        )
        for low in np.arange(0, 1, 0.1):
            mask = prob.ge(low) & prob.lt(low + 0.1)
            if mask.any():
                bands.append(
                    {
                        "season": int(season),
                        "band_low": round(low, 1),
                        "n": int(mask.sum()),
                        "mean_probability": float(prob[mask].mean()),
                        "win_fraction": float(truth[mask].mean()),
                    }
                )
    source = pd.read_parquet(
        directory / "features.parquet",
        filters=[[("season", "<", 2026)], [("season", "==", 2026), ("week", "<", 11)]],
    )
    protocol = {
        "final_start": "2026-11-19T00:00:00Z",
        "final_season": 2026,
        "final_week": 11,
        "prediction_lead_hours": 1,
    }
    panel = prepare_panel(source, protocol)
    archived = pd.read_parquet(
        ROOT / "experiments/stage1b/baseline-20261113-v5/forecasts.parquet"
    )
    results = []
    forecasts = []
    sunday = []
    selection = []
    for market in MARKETS:
        d = market_panel(panel, market)
        d = d[d.scorable & d.feature_complete]
        base = archived[(archived.market == market) & (archived.season < 2026)].copy()
        base = base.merge(
            d[["player_id", "game_id", "team"]],
            on=["player_id", "game_id"],
            validate="one_to_one",
        )
        model = joblib.load(
            ROOT
            / f"experiments/stage1b/baseline-20261113-v5/models/{market}-2026.joblib"
        )
        live = d[d.season.eq(2026)].copy()
        if (
            pd.Timestamp(model["model_information_available_at"])
            >= live.prediction_at.min()
        ):
            raise ValueError("Baseline model is not historically available")
        live["projection"] = model["point"].predict(live[model["features"]])
        if MARKETS[market][3]:
            live["projection"] = live.projection.clip(lower=0)
        live["market"] = market
        cols = [
            "player_id",
            "game_id",
            "team",
            "season",
            "week",
            "y",
            "projection",
            "market",
        ]
        both = pd.concat([base[cols], live[cols]], ignore_index=True)
        merged = both.merge(
            team.drop(columns=["season", "week", "opponent"]),
            on=["game_id", "team"],
            validate="many_to_one",
        )
        if len(merged) != len(both):
            raise ValueError("Context missing; evaluation populations differ")
        fit = merged[merged.season.isin(p["adjustment_fit_seasons"])]
        select = merged[merged.season.eq(2025)]
        test = merged[merged.season.eq(2026)].copy()
        adj = make_pipeline(StandardScaler(), Ridge(alpha=p["ridge_alpha"])).fit(
            adjustment_features(fit), fit.y - fit.projection
        )
        candidate = adj.predict(adjustment_features(select))
        baseline = abs(select.projection - select.y).mean()
        choices = [
            (
                float(
                    abs(
                        apply_adjustment(
                            select.projection, candidate, w, MARKETS[market][3]
                        )
                        - select.y
                    ).mean()
                ),
                w,
            )
            for w in p["strength_candidates"]
        ]
        mae, weight = min(choices)
        if mae > baseline * (1 - p["minimum_mae_gain"]):
            weight = 0
        hold_delta = adj.predict(adjustment_features(test))
        test["adjusted"] = apply_adjustment(
            test.projection, hold_delta, weight, MARKETS[market][3]
        )
        diagnostics = []
        for w in p["strength_candidates"]:
            candidate_test = test.copy()
            candidate_test["adjusted"] = apply_adjustment(
                test.projection, hold_delta, w, MARKETS[market][3]
            )
            diagnostics.append(
                dict(
                    weight=w,
                    **errors(test.y, candidate_test.adjusted),
                    paired_mae_delta95=uncertainty(candidate_test, p["seed"]),
                )
            )
        test["market"] = market
        forecasts.append(test)
        ci = uncertainty(test, p["seed"])
        before = errors(test.y, test.projection)
        after = errors(test.y, test.adjusted)
        gain = 1 - after["mae"] / before["mae"]
        results.append(
            {
                "market": market,
                "baseline": before,
                "adjusted": after,
                "relative_mae_gain": gain,
                "paired_mae_delta95": ci,
                "selection_weight": weight,
                "candidate_holdout_metrics": diagnostics,
                "passes_market_gate": bool(gain >= 0.02 and ci[1] < 0),
                "weeks": sorted(map(int, test.week.unique())),
                "games": int(test.game_id.nunique()),
            }
        )
        selection.append(
            {
                "market": market,
                "fit_n": len(fit),
                "select_n": len(select),
                "strength": weight,
                "selection_baseline_mae": float(baseline),
                "candidates": choices,
            }
        )
        label = {
            "passing_yards": "Passing Yards",
            "passing_attempts": "Passing Attempts",
            "completions": "Completions",
            "rushing_yards": "Rushing Yards",
            "rushing_attempts": "Rushing Attempts",
            "qb_rushing_yards": "QB Rushing Yards",
            "qb_rushing_attempts": "QB Rushing Attempts",
            "receiving_yards": "Receiving Yards",
            "receptions": "Receptions",
        }[market]
        future = slate[
            slate.market.eq(label) & slate.projection_status.eq("complete")
        ].merge(
            team[team.week.eq(11)].drop(columns=["season", "week", "opponent"]),
            on=["game_id", "team"],
            validate="many_to_one",
        )
        future["adjusted"] = apply_adjustment(
            future.projection,
            adj.predict(adjustment_features(future)),
            weight,
            MARKETS[market][3],
        )
        future["baseline"] = future.projection
        future["experimental_market"] = market
        for state in ["trailing", "close", "leading"]:
            scenario = future.copy()
            scenario.expected_attempts = scenario["attempts_" + state]
            scenario.expected_carries = scenario["carries_" + state]
            for s in ["trailing", "close", "leading"]:
                scenario["p_" + s] = float(s == state)
            future["projection_" + state] = apply_adjustment(
                future.projection,
                adj.predict(adjustment_features(scenario)),
                weight,
                MARKETS[market][3],
            )
        sunday.append(future)
    replay = pd.concat(forecasts)
    replay.to_parquet(OUT / "player_replay.parquet", index=False)
    weekly = []
    for (market, week), g in replay.groupby(["market", "week"]):
        weekly.append(
            {
                "market": market,
                "week": int(week),
                "baseline": errors(g.y, g.projection),
                "adjusted": errors(g.y, g.adjusted),
            }
        )
    (OUT / "weekly_metrics.json").write_text(
        json.dumps(weekly, indent=2, allow_nan=False) + "\n"
    )
    pd.concat(sunday).to_parquet(OUT / "sunday_experimental.parquet", index=False)
    team[team.week.eq(11) & team.season.eq(2026)].to_csv(
        OUT / "sunday_games.csv", index=False
    )
    pd.DataFrame(bands).to_csv(OUT / "win_reliability.csv", index=False)
    report = {
        "protocol": p,
        "source_release": manifest["release_id"],
        "team_volume_missing_rows": int(
            games[["attempts", "carries"]].isna().any(axis=1).sum()
        ),
        "baseline_description": "Archived Stage 1B chronological point models, not the November-trained live nine models; 2026 predictions regenerated on refreshed cutoff-safe inputs.",
        "team_scenario_definition": p["scenario_definition"],
        "team_metrics": scored,
        "player_metrics": results,
        "selection": selection,
        "activation": False,
        "reason": "Previously inspected development data; no validated in-game state model or player predictive distributions. Certified forecasts unchanged.",
        "team_games_2026": int(games[games.season.eq(2026)].game_id.nunique()),
        "player_holdout_rows": int(sum(x["baseline"]["n"] for x in results)),
    }
    (OUT / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    files = [
        "protocol.json",
        "player_replay.parquet",
        "sunday_experimental.parquet",
        "sunday_games.csv",
        "win_reliability.csv",
        "report.json",
        "weekly_metrics.json",
    ]
    inputs = {
        str(path.relative_to(ROOT)): digest(path)
        for path in [
            directory / "manifest.json",
            directory / "features.parquet",
            directory / "schedule.parquet",
            ROOT / "experiments/stage1b/baseline-20261113-v5/forecasts.parquet",
            ROOT / "stage1b/data.py",
            ROOT / "scripts/forecast_features.py",
        ]
    }
    for path in (ROOT / "experiments/stage1b/baseline-20261113-v5/models").glob(
        "*-2026.joblib"
    ):
        inputs[str(path.relative_to(ROOT))] = digest(path)
    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "final_period_sealed": True,
                "code_sha256": digest(Path(__file__)),
                "inputs": inputs,
                "files": {n: digest(OUT / n) for n in files},
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "team_games_2026": report["team_games_2026"],
                "player_rows": report["player_holdout_rows"],
                "activation": False,
            }
        )
    )


if __name__ == "__main__":
    run()
