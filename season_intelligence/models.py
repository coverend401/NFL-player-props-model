"""Fixed player-first comparators, fitted only on prior available outcomes."""

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from stage1b.data import MARKETS

from .data import columns


class PointModel:
    def __init__(self, market, family):
        self.market, self.family = market, family
        self.columns = columns(market, family)

    def fit(self, d):
        target = MARKETS[self.market][0]
        if self.family != "recent_shrunk":
            estimator = (
                HistGradientBoostingRegressor(
                    loss="absolute_error",
                    max_iter=100,
                    max_leaf_nodes=15,
                    l2_regularization=100,
                    min_samples_leaf=50,
                    random_state=221126,
                )
                if self.family == "context_tree"
                else Ridge(alpha=100)
            )
            self.model = make_pipeline(
                SimpleImputer(
                    strategy="median", add_indicator=True, keep_empty_features=True
                ),
                StandardScaler(),
                estimator,
            ).fit(d[self.columns], d[target])
        self.fit_before = d.available_at.max().isoformat()
        return self

    def predict(self, d):
        if self.family == "recent_shrunk":
            target = MARKETS[self.market][0]
            n = d[target + "_season_n"].fillna(0).clip(upper=5)
            recent = (d[target + "_last3"] + d[target + "_last5"]) / 2
            mu = (n * recent + 4 * d[target + "_career"]) / (n + 4)
            mu = mu.fillna(d[target + "_career"]).to_numpy()
        else:
            mu = self.model.predict(d[self.columns])
        if MARKETS[self.market][3]:
            mu = np.maximum(mu, 0)
        return np.asarray(mu, dtype=float)
