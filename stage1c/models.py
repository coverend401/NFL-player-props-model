"""Direct contextual regression and common proper-score wrapper, not C3–C6."""

import numpy as np
from scipy import stats
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from stage1b1.models import LagBlend
from stage1b1.probability import (
    student_cdf,
    mix_cdf,
    ShrunkSigmoid,
    interval_score,
    conformal_offset,
)
from stage1b.runner import probe_lines, probabilities
from stage1b.metrics import binary_scores, week_block_interval
from stage1b1.runner import phases
from stage1b.data import feature_columns, MARKETS
from stage1c.context import FAMILIES


def point_predict(b, d):
    mu = b["point"].predict(d[b["features"]])
    return np.maximum(mu, 0) if b["count"] else mu


def curve(b, d, key, weight=0.15):
    kind, cal = key.split("|")
    mu = point_predict(b, d)
    anchor = student_cdf(mu, b["bias"], b["scale"], b["count"])
    if kind == "student":
        base = anchor
    elif kind == "normal":

        def base(t):
            q = stats.norm.cdf(np.asarray(t) + 0.5, mu + b["bias"], b["scale"])
            return np.where(np.asarray(t) < 0, 0, q) if b["count"] else q
    elif kind == "empirical":
        spread = np.sqrt(np.maximum(mu, 1)) if b["count"] else np.maximum(abs(mu), 10)

        def base(t):
            q = np.searchsorted(
                b["errors"], (np.asarray(t) + 0.5 - mu) / spread, side="left"
            ) / len(b["errors"])
            return np.where(np.asarray(t) < 0, 0, q) if b["count"] else q
    else:
        raise ValueError("Unknown C0-C2 CDF")
    if cal == "sigmoid":
        base = b["calibrators"][key].cdf(base)
    return mix_cdf(base, anchor, weight)


def interval(b, d, kind):
    mu = point_predict(b, d)
    if kind == "normal":
        lo = mu + b["bias"] - stats.norm.ppf(0.95) * b["scale"]
        hi = mu + b["bias"] + stats.norm.ppf(0.95) * b["scale"]
    elif kind == "cqr":
        qs = np.sort(
            np.column_stack([q.predict(d[b["features"]]) for q in b["quantiles"]]),
            axis=1,
        )
        lo = qs[:, 0] - b["cqr_offset"]
        hi = qs[:, 1] + b["cqr_offset"]
    else:
        raise ValueError("Unknown interval")
    lo = np.floor(lo)
    hi = np.ceil(hi)
    return (np.maximum(lo, 0) if b["count"] else lo), hi


