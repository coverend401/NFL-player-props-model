"""Paired point and 90% predictive-interval comparisons in original market units."""

import numpy as np
import pandas as pd
from stage1b.metrics import week_block_interval


def summaries(f, protocol):
    rows = []
    differences = []
    for (market, tier), period in f.groupby(["market", "evaluation_tier"]):
        for season, d in [("all", period)] + list(period.groupby("season")):
            for version, point, lo, hi, score in [
                (
                    "stage1b",
                    "stage1b_projection",
                    "stage1b_lower90",
                    "stage1b_upper90",
                    "stage1b_interval_score",
                ),
                ("stage1b1", "projection", "lower90", "upper90", "interval_score"),
            ]:
                e = d[point] - d.y
                rows.append(
                    dict(
                        market=market,
                        evaluation_tier=tier,
                        season=str(season),
                        version=version,
                        n=len(d),
                        mae=float(abs(e).mean()),
                        rmse=float(np.sqrt(np.mean(e**2))),
                        bias=float(e.mean()),
                        naive_mae=float(abs(d.naive - d.y).mean()),
                        coverage90=float(((d.y >= d[lo]) & (d.y <= d[hi])).mean()),
                        width90=float((d[hi] - d[lo]).mean()),
                        interval_score90=float(d[score].mean()),
                        zeros=int(d.y.eq(0).sum()),
                    )
                )
        d = period.copy()
        for name, values in [
            ("mae", abs(d.projection - d.y) - abs(d.stage1b_projection - d.y)),
            ("interval_score", d.interval_score - d.stage1b_interval_score),
            ("width", d.upper90 - d.lower90 - (d.stage1b_upper90 - d.stage1b_lower90)),
        ]:
            d["delta"] = values
            lo, hi = week_block_interval(
                d,
                "delta",
                reps=protocol["bootstrap_replicates"],
                block=protocol["bootstrap_week_block"],
            )
            differences.append(
                dict(
                    market=market,
                    evaluation_tier=tier,
                    metric=name,
                    n=len(d),
                    delta=float(values.mean()),
                    low=lo,
                    high=hi,
                )
            )
    return pd.DataFrame(rows), pd.DataFrame(differences)
