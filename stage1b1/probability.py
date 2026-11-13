"""Smoothed integer-support CDFs and regularised monotone calibration."""

import numpy as np
from scipy import stats
from scipy.optimize import minimize
from scipy.special import expit, logit


class ShrunkSigmoid:
    def __init__(self, penalty=0.01):
        self.penalty = penalty

    def fit(self, p, y, anchor_probability=None, tail_weight=0):
        p = np.asarray(p)
        y = np.asarray(y)
        x = logit(np.clip(p, 1e-8, 1 - 1e-8))

        def loss(ab):
            z = ab[0] * x + ab[1]
            q = expit(z)
            if anchor_probability is not None:
                q = (1 - tail_weight) * q + tail_weight * np.asarray(anchor_probability)
            q = np.clip(q, 1e-9, 1 - 1e-9)
            return -np.mean(y * np.log(q) + (1 - y) * np.log1p(-q)) + self.penalty * (
                (ab[0] - 1) ** 2 + ab[1] ** 2
            )

        fit = minimize(loss, [1.0, 0.0], bounds=[(0.25, 4.0), (-3.0, 3.0)])
        if not fit.success:
            raise ValueError("Regularised calibration failed")
        self.ab = fit.x
        return self

    def __call__(self, p):
        p = np.asarray(p)
        q = expit(self.ab[0] * logit(np.clip(p, 1e-8, 1 - 1e-8)) + self.ab[1])
        return np.where(p <= 0, 0, np.where(p >= 1, 1, q))

    def cdf(self, base):
        return lambda t: 1 - self(1 - base(t))


def student_cdf(mu, bias, scale, count):
    mu = np.asarray(mu)
    scale = max(float(scale), 1e-3) * np.sqrt(3 / 5)

    def cdf(t):
        t = np.broadcast_to(np.asarray(t), mu.shape)
        p = stats.t.cdf((t + 0.5 - mu - bias) / scale, df=5)
        return np.where(t < 0, 0, p) if count else p

    return cdf


def mix_cdf(base, anchor, weight):
    if not 0 <= weight <= 1:
        raise ValueError("Invalid tail mixture weight")
    return lambda t: (1 - weight) * base(t) + weight * anchor(t)


def nb_cdf(mu, alpha):
    mu = np.maximum(np.asarray(mu), 1e-6)
    size = 1 / max(float(alpha), 1e-6)
    return lambda t: stats.nbinom.cdf(t, size, size / (size + mu))


def shrink_dispersion(mu, y, strength=100, prior=0.25):
    mu = np.maximum(np.asarray(mu), 1e-6)
    y = np.asarray(y)
    raw = max(float(np.sum((y - mu) ** 2 - mu) / np.sum(mu**2)), 0.0)
    return (len(y) * raw + strength * prior) / (len(y) + strength)


def interval_score(y, lo, hi, alpha=0.1):
    y, lo, hi = np.asarray(y), np.asarray(lo), np.asarray(hi)
    if (lo > hi).any():
        raise ValueError("Crossed predictive interval")
    return (
        hi
        - lo
        + (2 / alpha) * np.maximum(lo - y, 0)
        + (2 / alpha) * np.maximum(y - hi, 0)
    )


def conformal_offset(y, lo, hi, alpha=0.1):
    y, lo, hi = np.asarray(y), np.asarray(lo), np.asarray(hi)
    score = np.maximum.reduce([lo - y, y - hi, np.zeros(len(y))])
    rank = min(int(np.ceil((len(y) + 1) * (1 - alpha))), len(y))
    return float(np.sort(score)[rank - 1])
