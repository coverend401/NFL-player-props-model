"""Independent experimental conditional-CDF models; no deployed model is modified."""

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression

from stage1b.data import MARKETS

NEW = [
    "direct_classifier",
    "quantile_cdf",
    "distribution_forest",
    "workload_production",
    "player_consistency",
    "validated_ensemble",
]
REFERENCES = ["champion_normal", "existing_research", "threshold_prior"]
EPS = 1e-6


def features(frame, market):
    target, _, opp, _ = MARKETS[market]
    wanted = [
        "lag_anchor",
        "known_scale",
        "history_n",
        "days_rest",
        "offense_pct_last3",
        "offense_pct_career",
        "role_snap_change",
        "known_team_continuity",
        "efficiency3",
        "efficiency_career",
        "own_plays",
        "own_attempts",
        "own_carries",
        "own_pass_rate",
        "own_pace",
        "opp_allowed_plays",
        "opp_allowed_attempts",
        "opp_allowed_carries",
        "opp_pass_rate",
        "own_margin",
        "opp_margin",
        "is_home",
    ]
    wanted += [
        stat + lag
        for stat in dict.fromkeys([target, opp])
        for lag in [
            "_career",
            "_last3",
            "_last5",
            "_season",
            "_sd5",
            "_share3",
            "_share5",
            "_share_sd5",
        ]
    ]
    return list(dict.fromkeys(c for c in wanted if c in frame.columns))


def thresholds(train):
    residual = train.y - train.lag_anchor
    return np.quantile(residual, [0.2, 0.5, 0.8])


def proposals(frame, offsets):
    parts = []
    for level, offset in enumerate(offsets):
        part = frame.copy()
        part["threshold_level"] = level
        part["research_line"] = np.maximum(
            0.5, np.floor(part.lag_anchor + offset) + 0.5
        )
        part["observed_over"] = part.y.gt(part.research_line).astype(int)
        parts.append(part)
    d = pd.concat(parts, ignore_index=True)
    return d.drop_duplicates(
        ["game_id", "player_id", "market", "research_line"]
    ).reset_index(drop=True)


def loss_metrics(frame, column):
    p = np.clip(frame[column].to_numpy(float), EPS, 1 - EPS)
    y = frame.observed_over.to_numpy(float)
    weights = (
        1
        / frame.groupby(["game_id", "player_id", "market"])[column]
        .transform("size")
        .to_numpy()
    )
    bands = np.minimum((p * 10).astype(int), 9)
    ece = 0.0
    for band in np.unique(bands):
        mask = bands == band
        ece += (
            abs(np.average(p[mask] - y[mask], weights=weights[mask]))
            * weights[mask].sum()
            / weights.sum()
        )
    return {
        "n_thresholds": len(frame),
        "player_markets": int(
            frame[["game_id", "player_id", "market"]].drop_duplicates().shape[0]
        ),
        "brier": float(np.average((p - y) ** 2, weights=weights)),
        "log_loss": float(
            np.average(-(y * np.log(p) + (1 - y) * np.log1p(-p)), weights=weights)
        ),
        "exceedance_accuracy": float(np.average((p >= 0.5) == y, weights=weights)),
        "calibration_gap": float(ece),
    }


class Calibrator:
    def fit(self, score, labels, weights, *, probabilistic=False):
        x = np.asarray(score, float)
        y = np.asarray(labels, float)
        w = np.asarray(weights, float)
        if probabilistic:
            prior = np.linspace(0.05, 0.95, 10)
            x = np.r_[x, prior]
            y = np.r_[y, prior]
            w = np.r_[w, np.full(10, 10.0)]
        self.model = IsotonicRegression(
            y_min=EPS, y_max=1 - EPS, out_of_bounds="clip"
        ).fit(x, y, sample_weight=w)
        return self

    def predict(self, score):
        return self.model.predict(np.asarray(score, float))


