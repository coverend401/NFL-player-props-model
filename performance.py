"""Performance reporting. Singles, 2-leg parlays, SGPs and larger parlays are kept strictly separate."""
import numpy as np
import pandas as pd

TYPE_LABELS = {"single": "Singles", "parlay2": "2-Leg Parlays", "sgp": "SGPs", "parlayN": "Larger Parlays"}


def _settled(df, paper):
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[(df["paper"].astype(bool) == paper) & (df["status"] == "settled") & (df["result"] != "void")].copy()
    for c in ("actual_stake", "profit", "ev_pct", "model_prob", "clv_pct", "confidence", "bet_score",
              "parlay_score", "odds_decimal", "parlay_odds_decimal"):
        if c in d:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d["settled_at"] = pd.to_datetime(d["settled_at"], errors="coerce")
    return d.sort_values("settled_at")


def max_drawdown(profits: pd.Series) -> float:
    if profits.empty:
        return 0.0
    curve = profits.cumsum()
    return float((curve.cummax() - curve).max())


def max_losing_streak(results: pd.Series) -> int:
    best = cur = 0
    for r in results:
        cur = cur + 1 if r == "loss" else 0
        best = max(best, cur)
    return best


def summarise(d: pd.DataFrame) -> dict:
    if d.empty:
        return {"bets": 0}
    staked = float(d["actual_stake"].sum())
    profit = float(d["profit"].sum())
    wins = int((d["result"] == "win").sum())
    losses = int((d["result"] == "loss").sum())
    odds = d["odds_decimal"].fillna(d["parlay_odds_decimal"])
    return {
        "bets": len(d), "wins": wins, "losses": losses,
        "win_rate": wins / max(wins + losses, 1) * 100, "staked": staked, "profit": profit,
        "roi_pct": profit / staked * 100 if staked else 0.0,
        "avg_odds": float(odds.mean()), "avg_ev": float(d["ev_pct"].mean()),
        "avg_model_prob": float(d["model_prob"].mean() * 100),
        "avg_clv": float(d["clv_pct"].mean()) if d["clv_pct"].notna().any() else None,
        "avg_confidence": float(d["confidence"].mean()),
        "avg_bet_score": float(d["bet_score"].mean()) if d["bet_score"].notna().any() else None,
        "avg_parlay_score": float(d["parlay_score"].mean()) if d["parlay_score"].notna().any() else None,
        "max_losing_streak": max_losing_streak(d["result"]),
        "max_drawdown": max_drawdown(d["profit"]),
    }


def by_type(df, paper):
    d = _settled(df, paper)
    return {TYPE_LABELS.get(t, t): summarise(g) for t, g in d.groupby("bet_type")} if not d.empty else {}


def breakdown(df, paper, by: str, singles_only=True) -> pd.DataFrame:
    d = _settled(df, paper)
    if d.empty:
        return pd.DataFrame()
    if singles_only:
        d = d[d["bet_type"] == "single"]
    if d.empty:
        return pd.DataFrame()
    if by == "ev_band":
        d["grp"] = pd.cut(d["ev_pct"], [-100, 3, 5, 8, 12, 1000], labels=["<3", "3-5", "5-8", "8-12", "12+"])
    elif by == "prob_band":
        d["grp"] = pd.cut(d["model_prob"], [0, .5, .55, .6, .65, .7, .8, 1.01],
                          labels=["<50", "50-55", "55-60", "60-65", "65-70", "70-80", "80+"], right=False)
    else:
        d["grp"] = d[by]
    g = d.groupby("grp", observed=True).apply(lambda x: pd.Series({
        "bets": len(x), "win_rate_%": (x["result"] == "win").mean() * 100,
        "staked": x["actual_stake"].sum(), "profit": x["profit"].sum(),
        "ROI_%": x["profit"].sum() / x["actual_stake"].sum() * 100 if x["actual_stake"].sum() else 0.0,
    }), include_groups=False).reset_index().rename(columns={"grp": by})
    return g


def profit_curve(df, paper) -> pd.DataFrame:
    d = _settled(df, paper)
    if d.empty:
        return pd.DataFrame()
    d = d.reset_index(drop=True)
    d["cumulative_profit"] = d["profit"].cumsum()
    return d[["settled_at", "cumulative_profit"]]
