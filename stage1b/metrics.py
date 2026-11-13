"""Proper scores, descriptive cohorts, and paired week-block uncertainty."""

import numpy as np
import pandas as pd
from scipy.stats import norm


def binary_scores(p, y):
    p, y = np.asarray(p), np.asarray(y)
    if p.shape != y.shape or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid probability array")
    q = np.clip(p, 1e-9, 1 - 1e-9)
    return (p - y) ** 2, -(y * np.log(q) + (1 - y) * np.log1p(-q))


def wilson(wins, n):
    if n <= 0:
        return np.nan, np.nan
    z = norm.ppf(0.975)
    p = wins / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def reliability(probes):
    d = probes.copy()
    d["band"] = np.minimum((d.probability * 10).astype(int), 9)
    rows = []
    for keys, g in d.groupby(["market", "version", "evaluation_tier", "band"]):
        low, high = wilson(g.event.sum(), len(g))
        rows.append(
            dict(
                zip(["market", "version", "evaluation_tier", "band"], keys),
                n_probes=len(g),
                n_player_games=g.row_id.nunique(),
                mean_probability=float(g.probability.mean()),
                observed=float(g.event.mean()),
                brier=float(g.brier.mean()),
                log_loss=float(g.log_loss.mean()),
                descriptive_wilson_low=low,
                descriptive_wilson_high=high,
            )
        )
    return pd.DataFrame(rows)


def week_block_interval(frame, column, seed=41017, reps=500, block=4):
    """Resample 4-week blocks, retaining unequal week sizes and within-week dependence."""
    g = frame.groupby(["season", "week"], sort=True)[column].agg(["sum", "count"])
    if len(g) < 4:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    n = len(g)
    starts = rng.integers(
        0, max(1, n - block + 1), size=(reps, int(np.ceil(n / block)))
    )
    idx = (starts[..., None] + np.arange(block)).reshape(reps, -1)[:, :n]
    idx = np.minimum(idx, n - 1)
    values = g["sum"].to_numpy()[idx].sum(axis=1) / g["count"].to_numpy()[idx].sum(
        axis=1
    )
    return tuple(float(x) for x in np.quantile(values, [0.025, 0.975]))


def accuracy(forecasts):
    rows = []
    for market, d in forecasts.groupby("market"):
        for season, seasonal in [("all_development", d[d.season < 2026])] + list(
            d.groupby("season")
        ):
            cohorts = [
                ("all", seasonal),
                ("limited_history", seasonal[seasonal.games_played_prior < 8]),
                ("established", seasonal[seasonal.games_played_prior >= 8]),
                ("returning_21d", seasonal[seasonal.returning]),
                ("observed_zero", seasonal[seasonal.y == 0]),
            ]
            for cohort, g in cohorts:
                if g.empty:
                    continue
                err = g.projection - g.y
                rows.append(
                    dict(
                        market=market,
                        season=str(season),
                        cohort=cohort,
                        n=len(g),
                        mae=float(err.abs().mean()),
                        rmse=float(np.sqrt(np.mean(err**2))),
                        bias=float(err.mean()),
                        naive_mae=float((g.naive - g.y).abs().mean()),
                        zero_rate=float(g.y.eq(0).mean()),
                        interval90_coverage=float(
                            ((g.y >= g.lower90) & (g.y <= g.upper90)).mean()
                        ),
                        interval90_width=float((g.upper90 - g.lower90).mean()),
                        quantile10_pinball=float(
                            np.maximum(0.1 * (g.y - g.q10), -0.9 * (g.y - g.q10)).mean()
                        ),
                        quantile90_pinball=float(
                            np.maximum(0.9 * (g.y - g.q90), -0.1 * (g.y - g.q90)).mean()
                        ),
                    )
                )
    return pd.DataFrame(rows)


def probability_summary(probes, protocol):
    rows = []
    # Average the three dependent thresholds per player-game before inference.
    d = probes.groupby(
        ["market", "version", "evaluation_tier", "season", "week", "row_id"],
        as_index=False,
    )[["brier", "log_loss"]].mean()
    for (market, version, tier), period in d.groupby(
        ["market", "version", "evaluation_tier"]
    ):
        for season, g in [("all", period)] + list(period.groupby("season")):
            lo, hi = week_block_interval(
                g,
                "brier",
                reps=protocol["bootstrap_replicates"],
                block=protocol["bootstrap_week_block"],
            )
            rows.append(
                dict(
                    market=market,
                    version=version,
                    evaluation_tier=tier,
                    season=str(season),
                    n=len(g),
                    brier=float(g.brier.mean()),
                    log_loss=float(g.log_loss.mean()),
                    brier_low=lo,
                    brier_high=hi,
                )
            )
    return pd.DataFrame(rows)


def paired_improvements(probes, protocol):
    d = probes.groupby(
        ["market", "version", "evaluation_tier", "season", "week", "row_id"],
        as_index=False,
    )[["brier", "log_loss"]].mean()
    a = d[d.version.eq("stage1a_normal_rule")].drop(columns="version")
    b = d[d.version.eq("selected_stage1b")].drop(columns="version")
    joined = a.merge(
        b,
        on=["market", "evaluation_tier", "season", "week", "row_id"],
        suffixes=("_baseline", "_selected"),
        validate="one_to_one",
    )
    rows = []
    for (market, tier), g in joined.groupby(["market", "evaluation_tier"]):
        g = g.copy()
        g["delta_brier"] = g.brier_selected - g.brier_baseline
        g["delta_log_loss"] = g.log_loss_selected - g.log_loss_baseline
        lo, hi = week_block_interval(
            g,
            "delta_brier",
            reps=protocol["bootstrap_replicates"],
            block=protocol["bootstrap_week_block"],
        )
        rows.append(
            dict(
                market=market,
                evaluation_tier=tier,
                n=len(g),
                delta_brier=float(g.delta_brier.mean()),
                delta_log_loss=float(g.delta_log_loss.mean()),
                delta_brier_low=lo,
                delta_brier_high=hi,
            )
        )
    return pd.DataFrame(rows)