class ThresholdModels:
    def __init__(self, market, policy):
        self.market, self.policy = market, policy

    def x(self, frame):
        x = frame[self.cols].copy()
        x["position_code"] = frame.position.map({"QB": 0, "RB": 1, "WR": 2, "TE": 3})
        return self.imputer.transform(x)

    def boosted(self, **extra):
        return HistGradientBoostingRegressor(
            max_iter=self.policy["boost_iterations"],
            max_leaf_nodes=self.policy["boost_leaves"],
            l2_regularization=self.policy["boost_l2"],
            min_samples_leaf=30,
            random_state=self.policy["seed"],
            **extra,
        )

    def fit(self, train, calibration):
        self.cols = features(train, self.market)
        raw = train[self.cols].copy()
        raw["position_code"] = train.position.map({"QB": 0, "RB": 1, "WR": 2, "TE": 3})
        self.imputer = SimpleImputer(
            strategy="median", add_indicator=True, keep_empty_features=True
        ).fit(raw)
        x = self.x(train)
        self.offsets = thresholds(train)
        tp = proposals(train, self.offsets)
        tx = self.classifier_x(tp)
        weights = (
            1
            / tp.groupby(["game_id", "player_id"])
            .research_line.transform("size")
            .to_numpy()
        )
        self.classifier = HistGradientBoostingClassifier(
            max_iter=self.policy["boost_iterations"],
            max_leaf_nodes=self.policy["boost_leaves"],
            l2_regularization=self.policy["boost_l2"],
            min_samples_leaf=30,
            monotonic_cst=[0] * (tx.shape[1] - 1) + [-1],
            random_state=self.policy["seed"],
        ).fit(tx, tp.observed_over, sample_weight=weights)
        self.quantiles = [
            self.boosted(loss="quantile", quantile=q).fit(x, train.y)
            for q in self.policy["quantiles"]
        ]
        self.forest = RandomForestRegressor(
            n_estimators=self.policy["forest_trees"],
            max_depth=self.policy["forest_depth"],
            min_samples_leaf=self.policy["forest_min_leaf"],
            max_features=0.8,
            n_jobs=1,
            random_state=self.policy["seed"],
        ).fit(x, train.y)
        leaves = self.forest.apply(x)
        self.leaf_values = []
        for i in range(leaves.shape[1]):
            self.leaf_values.append(
                {
                    leaf: np.sort(train.y.to_numpy()[leaves[:, i] == leaf])
                    for leaf in np.unique(leaves[:, i])
                }
            )
        valid = train.observed_opportunity.notna() & train.observed_opportunity.ge(0)
        if (
            valid.sum() < 100
            or not train.loc[valid, "observed_opportunity"].gt(0).any()
        ):
            raise ValueError(
                "Insufficient observed training opportunities; no outcome imputation"
            )
        self.workload = self.boosted(loss="poisson").fit(
            x[valid], train.loc[valid, "observed_opportunity"]
        )
        target, _, opp, _ = MARKETS[self.market]
        self.production = None
        if target != opp:
            productive = valid & train.observed_opportunity.gt(0)
            rate = (
                train.loc[productive, "y"]
                / train.loc[productive, "observed_opportunity"]
            )
            self.production = self.boosted(loss="squared_error").fit(
                x[productive],
                rate,
                sample_weight=train.loc[productive, "observed_opportunity"],
            )
        residual = train.y - train.lag_anchor
        self.player = (
            pd.DataFrame({"player_id": train.player_id, "residual": residual})
            .groupby("player_id")
            .residual.agg(["count", "mean", "var"])
        )
        self.positions = (
            pd.DataFrame({"position": train.position, "square": residual**2})
            .groupby("position")
            .square.mean()
            .to_dict()
        )
        self.global_var = max(float((residual**2).mean()), 1.0)
        self.priors = tp.groupby("threshold_level").observed_over.mean().to_dict()
        cp = proposals(calibration, self.offsets)
        raw_scores = self.raw_scores(cp)
        cw = (
            1
            / cp.groupby(["game_id", "player_id"])
            .research_line.transform("size")
            .to_numpy()
        )
        self.maps = {
            name: Calibrator().fit(
                raw_scores[name],
                cp.observed_over,
                cw,
                probabilistic=name in ["direct_classifier", "distribution_forest"],
            )
            for name in NEW[:-1]
        }
        self.fit_details = {
            "train_rows": len(train),
            "calibration_rows": len(calibration),
            "training_opportunity_missing": int((~valid).sum()),
            "efficiency_excluded_zero_or_missing_opportunity": int(
                (~(valid & train.observed_opportunity.gt(0))).sum()
            ),
            "threshold_offsets": self.offsets.tolist(),
            "features": self.cols,
            "methods_fitted_before": str(calibration.prediction_at.min()),
        }
        return self

    def classifier_x(self, frame):
        gap = (frame.research_line - frame.lag_anchor) / frame.known_scale.clip(lower=1)
        return np.column_stack([self.x(frame), gap])

    def raw_scores(self, frame):
        x = self.x(frame)
        line = frame.research_line.to_numpy()
        qs = np.sort(np.column_stack([m.predict(x) for m in self.quantiles]), axis=1)
        quantile = (qs[:, 1] - line) / np.maximum(qs[:, 2] - qs[:, 0], 1.0)
        leaves = self.forest.apply(x)
        forest = np.zeros(len(frame))
        for i, table in enumerate(self.leaf_values):
            for leaf in np.unique(leaves[:, i]):
                mask = leaves[:, i] == leaf
                ys = table[leaf]
                forest[mask] += 1 - np.searchsorted(ys, line[mask], side="right") / len(
                    ys
                )
        forest /= len(self.leaf_values)
        volume = np.maximum(self.workload.predict(x), 0)
        rate = (
            np.ones(len(frame))
            if self.production is None
            else self.production.predict(x)
        )
        target, _, opp, count = MARKETS[self.market]
        if count and target != opp:
            rate = np.clip(rate, 0, 1)
        mu = volume * rate
        scale = (
            frame[MARKETS[self.market][0] + "_sd5"]
            .fillna(frame.known_scale)
            .clip(lower=1)
            .to_numpy()
        )
        stage = (mu - line) / scale
        effect = frame.player_id.map(self.player["mean"]).fillna(0).to_numpy()
        n = frame.player_id.map(self.player["count"]).fillna(0).to_numpy()
        pv = frame.player_id.map(self.player["var"]).to_numpy()
        prior = frame.position.map(self.positions).fillna(self.global_var).to_numpy()
        pv = np.where(np.isfinite(pv), pv, prior)
        shrunk = (n * pv + 10 * prior) / (n + 10)
        consistency = (
            frame.lag_anchor.to_numpy() + n / (n + 10) * effect - line
        ) / np.sqrt(np.maximum(shrunk, 1.0))
        return {
            "direct_classifier": self.classifier.predict_proba(
                self.classifier_x(frame)
            )[:, 1],
            "quantile_cdf": quantile,
            "distribution_forest": forest,
            "workload_production": stage,
            "player_consistency": consistency,
        }

    def predict(self, frame):
        scores = self.raw_scores(frame)
        return {
            name: np.clip(self.maps[name].predict(scores[name]), EPS, 1 - EPS)
            for name in NEW[:-1]
        }

    def interval(self, frame):
        return np.sort(
            np.column_stack([m.predict(self.x(frame)) for m in self.quantiles]), axis=1
        )


def normal_reference(frame):
    return np.clip(
        norm.sf(
            frame.research_line,
            loc=frame.baseline,
            scale=frame.champion_sigma.clip(lower=1e-6),
        ),
        EPS,
        1 - EPS,
    )
