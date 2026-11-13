"""Portable point estimators and count thinning without actual future trials."""

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class LagBlend:
    def __init__(self, weights=(1.0, 0.0, 0.0)):
        self.weights = np.asarray(weights, dtype=float)

    def predict(self, x):
        return np.asarray(x)[:, :3] @ self.weights


class CompletionThinning:
    """A~NB2, C|A~Binomial(A,p); marginal C~NB2(mean(A)*p, alpha).

    Actual attempts are historical supervised labels only, NEVER inference inputs.
    """

    def fit(self, x, attempts, completions):
        a = np.asarray(attempts, dtype=float)
        c = np.asarray(completions, dtype=float)
        if (
            not np.isfinite(a).all()
            or not np.isfinite(c).all()
            or (a < c).any()
            or (c < 0).any()
        ):
            raise ValueError("Invalid historical joint completion/attempt labels")
        self.attempt_model = make_pipeline(
            StandardScaler(), PoissonRegressor(alpha=1.0, max_iter=500)
        ).fit(x, a)
        self.scaler = StandardScaler().fit(x)
        z = np.column_stack([np.ones(len(x)), self.scaler.transform(x)])

        def loss(beta):
            t = z @ beta
            return (a * np.logaddexp(0, t) - c * t).sum() / max(
                a.sum(), 1
            ) + 0.01 * np.sum(beta[1:] ** 2)

        fit = minimize(loss, np.zeros(z.shape[1]), method="L-BFGS-B")
        if not fit.success:
            raise ValueError("Binomial completion-rate optimisation failed")
        self.beta = fit.x
        return self

    def predict(self, x):
        z = np.column_stack([np.ones(len(x)), self.scaler.transform(x)])
        return self.attempt_model.predict(x) * expit(z @ self.beta)

    def attempt_mean(self, x):
        return self.attempt_model.predict(x)
