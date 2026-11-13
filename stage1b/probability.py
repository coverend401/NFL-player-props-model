"""Integer-support predictive CDFs and monotone, separately fitted calibration."""

import numpy as np
from scipy import stats
from scipy.special import expit, logit
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression

EPS = 1e-9


def outcomes(cdf, line):
    """Strict over/under and exact push, including negative yardage and zero."""
    line = np.asarray(line, dtype=float)
    if not np.isfinite(line).all():
        raise ValueError("Nonfinite line")
    upper = np.clip(cdf(np.floor(line)), 0, 1)
    lower = np.clip(cdf(np.ceil(line) - 1), 0, 1)
    if np.any(lower > upper + 1e-9):
        raise ValueError("Nonmonotone predictive CDF")
    return np.stack([1 - upper, lower, np.maximum(upper - lower, 0)], axis=-1)


class Calibration:
    def __init__(self, method="identity"):
        self.method = method

    def fit(self, p, y):
        p = np.asarray(p)
        y = np.asarray(y)
        if len(p) < 30 or len(np.unique(y)) < 2 or self.method == "identity":
            self.method = "identity"
        elif self.method == "sigmoid":
            x = logit(np.clip(p, EPS, 1 - EPS))

            def loss(ab):
                z = ab[0] * x + ab[1]
                return np.mean(np.logaddexp(0, z) - y * z)

            fit = minimize(loss, [1.0, 0.0], bounds=[(0, 20), (-20, 20)])
            if not fit.success:
                raise ValueError("Calibration optimiser failed")
            self.ab = fit.x
        elif self.method == "isotonic":
            self.model = IsotonicRegression(increasing=True, out_of_bounds="clip").fit(
                p, y
            )
        else:
            raise ValueError("Unknown calibration method")
        return self

    def __call__(self, p):
        p = np.asarray(p, dtype=float)
        if self.method == "identity":
            return p
        if self.method == "sigmoid":
            q = expit(self.ab[0] * logit(np.clip(p, EPS, 1 - EPS)) + self.ab[1])
        else:
            q = self.model.predict(p.ravel()).reshape(p.shape)
        # Preserve support endpoints. All transformations remain monotone.
        return np.where(p <= 0, 0, np.where(p >= 1, 1, q))

    def cdf(self, base):
        return lambda t: 1 - self(1 - base(t))


class Distribution:
    def __init__(self, kind, count=False):
        self.kind = kind
        self.count = count

    def fit(self, mu, y, *, in_sample_scale=None):
        mu, y = np.asarray(mu), np.asarray(y)
        self.residual = np.sort(y - mu)
        self.bias = float(np.mean(y - mu))
        self.scale = max(float(np.std(y - mu)), 1e-3)
        self.in_sample_scale = max(float(in_sample_scale or self.scale), 1e-3)
        # Moment fit on genuinely held-out outcomes, not fitted residuals.
        posmu = np.maximum(mu, 1e-3)
        self.alpha = max(
            float(np.sum((y - posmu) ** 2 - posmu) / np.sum(posmu**2)), 1e-6
        )
        self.ratio_residual = np.sort((y - mu) / self.scaler(mu))
        self.edges = np.unique(np.quantile(mu, [0, 0.25, 0.5, 0.75, 1]))
        self.nonzero = np.sort(y[y != 0])
        self.zero_rate = float(np.mean(y == 0))
        self.bin_samples = {}
        bins = np.digitize(mu, self.edges[1:-1])
        for b in np.unique(bins):
            vals = np.sort(y[(bins == b) & (y != 0)])
            self.bin_samples[int(b)] = vals if len(vals) >= 30 else self.nonzero
        return self

    def scaler(self, mu):
        return np.sqrt(np.maximum(mu, 1)) if self.count else np.maximum(np.abs(mu), 10)

    def cdf(self, mu, *, zero_probability=None, quantiles=None):
        mu = np.asarray(mu, dtype=float)

        def cdf(t):
            t = np.broadcast_to(np.asarray(t, dtype=float), mu.shape)
            if self.kind == "stage1a_normal":
                # Used only for historical half-line probes; this deliberately
                # reproduces the legacy continuous-normal rule for comparison.
                return stats.norm.cdf(t + 0.5, mu, self.in_sample_scale)
            if self.kind == "normal_oos":
                q = stats.norm.cdf(t + 0.5, mu + self.bias, self.scale)
            elif self.kind in ("empirical", "scaled_empirical"):
                scale = self.scaler(mu) if self.kind == "scaled_empirical" else 1
                residuals = (
                    self.ratio_residual
                    if self.kind == "scaled_empirical"
                    else self.residual
                )
                q = np.searchsorted(
                    residuals, (t + 0.5 - mu) / scale, side="left"
                ) / len(residuals)
            elif self.kind in ("poisson", "negative_binomial"):
                mean = np.maximum(mu, 1e-3)
                if self.kind == "poisson":
                    q = stats.poisson.cdf(t, mean)
                else:
                    size = 1 / self.alpha
                    q = stats.nbinom.cdf(t, size, size / (size + mean))
            elif self.kind == "hurdle":
                # Conditional empirical nonzero outcomes preserve negative
                # yardage. Zero probability is learned from pregame features.
                bins = np.digitize(mu, self.edges[1:-1])
                q = np.empty_like(mu)
                z = np.broadcast_to(
                    self.zero_rate if zero_probability is None else zero_probability,
                    mu.shape,
                )
                for b in np.unique(bins):
                    mask = bins == b
                    sample = self.bin_samples.get(int(b), self.nonzero)
                    nz = (
                        np.searchsorted(sample, t[mask], side="right") / len(sample)
                        if len(sample)
                        else np.ones(mask.sum())
                    )
                    q[mask] = (
                        (1 - z[mask]) * nz + z[mask] * (t[mask] >= 0)
                        if len(sample)
                        else (t[mask] >= 0).astype(float)
                    )
            elif self.kind == "quantile":
                # Rearrangement prevents crossing; bounded linear tails are an
                # explicit approximation, judged on separate selection data.
                knots = np.sort(np.asarray(quantiles), axis=1)
                spread = np.maximum(knots[:, -1] - knots[:, 0], 1)
                knots = np.column_stack(
                    [knots[:, 0] - 5 * spread, knots, knots[:, -1] + 5 * spread]
                )
                q = np.array(
                    [
                        np.interp(v + 0.5, k, [0, 0.1, 0.5, 0.9, 1])
                        for v, k in zip(t, knots)
                    ]
                )
            else:
                raise ValueError("Unknown distribution")
            return np.where(t < 0, 0, q) if self.count else q

        return cdf


def inverse_cdf(cdf, n, probability, bound=10000):
    lo = np.full(n, -bound, dtype=float)
    hi = np.full(n, bound, dtype=float)
    if np.any(cdf(lo) >= probability) or np.any(cdf(hi) < probability):
        raise ValueError("Predictive quantile outside search bounds")
    for _ in range(16):
        mid = np.floor((lo + hi) / 2)
        mask = cdf(mid) >= probability
        hi = np.where(mask, mid, hi)
        lo = np.where(mask, lo, mid + 1)
    return hi
