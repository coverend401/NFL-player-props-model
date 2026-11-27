"""Discrete, zero-aware empirical forecasts with strictly earlier OOF residuals."""

import numpy as np
from scipy.stats import norm


class HurdleEmpirical:
    def fit(self, mu, y, position):
        mu, y = np.asarray(mu, float), np.asarray(y, float)
        position = np.asarray(position, str)
        if len(y) < 100 or not np.isfinite(mu).all() or not np.isfinite(y).all():
            raise ValueError("Insufficient finite out-of-sample distribution data")
        self.mu, self.y, self.position = mu, y, position
        self.edges = np.unique(np.quantile(mu, np.linspace(0, 1, 6)))
        self.bin = np.digitize(mu, self.edges[1:-1])
        return self

    def samples(self, mu, position, count):
        """A global/conditional mixture; no missing outcome is changed into zero."""
        b = np.digitize(mu, self.edges[1:-1])
        cohort = self.position == str(position)
        local = (self.bin == b) & cohort
        global_mask = cohort if cohort.sum() >= 100 else np.ones(len(self.y), bool)
        weight = local.sum() / (local.sum() + 100)
        masks = [local, global_mask]
        weights = [weight, 1 - weight]
        draws = []
        mass = []
        for mask, w in zip(masks, weights):
            if not mask.any() or w == 0:
                continue
            y, m = self.y[mask], self.mu[mask]
            zero = y == 0
            p0 = (zero.sum() + 20 * (self.y[global_mask] == 0).mean()) / (len(y) + 20)
            if zero.all():
                draws.append(np.array([0.0]))
                mass.append(np.array([w]))
                continue
            # Scale with expected workload, preserving asymmetric observed errors.
            scale = np.sqrt(np.maximum(np.abs(m[~zero]), 1))
            residual = (y[~zero] - m[~zero]) / scale
            raw = mu + np.sqrt(max(abs(mu), 1)) * residual
            values = np.rint(raw)
            values = (
                np.maximum(values, 1)
                if count
                else np.where(values == 0, np.where(raw < 0, -1, 1), values)
            )
            draws += [np.array([0.0]), values]
            mass += [
                np.array([w * p0]),
                np.full(len(values), w * (1 - p0) / len(values)),
            ]
        values = np.concatenate(draws)
        weights = np.concatenate(mass)
        order = np.argsort(values, kind="stable")
        return values[order], weights[order] / weights.sum()

    def price(self, mu, position, count, line):
        if not np.isfinite(line) or not np.isfinite(mu):
            raise ValueError("Nonfinite forecast/line")
        values, w = self.samples(float(mu), position, count)
        over = float(w[values > line].sum())
        under = float(w[values < line].sum())
        push = float(w[values == line].sum())
        cumulative = np.cumsum(w)
        quantile = lambda p: float(
            values[min(np.searchsorted(cumulative, p), len(values) - 1)]
        )
        return {
            "over": over,
            "under": under,
            "push": push,
            "fair_over": (1 - push) / over if over > 0 else None,
            "fair_under": (1 - push) / under if under > 0 else None,
            "q05": quantile(0.05),
            "q50": quantile(0.5),
            "q95": quantile(0.95),
        }


def normal_price(mu, sigma, line):
    over = float(norm.sf((line - mu) / max(sigma, 1e-6)))
    return {"over": over, "under": 1 - over, "push": 0.0}


def quoted_value(probabilities, decimal_odds, side="over", push_rule="refund"):
    if push_rule != "refund":
        raise ValueError("Only full-stake refund pushes supported")
    if (
        side not in ["over", "under"]
        or not np.isfinite(decimal_odds)
        or decimal_odds <= 1
    ):
        raise ValueError("Invalid quoted odds or side")
    win = probabilities[side]
    push = probabilities["push"]
    loss = 1 - win - push
    return {
        "break_even_conditional": 1 / decimal_odds,
        "implied_unconditional_win_at_refund_push": (1 - push) / decimal_odds,
        "expected_profit_per_unit": win * (decimal_odds - 1) - loss,
    }
