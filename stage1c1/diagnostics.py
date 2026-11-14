"""Inner-window feature sensitivity and source-only effective sample sizes."""

import numpy as np
import pandas as pd
from stage1c.context import KINDS
from stage1c.contracts import availability
from stage1c1.data import CONTEXTS
from stage1c1.models import predict


def feature_diagnostics(b, train, selection, p):
    if not (selection.season.eq(b["year"] - 1) & selection.week.between(11, 18)).all():
        raise ValueError("Feature diagnostics must use prior-year selection only")
    if not train.completed_at.max() < selection.prediction_at.min():
        raise ValueError("Diagnostic model training overlaps selection")
    cols = b["features"]
    context = (
        [x for x in cols if x not in cols[: len(cols) - len(CONTEXTS[b["context"]])]]
        if CONTEXTS[b["context"]]
        else []
    )
    # Explicit names prevent the zero-context slice from accidentally selecting all.
    context = list(CONTEXTS[b["context"]])
    base = abs(predict(b, selection) - selection.y.to_numpy()).mean()
    records = []
    rng = np.random.default_rng(p["permutation_seed"])
    for block, names in [("c1", CONTEXTS["c1_only"]), ("c2", CONTEXTS["c2_volume"])]:
        features = [x for x in names if x in context]
        if not features:
            continue
        for repeat in range(p["permutation_repeats"]):
            d = selection.copy()
            # Move a whole fixture-side/kind block together, never shuffle teammates
            # independently or use another season/week as a purported exchangeable row.
            for (_, _, kind), g in d.groupby(["season", "week", "kind"], sort=True):
                unique = g.drop_duplicates(["game_id", "team_key", "kind"])
                order = rng.permutation(len(unique))
                mapping = {
                    tuple(r): unique.iloc[j][features].to_numpy(float)
                    for r, j in zip(
                        unique[["game_id", "team_key", "kind"]].itertuples(
                            index=False, name=None
                        ),
                        order,
                    )
                }
                values = np.vstack(
                    [mapping[(r.game_id, r.team_key, r.kind)] for r in g.itertuples()]
                )
                d.loc[g.index, features] = values
            err = float(abs(predict(b, d) - d.y.to_numpy()).mean())
            records.append(
                dict(
                    market=b["market"],
                    season=b["year"],
                    variant=b["variant"],
                    block=block,
                    repeat=repeat,
                    baseline_mae=float(base),
                    permuted_mae=err,
                    delta_mae=err - base,
                    n=len(selection),
                    window="prior_year_weeks11to18_ONLY",
                    information_max=selection.completed_at.max().isoformat(),
                    context_used=not type(b["point"]).__name__
                    in ["CareerMean", "LagBlend"],
                )
            )
    x = train[cols]
    corr = x.corr()
    redundancy = []
    for i, a in enumerate(cols):
        for z in cols[i + 1 :]:
            if a not in context and z not in context:
                continue
            value = corr.loc[a, z]
            if pd.notna(value) and abs(value) >= 0.95:
                redundancy.append(
                    dict(
                        market=b["market"],
                        season=b["year"],
                        variant=b["variant"],
                        feature=a,
                        other=z,
                        correlation=float(value),
                        window="point_training_ONLY",
                    )
                )
    weights = []
    point = b["point"]
    coef = None
    if hasattr(point, "named_steps"):
        last = list(point.named_steps.values())[-1]
        if hasattr(last, "coef_"):
            transformed = x
            for step in list(point.named_steps.values())[:-1]:
                transformed = step.transform(transformed)
            coef = np.asarray(last.coef_) * np.std(np.asarray(transformed), axis=0)
    elif hasattr(point, "coef_"):
        coef = np.asarray(point.coef_) * x.std(ddof=0).to_numpy()
    for j, name in enumerate(cols):
        weights.append(
            dict(
                market=b["market"],
                season=b["year"],
                variant=b["variant"],
                feature=name,
                is_context=name in context,
                training_std=float(x[name].std(ddof=0)),
                standardized_coefficient=float(coef[j]) if coef is not None else np.nan,
                coefficient_available=coef is not None,
                window="point_training_ONLY",
            )
        )
    return records, redundancy, weights


def effective_samples(games, rates, context):
    g = games.copy()
    g["evidence_tier"] = "retrospective"
    g["available"] = g.apply(lambda r: availability(r, lag_hours=36), axis=1)
    grid = g.merge(pd.DataFrame({"kind": list(KINDS)}), how="cross").merge(
        rates,
        on=["game_id", "team", "kind"],
        how="left",
        suffixes=("", "_rate"),
        validate="one_to_one",
    )
    grid["valid"] = False
    grid["exposure"] = 0.0
    for kind, (target, opp) in KINDS.items():
        mask = grid.kind.eq(kind)
        catch = (
            "completions"
            if kind == "pass"
            else "receptions"
            if kind.startswith("rec")
            else None
        )
        cols = [target, opp] + ([catch] if catch else [])
        valid = np.isfinite(grid.loc[mask, cols]).all(axis=1)
        grid.loc[mask, "valid"] = valid.to_numpy()
        grid.loc[mask, "exposure"] = grid.loc[mask, opp].fillna(0).to_numpy()
    updates = list(grid.groupby("available", sort=True))
    index = 0
    acc = {}
    rows = []
    for decision, fixtures in context.groupby("prediction_at", sort=True):
        while index < len(updates) and updates[index][0] < decision:
            for r in updates[index][1].itertuples():
                key = (r.opponent, r.kind)
                a = acc.setdefault(
                    key,
                    dict(w=0.0, w2=0.0, exposure=0.0, valid_n=0, total_n=0, last=None),
                )
                a["w"] *= 0.9
                a["w2"] *= 0.81
                a["exposure"] *= 0.9
                a["total_n"] += 1
                if r.valid:
                    a["w"] += 1
                    a["w2"] += 1
                    a["exposure"] += r.exposure
                    a["valid_n"] += 1
                    a["last"] = r.kickoff_at
            index += 1
        for r in fixtures.itertuples():
            a = acc.get(
                (r.opponent, r.kind),
                dict(w=0.0, w2=0.0, exposure=0.0, valid_n=0, total_n=0, last=None),
            )
            rows.append(
                dict(
                    game_id=r.game_id,
                    team=r.team,
                    kind=r.kind,
                    prediction_at=decision,
                    weighted_games=a["w"],
                    kish_game_ess=a["w"] ** 2 / a["w2"] if a["w2"] else 0,
                    weighted_opportunities=a["exposure"],
                    known_games=a["valid_n"],
                    total_games=a["total_n"],
                    days_since_valid=(decision - a["last"]).total_seconds() / 86400
                    if a["last"] is not None
                    else np.nan,
                )
            )
    return pd.DataFrame(rows)
