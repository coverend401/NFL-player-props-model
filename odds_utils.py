"""
Odds parsing and edge/expected-value calculation.

Accepts decimal (e.g. "1.91"), American (e.g. "-110", "+150"), or
fractional (e.g. "10/11", "6/4") odds as plain text and converts to a
common decimal-odds representation and implied probability.
"""


def parse_odds(raw: str) -> float:
    """Returns decimal odds from any of the three common formats."""
    s = raw.strip()

    # Fractional: contains a slash, e.g. "10/11"
    if "/" in s:
        num, denom = s.split("/")
        num, denom = float(num.strip()), float(denom.strip())
        if denom == 0:
            raise ValueError("Invalid fractional odds - denominator is zero.")
        return (num / denom) + 1

    # American: explicit +/- sign
    if s.startswith("+") or s.startswith("-"):
        american = float(s)
        if american > 0:
            return (american / 100) + 1
        else:
            return (100 / abs(american)) + 1

    # Otherwise assume decimal odds, e.g. "1.91"
    decimal = float(s)
    if decimal <= 1:
        raise ValueError("Decimal odds must be greater than 1.00.")
    return decimal


def implied_probability(decimal_odds: float) -> float:
    return 1 / decimal_odds


def expected_value(model_prob: float, decimal_odds: float, stake: float = 1.0) -> float:
    """EV per unit stake: what you'd expect to win/lose on average if the
    model's probability is correct and you made this bet many times."""
    return (model_prob * (decimal_odds - 1) * stake) - ((1 - model_prob) * stake)


def signal_category(edge_pct: float, games_played_prior: int) -> str:
    """Simple, transparent signal tiers - not a guarantee, just a label."""
    if games_played_prior < 5:
        return "Neutral (small sample)"
    if edge_pct >= 8:
        return "Strong Signal"
    if edge_pct >= 3:
        return "Signal"
    if edge_pct >= -3:
        return "Neutral"
    return "Negative Signal"