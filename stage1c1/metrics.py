"""Fixed full-population comparisons; RB receiving is prespecified, not selected."""

import numpy as np
import pandas as pd
from stage1b.metrics import week_block_interval

COMPARISONS = [
    ("b1_context", "b1_none"),
    ("c0_context", "c0_none"),
    ("c0_none", "b1_none"),
    ("b1_context", "c0_context"),
    ("b1_context", "b1_context_legacy"),
    ("b1_context", "b1_context_fixed"),
    ("b1_c1", "b1_none"),
    ("b1_c2", "b1_none"),
    ("b1_none", "frozen_b1"),
]


def summaries(f):
    rows = []
    for (market, tier, version), g in f.groupby(
        ["market", "evaluation_tier", "version"]
    ):
        for season, d in [("all", g)] + list(g.groupby("season")):
            e = d.projection - d.y
            rows.append(
                dict(
                    market=market,
                    evaluation_tier=tier,
                    version=version,
                    season=str(season),
                    cohort="all",
                    n=len(d),
                    mae=float(abs(e).mean()),
                    rmse=float(np.sqrt(np.mean(e**2))),
                    bias=float(e.mean()),
                    coverage90=float(((d.y >= d.lower90) & (d.y <= d.upper90)).mean()),
                    width90=float((d.upper90 - d.lower90).mean()),
                    interval_score90=float(d.interval_score.mean()),
                    zeros=int(d.y.eq(0).sum()),
                )
            )
    return pd.DataFrame(rows)


def paired(f, q, p):
    score = q.groupby(["row_id", "version"], as_index=False)[
        ["brier", "log_loss"]
    ].mean()
    z = f.merge(score, on=["row_id", "version"], validate="one_to_one")
    z["absolute_error"] = abs(z.projection - z.y)
    out = []
    for variant, reference in COMPARISONS:
        a = z[z.version.eq(variant)]
        b = z[z.version.eq(reference)]
        m = a.merge(
            b[["row_id", "absolute_error", "brier", "log_loss", "interval_score"]],
            on="row_id",
            suffixes=("", "_ref"),
            validate="one_to_one",
        )
        for (market, tier), g in m.groupby(["market", "evaluation_tier"]):
            for cohort, d in [("all", g)] + (
                [("RB_prespecified", g[g.position.eq("RB")])]
                if market == "receiving_yards"
                else []
            ):
                for metric in ["absolute_error", "brier", "log_loss", "interval_score"]:
                    d = d.copy()
                    d["delta"] = d[metric] - d[metric + "_ref"]
                    for block in [4, 8]:
                        lo, hi = week_block_interval(
                            d, "delta", reps=p["bootstrap_replicates"], block=block
                        )
                        out.append(
                            dict(
                                market=market,
                                evaluation_tier=tier,
                                cohort=cohort,
                                variant=variant,
                                reference=reference,
                                metric=metric,
                                week_block=block,
                                n=len(d),
                                delta=float(d.delta.mean()),
                                low=lo,
                                high=hi,
                            )
                        )
    # Factorial interaction on identical observations; not differences of unrelated means.
    for metric in ["absolute_error", "brier", "log_loss", "interval_score"]:
        w = z.pivot(index="row_id", columns="version", values=metric)
        d = z[z.version.eq("b1_none")][
            ["row_id", "market", "season", "week", "evaluation_tier", "position"]
        ].set_index("row_id")
        d = d.join(
            ((w.b1_context - w.b1_none) - (w.c0_context - w.c0_none)).rename("delta")
        )
        for (market, tier), g in d.groupby(["market", "evaluation_tier"]):
            for block in [4, 8]:
                lo, hi = week_block_interval(
                    g, "delta", reps=p["bootstrap_replicates"], block=block
                )
                out.append(
                    dict(
                        market=market,
                        evaluation_tier=tier,
                        cohort="all",
                        variant="factorial_interaction",
                        reference="(b1ctx-b1none)-(c0ctx-c0none)",
                        metric=metric,
                        week_block=block,
                        n=len(g),
                        delta=float(g.delta.mean()),
                        low=lo,
                        high=hi,
                    )
                )
    return pd.DataFrame(out)
