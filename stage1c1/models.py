"""Backbone-controlled point models and ONE common calibrated distribution."""

import copy
import numpy as np
from scipy import stats
from scipy.optimize import minimize
from scipy.special import logit, expit
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from stage1b.point_models import CareerMean
from stage1b1.models import LagBlend
from stage1b1.runner import point_policy, phases
from stage1b1.probability import student_cdf
from stage1b.metrics import week_block_interval
from stage1b.data import feature_columns, MARKETS
from stage1b.runner import probe_lines, probabilities
from stage1c1.data import CONTEXTS


def predict(b, d):
    mu = b["point"].predict(d[b["features"]])
    return np.maximum(mu, 0) if b["count"] else mu


class CommonCalibration:
    def __init__(self, penalty=0.01):
        self.penalty = penalty

    def fit(self, p, y):
        eps = np.finfo(float).eps
        x = logit(np.clip(np.asarray(p), eps, 1 - eps))
        y = np.asarray(y)

        def loss(ab):
            z = ab[0] * x + ab[1]
            return np.mean(np.logaddexp(0, z) - y * z) + self.penalty * (
                (ab[0] - 1) ** 2 + ab[1] ** 2
            )

        def gradient(ab):
            residual = expit(ab[0] * x + ab[1]) - y
            return np.array(
                [
                    np.mean(residual * x) + 2 * self.penalty * (ab[0] - 1),
                    np.mean(residual) + 2 * self.penalty * ab[1],
                ]
            )

        result = minimize(
            loss,
            [1.0, 0.0],
            jac=gradient,
            method="L-BFGS-B",
            bounds=[(0.25, 4.0), (-3.0, 3.0)],
        )
        if not result.success:
            raise ValueError("Common calibration failed")
        self.ab = result.x
        return self


def cdf(b, d):
    mu = predict(b, d)
    a, c = b["calibrator"].ab
    scale = b["scale"] * np.sqrt(3 / 5)

    def distribution(k):
        k = np.broadcast_to(np.asarray(k), mu.shape)
        z = (k + 0.5 - mu - b["bias"]) / scale
        # Stable log-CDF/log-survival preserves tails and agrees with inversion;
        # no artificial plateau from clipping a CDF at .00000001.
        value = expit(a * (stats.t.logcdf(z, 5) - stats.t.logsf(z, 5)) - c)
        return np.where(k < 0, 0, value) if b["count"] else value

    return distribution


def bounds(b, d, alpha=0.1):
    """Exact integer inverse of the SAME calibrated CDF used for pricing probes."""
    mu = predict(b, d)
    a, c = b["calibrator"].ab
    result = []
    for level in [alpha / 2, 1 - alpha / 2]:
        raw = expit((logit(level) + c) / a)
        q = np.ceil(
            mu + b["bias"] + b["scale"] * np.sqrt(3 / 5) * stats.t.ppf(raw, 5) - 0.5
        )
        result.append(np.maximum(q, 0) if b["count"] else q)
    return result


def choose(initial, selection, train, market, cols, backbone, p):
    if backbone == "b1" and market == "passing_yards":
        return point_policy(initial, selection, train, cols, p)
    if backbone == "b1":
        builders = {
            "career_mean": lambda: CareerMean(),
            "ridge": lambda: Ridge(alpha=1.0),
            "gradient_boosting": lambda: GradientBoostingRegressor(
                n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42
            ),
        }
    else:
        builders = {
            "career_mean": lambda: LagBlend(),
            "scaled_ridge100": lambda: make_pipeline(
                StandardScaler(), Ridge(alpha=100)
            ),
            "hist100": lambda: HistGradientBoostingRegressor(
                max_iter=100,
                max_leaf_nodes=7,
                min_samples_leaf=30,
                early_stopping=False,
                random_state=p["seed"],
            ),
        }
    baseline = abs(selection[cols[0]].to_numpy() - selection.y.to_numpy())
    winner = "career_mean"
    best = baseline.mean()
    rows = []
    for name, build in builders.items():
        m = build()
        if name != "career_mean":
            m.fit(initial[cols], initial.y)
        mu = m.predict(selection[cols])
        mu = np.maximum(mu, 0) if MARKETS[market][3] else mu
        err = abs(mu - selection.y.to_numpy())
        g = selection[["season", "week"]].copy()
        g["delta"] = err - baseline
        low, high = week_block_interval(g, "delta", reps=p["bootstrap_replicates"])
        admitted = (
            backbone == "b1"
            or name == "career_mean"
            or (
                g.week.nunique() >= 8
                and err.mean() < baseline.mean() * 0.98
                and high < 0
            )
        )
        rows.append(
            dict(
                candidate=name,
                mae=float(err.mean()),
                admitted=bool(admitted),
                low=low,
                high=high,
            )
        )
        if admitted and err.mean() < best:
            winner = name
            best = err.mean()
    m = builders[winner]()
    if winner != "career_mean":
        m.fit(train[cols], train.y)
    return m, winner, rows


def refit_fixed(point, train, cols):
    if isinstance(point, LagBlend):
        return LagBlend(tuple(point.weights))
    if isinstance(point, CareerMean):
        return CareerMean()
    return clone(point).fit(train[cols], train.y)


def fit(d, market, year, variant, p, archived):
    initial, psel, train, res, cal, selection, evaluation = phases(d, year, p)
    config = p["variants"][variant]
    cols = feature_columns(market) + CONTEXTS[config["context"]]
    if config.get("archived_point"):
        point = copy.deepcopy(archived["point"])
        method = "archived_" + type(point).__name__
        scores = []
    elif config.get("fixed_choice"):
        point = refit_fixed(archived["point"], train, cols)
        method = "fixed_" + type(point).__name__
        scores = []
    else:
        point, method, scores = choose(
            initial, psel, train, market, cols, config["backbone"], p
        )
    b = {
        "point": point,
        "point_method": method,
        "features": cols,
        "market": market,
        "year": year,
        "variant": variant,
        "count": MARKETS[market][3],
        "max_training_available_at": train.completed_at.max().isoformat(),
        "information_available_at": cal.completed_at.max().isoformat(),
        "probability_method": "fixed_student5_penalized_sigmoid",
        "backbone": config["backbone"],
        "context": config["context"],
        "source": config["source"],
    }
    error = res.y.to_numpy() - predict(b, res)
    b["bias"] = float(error.mean())
    b["scale"] = max(float(error.std()), 1e-3)
    lines = probe_lines(cal, market, p)
    pc = probabilities(
        student_cdf(predict(b, cal), b["bias"], b["scale"], b["count"]), lines
    )
    truth = (cal.y.to_numpy()[:, None] > lines).astype(int)
    b["calibrator"] = CommonCalibration(p["calibration_penalty"]).fit(
        pc.ravel(), truth.ravel()
    )
    info = dict(
        market=market,
        season=year,
        variant=variant,
        method=method,
        point_candidates=scores,
        training_max=b["max_training_available_at"],
        calibration_max=b["information_available_at"],
        diagnostic_selection_start=selection.prediction_at.min().isoformat(),
        evaluation_start=evaluation.prediction_at.min().isoformat(),
        phase_n=list(map(len, [initial, psel, train, res, cal, selection, evaluation])),
    )
    return b, info, evaluation, selection, train
