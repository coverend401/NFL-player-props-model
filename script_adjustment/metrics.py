"""Paired chronological diagnostics; hypothetical lines never imply betting returns."""

import numpy as np
import pandas as pd
from scipy.stats import norm


def point(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    good = np.isfinite(y) & np.isfinite(p)
    e = p[good] - y[good]
    return (
        {
            "n": int(good.sum()),
            "mae": float(np.abs(e).mean()),
            "rmse": float(np.sqrt(np.mean(e**2))),
            "bias": float(e.mean()),
        }
        if len(e)
        else {"n": 0, "mae": None, "rmse": None, "bias": None}
    )


def binary(y, p):
    y, p = np.asarray(y, float), np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return {
        "brier": float(np.mean((p - y) ** 2)),
        "log_loss": float(np.mean(-y * np.log(p) - (1 - y) * np.log(1 - p))),
    }


def player_metrics(d):
    records = []
    reliability = []
    for (market, year), g in d.groupby(["market", "season"]):
        out = {
            "market": market,
            "season": int(year),
            "adjusted_rows": int(
                g.adjustment_status.eq("experimental_residual_script").sum()
            ),
            "missing_context_kept_at_baseline": int(
                (~g.adjustment_features_available).sum()
            ),
            "zero_outcomes": int(g.y.eq(0).sum()),
        }
        for name, col in [("baseline", "baseline"), ("adjusted", "adjusted")]:
            out.update({name + "_" + k: v for k, v in point(g.y, g[col]).items()})
            # Explicit assumption-sensitive Stage1A pricing diagnostic. No odds/EV.
            target = {
                "passing_attempts": "attempts",
                "rushing_attempts": "carries",
                "qb_rushing_attempts": "carries",
                "qb_rushing_yards": "rushing_yards",
            }.get(market, market)
            line = np.floor(g[target + "_season_avg"].clip(lower=0)) + 0.5
            sigma = g.champion_sigma.clip(lower=1e-6)
            p = norm.sf(line, loc=g[col], scale=sigma)
            out.update({name + "_" + k: v for k, v in binary(g.y.gt(line), p).items()})
            lo = g[col] - norm.ppf(0.95) * sigma
            hi = g[col] + norm.ppf(0.95) * sigma
            out[name + "_coverage90"] = float(((g.y >= lo) & (g.y <= hi)).mean())
            out[name + "_width90"] = float((hi - lo).mean())
            out[name + "_interval_score90"] = float(
                np.mean(
                    hi
                    - lo
                    + 20 * (lo - g.y).clip(lower=0)
                    + 20 * (g.y - hi).clip(lower=0)
                )
            )
            for band in range(10):
                mask = (p >= band / 10) & (
                    p < ((band + 1) / 10) if band < 9 else p <= 1
                )
                if mask.any():
                    reliability.append(
                        {
                            "market": market,
                            "season": int(year),
                            "method": name,
                            "band": band,
                            "n": int(mask.sum()),
                            "predicted": float(np.mean(p[mask])),
                            "observed": float(g.y.gt(line)[mask].mean()),
                            "line_tier": "hypothetical_pregame_half_line_not_bookmaker",
                        }
                    )
        out["mae_gain"] = 1 - out["adjusted_mae"] / out["baseline_mae"]
        records.append(out)
    return pd.DataFrame(records), pd.DataFrame(reliability)


def team_metrics(d):
    rows = []
    reliability = []
    for year, g in d.groupby("season"):
        out = {
            "season": int(year),
            "team_games": len(g),
            "games": int(g.game_id.nunique()),
        }
        for actual, pred in [
            ("plays", "expected_plays"),
            ("attempts", "expected_attempts"),
            ("carries", "expected_carries"),
            ("margin", "expected_margin"),
        ]:
            out.update(
                {actual + "_" + k: v for k, v in point(g[actual], g[pred]).items()}
            )
            naive = "own_" + actual
            if naive in g:
                out[actual + "_naive_mae"] = point(g[actual], g[naive])["mae"]
        h = g[g.is_home.eq(1)]
        out.update(
            {
                "win_" + k: v
                for k, v in binary(h.margin.gt(0), h.win_probability).items()
            }
        )
        p = np.clip(g[[f"prob_cell_{i}" for i in range(15)]].to_numpy(), 1e-9, 1)
        n = g[[f"cell_{i}" for i in range(15)]].to_numpy()
        f = n / n.sum(axis=1, keepdims=True)
        out["clock_score_log_loss"] = float(np.sum(-n * np.log(p)) / n.sum())
        out["clock_score_brier"] = float(
            np.average(
                (p * p).sum(axis=1) - 2 * (p * f).sum(axis=1) + 1, weights=n.sum(axis=1)
            )
        )
        observed = np.column_stack(
            [
                f[:, [3, 4, 8, 9, 13, 14]].sum(axis=1),
                f[:, [2, 7, 12]].sum(axis=1),
                f[:, [0, 1, 5, 6, 10, 11]].sum(axis=1),
            ]
        )
        predicted = g[["prob_leading", "prob_tied", "prob_trailing"]].to_numpy()
        naive = g[
            ["own_leading_share", "own_tied_share", "own_trailing_share"]
        ].to_numpy()
        out["occupancy_share_rmse"] = float(
            np.sqrt(np.mean((predicted - observed) ** 2))
        )
        out["occupancy_naive_rmse"] = float(np.sqrt(np.mean((naive - observed) ** 2)))
        out["state_log_loss"] = float(
            np.sum(
                -observed
                * np.log(np.clip(predicted, 1e-9, 1))
                * n.sum(axis=1, keepdims=True)
            )
            / n.sum()
        )
        for idx, label in enumerate(["leading", "tied", "trailing"]):
            for band in range(10):
                mask = (predicted[:, idx] >= band / 10) & (
                    predicted[:, idx] < ((band + 1) / 10)
                    if band < 9
                    else predicted[:, idx] <= 1
                )
                if mask.any():
                    reliability.append(
                        {
                            "season": int(year),
                            "state": label,
                            "band": band,
                            "team_games": int(mask.sum()),
                            "plays": int(n[mask].sum()),
                            "predicted": float(
                                np.average(
                                    predicted[mask, idx], weights=n[mask].sum(axis=1)
                                )
                            ),
                            "observed": float(
                                np.average(
                                    observed[mask, idx], weights=n[mask].sum(axis=1)
                                )
                            ),
                        }
                    )
        for band in range(10):
            mask = h.win_probability.ge(band / 10) & h.win_probability.le(
                (band + 1) / 10
            )
            if mask.any():
                reliability.append(
                    {
                        "season": int(year),
                        "state": "home_win",
                        "band": band,
                        "team_games": int(mask.sum()),
                        "plays": None,
                        "predicted": float(h.loc[mask, "win_probability"].mean()),
                        "observed": float(h.loc[mask, "margin"].gt(0).mean()),
                    }
                )
        rows.append(out)
    return pd.DataFrame(rows), pd.DataFrame(reliability)


def selection(d, p):
    # All27 scale/market comparisons share the multiplicity family.
    rng = np.random.default_rng(p["seed"])
    candidates = []
    for market, g in d[d.season.eq(p["selection_season"])].groupby("market"):
        for scale in p["adjustment_scale_candidates"]:
            pred = g.baseline + scale * (g.adjusted - g.baseline)
            dif = np.abs(pred - g.y) - np.abs(g.baseline - g.y)
            weekly = (
                pd.DataFrame({"week": g.week, "delta": dif})
                .groupby("week")
                .delta.mean()
                .to_numpy()
            )
            # Nonoverlapping two-week blocks retain within-block dependence.
            blocks = np.array(
                [weekly[j : j + 2].mean() for j in range(0, len(weekly), 2)]
            )
            draws = rng.choice(
                blocks, (p["bootstrap_replicates"], len(blocks)), replace=True
            ).mean(axis=1)
            centered = blocks - blocks.mean()
            null = rng.choice(
                centered, (p["bootstrap_replicates"], len(centered)), replace=True
            ).mean(axis=1)
            pv = (1 + np.sum(null <= blocks.mean())) / (len(null) + 1)
            gain = 1 - np.abs(pred - g.y).mean() / np.abs(g.baseline - g.y).mean()
            seasons = []
            for year, h in d[
                d.market.eq(market) & d.season.isin(p["development_seasons"])
            ].groupby("season"):
                if (
                    np.abs(h.baseline + scale * (h.adjusted - h.baseline) - h.y).mean()
                    < np.abs(h.baseline - h.y).mean()
                ):
                    seasons.append(int(year))
            candidates.append(
                {
                    "market": market,
                    "scale": scale,
                    "n": len(g),
                    "weeks": int(g.week.nunique()),
                    "mae_gain": float(gain),
                    "paired_low": float(np.quantile(draws, 0.025)),
                    "paired_high": float(np.quantile(draws, 0.975)),
                    "p_value": float(pv),
                    "improving_development_seasons": seasons,
                }
            )
    ordered = sorted(candidates, key=lambda c: c["p_value"])
    running = 0
    for i, c in enumerate(ordered):
        running = max(running, min(1, c["p_value"] * (len(ordered) - i)))
        c["holm_p"] = running
        c["selection_gate_passed"] = bool(
            c["n"] >= p["minimum_rows"]
            and c["weeks"] >= p["minimum_weeks"]
            and c["mae_gain"] >= p["minimum_gain"]
            and c["paired_high"] < 0
            and c["holm_p"] < p["familywise_alpha"]
            and len(c["improving_development_seasons"]) >= 2
        )
    selected = {
        market: max(
            [c for c in candidates if c["market"] == market],
            key=lambda c: c["mae_gain"],
        )
        for market in d.market.unique()
    }
    return candidates, selected


def attribution(d):
    x = d.copy()
    eff = np.where(x.actual_opportunities.gt(0), x.y / x.actual_opportunities, 0)
    guessed = np.where(
        x.allocated_opportunities.gt(0),
        x.structural_projection / x.allocated_opportunities,
        np.nan,
    )
    share = np.where(
        x.actual_team_opportunities.gt(0),
        x.actual_opportunities / x.actual_team_opportunities,
        np.nan,
    )
    x["team_volume_component"] = (
        (x.team_opportunities - x.actual_team_opportunities)
        * x.predicted_share
        * guessed
    )
    x["player_share_component"] = (
        x.actual_team_opportunities * (x.predicted_share - share) * guessed
    )
    x["player_efficiency_component"] = x.actual_opportunities * (guessed - eff)
    x["residual_stack_component"] = x.adjusted - x.structural_projection
    x["decomposition_available"] = np.isfinite(
        x[
            [
                "team_volume_component",
                "player_share_component",
                "player_efficiency_component",
                "residual_stack_component",
            ]
        ]
    ).all(axis=1) & (~(x.actual_opportunities.eq(0) & x.y.ne(0)))
    expected = (
        x.team_volume_component
        + x.player_share_component
        + x.player_efficiency_component
        + x.residual_stack_component
    )
    if not np.allclose(
        expected[x.decomposition_available],
        (x.adjusted - x.y)[x.decomposition_available],
    ):
        raise ValueError("Error decomposition does not reconcile")
    return x
