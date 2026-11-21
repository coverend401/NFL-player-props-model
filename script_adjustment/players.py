"""Chronological champion replicas, coherent workload allocation and residual innovations."""

import hashlib
import inspect
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from scripts.forecast_features import observation_status, pregame_eligible
from scripts.train_all_markets import MARKETS as CHAMPION
from stage1b.data import MARKETS

CATEGORIES = {
    "attempts": ["QB"],
    "carries": ["RB", "QB", "WR", "TE"],
    "targets": ["RB", "WR", "TE", "QB"],
}
SHARE_COLS = [
    "share_recent",
    "share_career",
    "prior_opportunities",
    "prior_snaps",
    "prior_games",
    "is_qb",
    "is_rb",
    "is_wr",
    "is_te",
]
Z = [
    "volume_effect",
    "share_effect",
    "efficiency_effect",
    "state_effect",
    "mobility_effect",
]


def champion_replay(source, cache):
    """Never run the2026 champion on its own historical training observations."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, cfg in CHAMPION.items():
        market = cfg.get("model_name", key)
        target = cfg.get("target_col", key)
        cols = cfg["features"]
        d = (
            source[
                pregame_eligible(source, cfg["positions"])
                & observation_status(source).eq("participated")
                & source.stats_observed.eq(True)
            ]
            .dropna(subset=cols + [target, "completed_at"])
            .copy()
        )
        d["prediction_at"] = pd.to_datetime(d.kickoff_at, utc=True) - pd.Timedelta(
            minutes=60
        )
        d["available_at"] = pd.concat(
            [
                pd.to_datetime(d.completed_at, utc=True),
                pd.to_datetime(d.kickoff_at, utc=True) + pd.Timedelta(hours=36),
            ],
            axis=1,
        ).max(axis=1)
        for year in range(2022, 2027):
            evaluate = d[d.season.eq(year)].copy()
            if evaluate.empty:
                continue
            cutoff = evaluate.prediction_at.min()
            past = d[d.season.lt(year) & d.available_at.lt(cutoff)]
            selection = past[past.season.eq(year - 1)]
            fit = past[past.available_at.lt(selection.prediction_at.min())]
            token = hashlib.sha256(
                (
                    inspect.getsource(champion_replay)
                    + pd.util.hash_pandas_object(
                        past[cols + [target, "game_id", "player_id"]], index=False
                    )
                    .values.tobytes()
                    .hex()
                ).encode()
            ).hexdigest()
            path = cache / f"{market}-{year}.joblib"
            if path.exists():
                bundle = joblib.load(path)
                if bundle["token"] != token:
                    raise ValueError("Research backbone cache mismatch")
            else:
                builds = {
                    "ridge": lambda: Ridge(alpha=1),
                    "gradient_boosting": lambda: GradientBoostingRegressor(
                        n_estimators=200,
                        max_depth=3,
                        learning_rate=0.05,
                        random_state=42,
                    ),
                }
                scores = {
                    "naive": float(
                        np.mean(np.abs(selection[cols[0]] - selection[target]))
                    )
                }
                for name, build in builds.items():
                    candidate = build().fit(fit[cols], fit[target])
                    scores[name] = float(
                        np.mean(
                            np.abs(
                                candidate.predict(selection[cols]) - selection[target]
                            )
                        )
                    )
                name = min(scores, key=scores.get)
                model = (
                    None
                    if name == "naive"
                    else builds[name]().fit(past[cols], past[target])
                )
                residual = past[target].to_numpy() - (
                    past[cols[0]].to_numpy()
                    if model is None
                    else model.predict(past[cols])
                )
                bundle = {
                    "token": token,
                    "model": model,
                    "method": name,
                    "selection_scores": scores,
                    "training_before": cutoff.isoformat(),
                    "last_training_outcome": past.available_at.max().isoformat(),
                    "features": cols,
                    "sigma": float(np.std(residual)),
                    "naive_fallback": name == "naive",
                }
                joblib.dump(bundle, path)
            evaluate["baseline"] = (
                evaluate[cols[0]]
                if bundle["model"] is None
                else bundle["model"].predict(evaluate[cols])
            )
            evaluate["champion_method"] = bundle["method"]
            evaluate["champion_sigma"] = bundle["sigma"]
            evaluate["champion_fit_before"] = bundle["last_training_outcome"]
            evaluate["market"] = market
            evaluate["y"] = evaluate[target]
            metadata = [
                "player_id",
                "player_display_name",
                "team",
                "opponent_team",
                "position",
                "season",
                "week",
                "game_id",
                "completed_at",
                "prediction_at",
                "available_at",
                "offense_pct",
                "stats_observed",
                "games_played_prior",
                "baseline",
                "champion_method",
                "champion_sigma",
                "champion_fit_before",
                "market",
                "y",
            ]
            rows.append(
                evaluate[
                    list(dict.fromkeys(cols + [c for c in metadata if c in evaluate]))
                ]
            )
        print("BACKBONE", market, flush=True)
    return pd.concat(rows, ignore_index=True)


def player_histories(source, operational_available=None, fixtures=None):
    """Pregame pools come from earlier observations, never eventual game participants.

    Last observed team is a retrospective membership hypothesis, not verified
    active status. Missing/retired/traded histories remain uncertain, never zeros.
    Cached summaries avoid recomputing unchanged past history for absent players.
    """
    columns = [
        "player_id",
        "game_id",
        "team",
        "position",
        "season",
        "week",
        "kickoff_at",
        "completed_at",
        "offense_pct",
        "stats_observed",
        "attempts",
        "carries",
        "targets",
        "passing_yards",
        "completions",
        "rushing_yards",
        "receiving_yards",
        "receptions",
        "team_total_attempts",
        "team_total_carries",
    ]
    d = source[columns].copy()
    d["available_at"] = pd.concat(
        [
            pd.to_datetime(d.completed_at, utc=True),
            pd.to_datetime(d.kickoff_at, utc=True) + pd.Timedelta(hours=36),
        ],
        axis=1,
    ).max(axis=1)
    if operational_available is not None:
        observed = pd.to_datetime(d.game_id.map(operational_available), utc=True)
        mask = observed.notna()
        d.loc[mask, "available_at"] = pd.concat(
            [pd.to_datetime(d.completed_at, utc=True), observed], axis=1
        ).max(axis=1)[mask]
    genuine = d[
        d.offense_pct.gt(0)
        & d.stats_observed.eq(True)
        & d.available_at.notna()
        & d.position.isin(["QB", "RB", "WR", "TE"])
    ]
    updates = list(genuine.sort_values("available_at").to_dict("records"))
    actual = {(g["game_id"], g["player_id"]): g for g in d.to_dict("records")}
    requests = (
        fixtures
        if fixtures is not None
        else d[["game_id", "team", "season", "week", "kickoff_at"]].drop_duplicates()
    ).sort_values(["kickoff_at", "team"])
    histories = {}
    pools = {}
    summaries = {}
    i = 0
    rows = []

    def summarize(h, cat):
        recent = h[-3:]
        denominator = (
            "team_total_attempts"
            if cat in ["attempts", "targets"]
            else "team_total_carries"
        )

        def total(group, col):
            values = np.asarray([x.get(col, np.nan) for x in group], dtype=float)
            return float(values.sum()) if np.isfinite(values).all() else np.nan

        num, den, rn, rd = (
            total(h, cat),
            total(h, denominator),
            total(recent, cat),
            total(recent, denominator),
        )
        if not np.isfinite([num, den, rn, rd]).all() or den <= 0 or rd <= 0:
            return None
        career = num / den
        result = {
            "share_recent": (rn + 30 * career) / (rd + 30),
            "share_career": career,
            "prior_opportunities": rn / len(recent),
            "prior_snaps": float(np.mean([x["offense_pct"] for x in recent])),
            "prior_games": len(h),
            "history_available_at": max(pd.Timestamp(x["available_at"]) for x in h),
            "last_team": h[-1]["team"],
            "membership_basis": "last_observed_team_only_not_verified_roster",
            "membership_observed_at": h[-1]["available_at"],
        }
        for pos in ["QB", "RB", "WR", "TE"]:
            result["is_" + pos.lower()] = int(h[-1]["position"] == pos)
        for target in [
            "passing_yards",
            "completions",
            "rushing_yards",
            "receiving_yards",
            "receptions",
        ]:
            cy, ry = total(h, target), total(recent, target)
            result["eff_" + target] = (
                (ry + 30 * (cy / num)) / (rn + 30)
                if num > 0 and np.isfinite([cy, ry]).all()
                else np.nan
            )
            result["career_eff_" + target] = cy / num if num > 0 else np.nan
        return result

    for game in requests.to_dict("records"):
        decision = pd.Timestamp(game["kickoff_at"]) - pd.Timedelta(minutes=60)
        while i < len(updates) and pd.Timestamp(updates[i]["available_at"]) < decision:
            u = updates[i]
            identity = u["player_id"]
            old = histories.get(identity)
            if old and old[-1]["team"] != u["team"]:
                pools[old[-1]["team"]].discard(identity)
            histories.setdefault(identity, []).append(u)
            pools.setdefault(u["team"], set()).add(identity)
            for cat in CATEGORIES:
                summaries.pop((identity, cat), None)
            i += 1
        for identity in sorted(pools.get(game["team"], set())):
            h = histories[identity]
            if len(h) < 3:
                continue
            position = h[-1]["position"]
            # Outcome lookup supplies labels only, after the pregame pool is fixed.
            label = actual.get((game["game_id"], identity), {})
            for cat, positions in CATEGORIES.items():
                if position not in positions:
                    continue
                key = (identity, cat)
                if key not in summaries:
                    summaries[key] = summarize(h, cat)
                features = summaries[key]
                if features is None:
                    continue
                denominator = (
                    "team_total_attempts"
                    if cat in ["attempts", "targets"]
                    else "team_total_carries"
                )
                row = {
                    **features,
                    **game,
                    "player_id": identity,
                    "position": position,
                    "category": cat,
                    "completed_at": label.get("completed_at", pd.NaT),
                    "stats_observed": label.get("stats_observed", False),
                    "offense_pct": label.get("offense_pct", np.nan),
                    "actual_opportunities": label.get(cat, np.nan),
                    "actual_team_opportunities": label.get(denominator, np.nan),
                }
                rows.append(row)
    return pd.DataFrame(rows)


def allocate(candidates, teams, models=None):
    """Coherent capacity ceiling and explicit unassigned buckets, no fabricated teammates."""
    d = candidates.merge(
        teams,
        on=["game_id", "team", "season", "week", "kickoff_at"],
        how="inner",
        validate="many_to_one",
        suffixes=("", "_team"),
    )
    if d.empty:
        return d, pd.DataFrame()
    pieces = []
    for cat, g in d.groupby("category"):
        g = g.copy()
        g["predicted_share"] = (
            g.share_recent
            if models is None
            else np.clip(models[cat].predict(g[SHARE_COLS]), 0, 1)
        )
        # Individual mobility response: scramble capacity changes only QB carry shares.
        if cat == "carries":
            mobility = g.expected_scramble - g.expected_carries * (
                g.own_plays * g.own_scramble_rate / g.own_carries.clip(lower=1)
            )
            qb = g.position.eq("QB")
            g.loc[qb, "predicted_share"] += (
                mobility[qb]
                / g.expected_carries[qb].clip(lower=1)
                * g.loc[qb, "prior_snaps"].clip(0, 1)
            )
        g["predicted_share"] = g.predicted_share.clip(0, 1)
        sums = g.groupby(["game_id", "team"]).predicted_share.transform("sum")
        g["predicted_share"] /= sums.clip(lower=1)
        g["team_opportunities"] = (
            g.expected_carries if cat == "carries" else g.expected_attempts
        )
        g["usual_team_opportunities"] = (
            g.own_carries if cat == "carries" else g.own_attempts
        )
        g["allocated_opportunities"] = g.predicted_share * g.team_opportunities
        pieces.append(g)
    result = pd.concat(pieces, ignore_index=True)
    summary = result.groupby(["game_id", "team", "category"], as_index=False).agg(
        allocated=("allocated_opportunities", "sum"),
        capacity=("team_opportunities", "first"),
        players=("player_id", "nunique"),
    )
    summary["unassigned"] = summary.capacity - summary.allocated
    if summary.unassigned.lt(-1e-8).any() or result.allocated_opportunities.lt(0).any():
        raise ValueError("Incoherent allocations")
    return result, summary


def allocation_folds(players, teams):
    frames = []
    coherence = []
    bundles = {}
    for year in range(2022, 2027):
        current = teams[teams.season.eq(year)]
        if current.empty:
            continue
        cutoff = current.prediction_at.min()
        models = {}
        for cat, g in players.groupby("category"):
            available = pd.concat(
                [
                    pd.to_datetime(g.completed_at, utc=True),
                    pd.to_datetime(g.kickoff_at, utc=True) + pd.Timedelta(hours=36),
                ],
                axis=1,
            ).max(axis=1)
            fit = g[
                g.season.lt(year)
                & available.lt(cutoff)
                & g.stats_observed.eq(True)
                & g.offense_pct.gt(0)
                & g.actual_team_opportunities.gt(0)
            ].dropna(subset=SHARE_COLS + ["actual_opportunities"])
            y = (fit.actual_opportunities / fit.actual_team_opportunities).clip(0, 1)
            model = make_pipeline(StandardScaler(), Ridge(alpha=100))
            model.fit(
                fit[SHARE_COLS],
                y,
                ridge__sample_weight=fit.actual_team_opportunities.to_numpy(),
            )
            models[cat] = model
        frame, counts = allocate(players[players.season.eq(year)], current, models)
        frames.append(frame)
        coherence.append(counts)
        bundles[year] = models
    return (
        pd.concat(frames, ignore_index=True),
        pd.concat(coherence, ignore_index=True),
        bundles,
    )


def innovations(baseline, allocations):
    pieces = []
    configs = {c.get("model_name", k): c for k, c in CHAMPION.items()}
    for market, g in baseline.groupby("market"):
        target, _, cat, count = MARKETS[market]
        a = allocations[allocations.category.eq(cat)]
        keep = [
            "game_id",
            "player_id",
            "allocated_opportunities",
            "predicted_share",
            "share_recent",
            "prior_opportunities",
            "usual_team_opportunities",
            "team_opportunities",
            "expected_scramble",
            "own_plays",
            "own_scramble_rate",
            "prob_leading",
            "prob_tied",
            "prob_trailing",
            "own_leading_share",
            "own_trailing_share",
            "expected_plays",
            "expected_attempts",
            "expected_carries",
            "expected_margin",
            "win_probability",
            "tie_probability",
            "plays_leading",
            "plays_tied",
            "plays_trailing",
            "history_available_at",
            "prior_snaps",
            "last_team",
            "actual_opportunities",
            "actual_team_opportunities",
        ]
        if not count:
            keep += ["eff_" + target, "career_eff_" + target]
        x = g.merge(
            a[keep],
            on=["game_id", "player_id"],
            how="left",
            validate="one_to_one",
            suffixes=("", "_allocation"),
        )
        eff = np.ones(len(x)) if count else x["eff_" + target].to_numpy()
        career_eff = eff if count else x["career_eff_" + target].to_numpy()
        x["structural_projection"] = x.allocated_opportunities * eff
        x["volume_effect"] = (
            (x.team_opportunities - x.usual_team_opportunities)
            * x.predicted_share
            * eff
        )
        x["share_effect"] = (
            (x.predicted_share - x.share_recent) * x.usual_team_opportunities * eff
        )
        x["efficiency_effect"] = (eff - career_eff) * x.prior_opportunities
        x["state_effect"] = (
            (
                x.prob_trailing
                - x.own_trailing_share
                - x.prob_leading
                + x.own_leading_share
            )
            * x.prior_opportunities
            * eff
        )
        x["mobility_effect"] = np.where(
            x.position.eq("QB"),
            (x.expected_scramble - x.own_plays * x.own_scramble_rate)
            * x.prior_snaps
            * eff,
            0,
        )
        x["adjustment_features_available"] = np.isfinite(x[Z]).all(axis=1)
        x["baseline_features_complete"] = (
            x[configs[market]["features"]].notna().all(axis=1)
        )
        pieces.append(x)
    return pd.concat(pieces, ignore_index=True)


class Correction:
    def fit(self, d, columns, z_columns=None):
        self.columns = columns
        self.z_columns = list(z_columns or Z)
        self.orthogonal = make_pipeline(StandardScaler(), LinearRegression()).fit(
            d[columns], d[self.z_columns]
        )
        residual = d[self.z_columns].to_numpy() - self.orthogonal.predict(d[columns])
        # Exact projection removes components already linearly explained by champion
        # inputs. Do not turn floating-point projection noise into a new signal.
        tolerance = 1e-8 * np.maximum(1, d[self.z_columns].std(ddof=0).to_numpy())
        self.active = np.std(residual, axis=0) > tolerance
        residual = np.where(self.active, residual, 0)
        self.scale = StandardScaler(with_mean=False).fit(residual)
        self.model = Ridge(alpha=100, fit_intercept=False).fit(
            self.scale.transform(residual), d.y - d.baseline
        )
        return self

    def predict(self, d):
        self.z_columns = getattr(self, "z_columns", Z)
        residual = d[self.z_columns].to_numpy() - self.orthogonal.predict(
            d[self.columns]
        )
        residual = np.where(self.active, residual, 0)
        contributions = self.scale.transform(residual) * self.model.coef_[None, :]
        return contributions.sum(axis=1), contributions


def correction_folds(frame, protocol, z_columns=None):
    configs = {c.get("model_name", k): c for k, c in CHAMPION.items()}
    rows = []
    bundles = {}
    for market, g in frame.groupby("market"):
        cols = list(dict.fromkeys(configs[market]["features"] + ["baseline"]))
        for year in range(2022, 2027):
            e = g[g.season.eq(year)].copy()
            if e.empty:
                continue
            cutoff = e.prediction_at.min()
            available = pd.to_datetime(g.completed_at, utc=True) + pd.Timedelta(
                hours=28
            )
            fit = g[
                g.season.lt(year)
                & available.lt(cutoff)
                & g.adjustment_features_available
                & g.baseline_features_complete
            ]
            e["delta"] = 0.0
            e["adjustment_status"] = "insufficient_prior_chronological_residuals"
            valid = e.adjustment_features_available & e.baseline_features_complete
            if len(fit) >= 100:
                model = Correction().fit(fit, cols, z_columns)
                raw, contrib = model.predict(e[valid])
                cap = np.maximum(
                    np.abs(e.loc[valid, "baseline"])
                    * protocol["maximum_adjustment_fraction"],
                    protocol["maximum_adjustment_floors"][market],
                )
                e.loc[valid, "delta"] = np.clip(raw, -cap, cap)
                e.loc[valid, "adjustment_status"] = "experimental_residual_script"
                for i, c in enumerate(model.z_columns):
                    e.loc[valid, "contribution_" + c] = contrib[:, i]
                bundles[(market, year)] = model
                e["correction_fit_before"] = available.loc[fit.index].max()
            e["adjusted"] = e.baseline + e.delta
            if MARKETS[market][3]:
                e["adjusted"] = e.adjusted.clip(lower=0)
            e["delta"] = e.adjusted - e.baseline
            rows.append(e)
    return pd.concat(rows, ignore_index=True), bundles