def fit(d, market, year, family, p):
    initial, select, train, res, cal, selection, evaluation = phases(d, year, p)
    cols = feature_columns(market) + FAMILIES[family]

    def build(name):
        if name == "career_mean":
            return LagBlend()
        if name == "scaled_ridge100":
            return make_pipeline(StandardScaler(), Ridge(alpha=100))
        return HistGradientBoostingRegressor(
            max_iter=100,
            max_leaf_nodes=7,
            min_samples_leaf=30,
            early_stopping=False,
            random_state=p["seed"],
        )

    scores = []
    best = "career_mean"
    err0 = np.abs(select[cols[0]].to_numpy() - select.y.to_numpy())
    best_mae = err0.mean()
    for name in p["point_candidates"]:
        m = build(name)
        if name != "career_mean":
            m.fit(initial[cols], initial.y)
        pred = m.predict(select[cols])
        pred = np.maximum(pred, 0) if MARKETS[market][3] else pred
        error = abs(pred - select.y.to_numpy())
        g = select[["season", "week"]].copy()
        g["delta"] = error - err0
        low, high = week_block_interval(g, "delta", reps=p["bootstrap_replicates"])
        accepted = name == "career_mean" or (
            g.week.nunique() >= p["minimum_gate_weeks"]
            and error.mean() < err0.mean() * (1 - p["point_minimum_relative_gain"])
            and high < 0
        )
        scores.append(
            dict(
                name=name,
                mae=float(error.mean()),
                accepted=bool(accepted),
                low=low,
                high=high,
            )
        )
        if accepted and error.mean() < best_mae:
            best = name
            best_mae = error.mean()
    m = build(best)
    if best != "career_mean":
        m.fit(train[cols], train.y)
    b = {
        "point": m,
        "features": cols,
        "point_method": best,
        "market": market,
        "year": year,
        "family": family,
        "count": MARKETS[market][3],
        "quantiles": [],
        "calibrators": {},
        "max_training_available_at": train.completed_at.max().isoformat(),
        "information_available_at": selection.completed_at.max().isoformat(),
    }
    for level in [0.05, 0.95]:
        q = HistGradientBoostingRegressor(
            loss="quantile",
            quantile=level,
            max_iter=100,
            max_leaf_nodes=7,
            min_samples_leaf=30,
            early_stopping=False,
            random_state=p["seed"],
        ).fit(train[cols], train.y)
        b["quantiles"].append(q)
    mu = point_predict(b, res)
    error = res.y.to_numpy() - mu
    b.update(
        bias=float(error.mean()),
        scale=max(float(error.std()), 1e-3),
        errors=np.sort(
            error
            / (np.sqrt(np.maximum(mu, 1)) if b["count"] else np.maximum(abs(mu), 10))
        ),
    )
    lines = probe_lines(cal, market, p)
    truth = (cal.y.to_numpy()[:, None] > lines).astype(int)
    anchor = probabilities(
        student_cdf(point_predict(b, cal), b["bias"], b["scale"], b["count"]), lines
    )
    losses = {}
    bscores = {}
    candidates = []
    slines = probe_lines(selection, market, p)
    sy = (selection.y.to_numpy()[:, None] > slines).astype(int)
    for kind in ["normal", "student", "empirical"]:
        pc = probabilities(curve(b, cal, kind + "|identity", weight=0), lines)
        b["calibrators"][kind + "|sigmoid"] = ShrunkSigmoid().fit(
            pc.ravel(), truth.ravel(), anchor.ravel(), 0.15
        )
        for method in ["identity", "sigmoid"]:
            key = kind + "|" + method
            bs, ll = binary_scores(probabilities(curve(b, selection, key), slines), sy)
            losses[key] = ll.mean(axis=1)
            bscores[key] = bs.mean(axis=1)
    chosen = "normal|identity"
    loss = losses[chosen].mean()
    for key, ll in losses.items():
        g = selection[["season", "week"]].copy()
        g["delta"] = ll - losses["normal|identity"]
        low, high = week_block_interval(g, "delta", reps=p["bootstrap_replicates"])
        accept = key == "normal|identity" or (
            g.week.nunique() >= p["minimum_gate_weeks"]
            and high < 0
            and losses["normal|identity"].mean() - ll.mean() >= 0.005
            and bscores[key].mean() <= bscores["normal|identity"].mean()
        )
        candidates.append(
            dict(
                key=key,
                log_loss=float(ll.mean()),
                brier=float(bscores[key].mean()),
                accepted=bool(accept),
                low=low,
                high=high,
            )
        )
        if accept and ll.mean() < loss:
            chosen = key
            loss = ll.mean()
    b["selected_probability"] = chosen
    cq = np.sort(
        np.column_stack([q.predict(cal[cols]) for q in b["quantiles"]]), axis=1
    )
    b["cqr_offset"] = float(
        np.ceil(conformal_offset(cal.y, np.floor(cq[:, 0]), np.ceil(cq[:, 1])))
    )
    info = {}
    for key in ["normal", "cqr"]:
        lo, hi = interval(b, selection, key)
        info[key] = dict(
            score=float(interval_score(selection.y, lo, hi).mean()),
            coverage=float(((selection.y >= lo) & (selection.y <= hi)).mean()),
        )
    b["selected_interval"] = (
        "cqr"
        if info["cqr"]["score"] < info["normal"]["score"] * 0.99
        and info["cqr"]["coverage"] >= 0.85
        else "normal"
    )
    meta = dict(
        market=market,
        season=year,
        family=family,
        point=best,
        probability=chosen,
        interval=b["selected_interval"],
        point_candidates=scores,
        probability_candidates=candidates,
        interval_candidates=info,
        phase_n=list(
            map(len, [initial, select, train, res, cal, selection, evaluation])
        ),
        train_max=b["max_training_available_at"],
        selection_max=b["information_available_at"],
        first_evaluation=evaluation.prediction_at.min().isoformat(),
    )
    return b, meta, evaluation
