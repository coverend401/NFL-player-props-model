"""Provider-neutral bulk quotes: exact identities or unambiguous player/team matching."""

import re
import unicodedata
from fractions import Fraction

import pandas as pd

from .engine import evaluate

ALIASES = {
    "passing yards": "passing_yards",
    "pass yards": "passing_yards",
    "passing attempts": "passing_attempts",
    "pass attempts": "passing_attempts",
    "passing completions": "completions",
    "completions": "completions",
    "rushing yards": "rushing_yards",
    "rush yards": "rushing_yards",
    "rushing attempts": "rushing_attempts",
    "carries": "rushing_attempts",
    "receiving yards": "receiving_yards",
    "receptions": "receptions",
}


def name(value):
    value = (
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    value = re.sub(r"\b(jr|sr|ii|iii|iv)\.?$", "", value.strip())
    return re.sub("[^a-z]", "", value)


def decimal(value, form):
    if form == "decimal":
        return float(value)
    if form == "fractional":
        return 1 + float(Fraction(str(value)))
    if form == "american":
        number = float(value)
        if abs(number) < 100:
            raise ValueError("Invalid American odds")
        return 1 + number / 100 if number > 0 else 1 + 100 / abs(number)
    raise ValueError("Unsupported odds format; no guessing")


def normalise(frame, forecasts):
    """No prices/times are imputed. Over/under columns expand into separate real quotes."""
    if not 0 < len(frame) <= 100:
        raise ValueError("Bulk import must contain 1–100 source rows")
    rows = []
    for raw in frame.to_dict("records"):
        r = {k: v for k, v in raw.items() if pd.notna(v)}
        if r.get("period", "full_game") not in ["full_game", "fullgame", "game"]:
            raise ValueError("Only full-game player props are supported")
        label = str(r.get("market", "")).strip()
        market = ALIASES.get(label.lower(), label)
        f = forecasts
        if r.get("game_id"):
            f = f[f.game_id.eq(str(r["game_id"]))]
        if r.get("player_id"):
            f = f[f.player_id.eq(str(r["player_id"]))]
        elif r.get("player"):
            f = f[f.player.map(name).eq(name(r["player"]))]
        else:
            raise ValueError("Player identity required")
        if r.get("team"):
            f = f[f.team.eq(str(r["team"]).upper())]
        candidates = [market]
        if market in ["rushing_yards", "rushing_attempts"]:
            candidates.append("qb_" + market)
        f = f[f.market.isin(candidates)]
        if len(f) != 1:
            raise ValueError(
                "Unmatched or ambiguous player/fixture/market; import rejected"
            )
        matched = f.iloc[0]
        r.update(
            game_id=matched.game_id, player_id=matched.player_id, market=matched.market
        )
        if "over_odds" in r or "under_odds" in r:
            for side in ["over", "under"]:
                if side + "_odds" in r:
                    rows.append(
                        {
                            **r,
                            "side": side,
                            "line": r.get(side + "_line", r.get("line")),
                            "original_odds": str(r[side + "_odds"]),
                            "decimal_odds": decimal(
                                r[side + "_odds"], r.get("odds_format", "decimal")
                            ),
                        }
                    )
        else:
            r["original_odds"] = str(r.get("decimal_odds", r.get("odds", "")))
            r["decimal_odds"] = decimal(
                r.get("decimal_odds", r.get("odds")), r.get("odds_format", "decimal")
            )
            rows.append(r)
    if len(rows) > 200:
        raise ValueError("Expanded bulk import exceeds bound")
    return rows


def compare(frame, forecasts, *, now=None):
    return [evaluate(r, forecasts, now=now) for r in normalise(frame, forecasts)]
