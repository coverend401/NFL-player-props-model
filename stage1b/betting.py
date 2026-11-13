"""Push-aware economics and conservative experimental risk diagnostics."""

import numpy as np


def economics(p_win, p_push, decimal_odds):
    if not all(np.isfinite(x) for x in [p_win, p_push, decimal_odds]):
        raise ValueError("Nonfinite pricing input")
    if p_win < 0 or p_push < 0 or p_win + p_push > 1 + 1e-10 or decimal_odds <= 1:
        raise ValueError("Invalid outcome probabilities or decimal odds")
    loss = max(0.0, 1 - p_win - p_push)
    ev = p_win * (decimal_odds - 1) - loss
    fair = (1 - p_push) / p_win if p_win > 0 else None
    kelly = (
        max(
            0.0,
            (p_win * (decimal_odds - 1) - loss) / ((decimal_odds - 1) * (1 - p_push)),
        )
        if p_push < 1
        else 0.0
    )
    return {
        "ev_per_unit": ev,
        "fair_decimal_odds": fair,
        "kelly_fraction": min(kelly, 1.0),
    }


def no_vig(over_odds, under_odds):
    if min(over_odds, under_odds) <= 1:
        raise ValueError("Invalid two-sided prices")
    a, b = 1 / over_odds, 1 / under_odds
    return {
        "overround": a + b - 1,
        "over_conditional_no_push": a / (a + b),
        "under_conditional_no_push": b / (a + b),
    }


def edge_assessment(
    probabilities,
    odds,
    *,
    n_calibration_games,
    validated=False,
    bankroll=1000.0,
    fraction=0.125,
    cap=0.005,
):
    """Disagreement range is not a statistical confidence interval."""
    if bankroll <= 0 or not 0 <= fraction <= 1 or not 0 <= cap <= 1:
        raise ValueError("Invalid research risk limits")
    scores = [economics(float(p[0]), float(p[2]), odds) for p in probabilities]
    if not scores:
        raise ValueError("At least one forecast is required")
    worst = min(s["ev_per_unit"] for s in scores)
    allowed = validated and n_calibration_games >= 100 and worst > 0
    stake_fraction = (
        min(min(s["kelly_fraction"] for s in scores) * fraction, cap)
        if allowed
        else 0.0
    )
    return {
        "experimental": True,
        "worst_method_ev": worst,
        "ev_range": [worst, max(s["ev_per_unit"] for s in scores)],
        "n_calibration_games": n_calibration_games,
        "fractional_kelly_stake": round(bankroll * stake_fraction, 2),
        "fixed_stake_comparator": 1.0 if allowed else 0.0,
        "warning": "No individual probability confidence interval is implied. Default stake is zero until independently validated.",
    }
