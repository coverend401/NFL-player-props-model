"""
Betting engine - sits ON TOP of the existing model outputs.

Nothing here predicts anything. It takes the probabilities the existing model
already produces and turns them into: value class, confidence, bet score,
stake, correlation checks and 2-leg parlay selection.

Projection != Value != Bet.
"""
import itertools
import numpy as np
import pandas as pd

MODEL_VERSION = "v1.1"

DEFAULT_SETTINGS = {
    # bankroll / staking
    "starting_bankroll": 1000.0,
    "current_bankroll_override": 0.0,      # 0 = use starting bankroll + realised live P/L
    "unit_pct": 1.0,                       # 1 unit = 1% of bankroll
    "max_single_pct": 2.0,
    "max_parlay_pct": 0.5,
    "max_daily_exposure_pct": 6.0,
    "kelly_fraction": 0.25,
    "paper_mode": True,                    # default ON: model has never been tested against real prices
    # parlay hunter leg thresholds
    "leg_min_prob": 0.60, "leg_min_ev": 5.0, "leg_min_conf": 75,
    "safest_min_prob": 0.65, "safest_min_ev": 5.0, "safest_min_conf": 80,
    "big_min_prob": 0.50, "big_min_ev": 5.0, "big_min_conf": 65,
    "big_min_odds": 3.0, "big_min_combined_prob": 0.20,
    "allow_same_game": False,
}

# Typical miss as % of a typical result, measured on the 2025 hold-out season.
# Used as a "how reliable is this market" input. Re-derive after retraining.
MARKET_REL_ERROR = {
    "Passing Attempts": 27.8, "Passing Yards": 30.0, "Completions": 29.5,
    "Rushing Attempts": 38.5, "QB Rushing Attempts": 43.9, "Rushing Yards": 53.9,
    "Receptions": 50.5, "Receiving Yards": 61.2, "QB Rushing Yards": 71.0,
}

INJURY_FACTOR = {"healthy": 1.0, "unknown": 0.6, "questionable": 0.4, "doubtful": 0.1, "out": 0.0}
INJURY_BLOCKS_PARLAY = {"questionable", "doubtful", "out"}

ORDER = ["PASS", "WATCH", "SMALL", "STANDARD", "STRONG"]


# --------------------------------------------------------------------------
# Value
# --------------------------------------------------------------------------
def no_vig_probs(dec_a: float, dec_b: float):
    """Remove the bookmaker margin when BOTH sides' prices are known."""
    ia, ib = 1 / dec_a, 1 / dec_b
    s = ia + ib
    return ia / s, ib / s


def ev_pct(model_prob: float, dec_odds: float) -> float:
    """Expected profit per 1 staked, as a percentage."""
    return (model_prob * dec_odds - 1) * 100


def ev_band(ev: float) -> str:
    if ev >= 12: return "STRONG"
    if ev >= 8: return "STANDARD"
    if ev >= 5: return "SMALL"
    if ev >= 3: return "WATCH"
    return "PASS"


def classify_bet(ev: float, confidence: float, data_quality: str) -> str:
    """EV band, capped by confidence and data quality - high EV alone never makes a bet STRONG."""
    cap = "STRONG"
    if confidence < 50: cap = "WATCH"
    elif confidence < 65: cap = "SMALL"
    elif confidence < 75: cap = "STANDARD"
    if data_quality == "poor": cap = "WATCH" if ORDER.index(cap) > 1 else cap
    elif data_quality == "warn" and ORDER.index(cap) > 3: cap = "STANDARD"
    return ORDER[min(ORDER.index(ev_band(ev)), ORDER.index(cap))]


# --------------------------------------------------------------------------
# Calibration (no look-ahead: only bets settled BEFORE `as_of` are used)
# --------------------------------------------------------------------------
PROB_BINS = [0.0, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80, 1.01]


def calibration_table(ledger: pd.DataFrame, as_of=None, live_only=False) -> pd.DataFrame:
    """Predicted vs actual win rate by probability bucket, from settled singles."""
    cols = ["bucket", "n", "predicted", "actual"]
    if ledger is None or ledger.empty:
        return pd.DataFrame(columns=cols)
    d = ledger[(ledger["bet_type"] == "single") & (ledger["result"].isin(["win", "loss"]))].copy()
    if live_only:
        d = d[~d["paper"].astype(bool)]
    if as_of is not None and "settled_at" in d:
        d = d[pd.to_datetime(d["settled_at"], errors="coerce") < pd.Timestamp(as_of)]
    if d.empty:
        return pd.DataFrame(columns=cols)
    d["won"] = (d["result"] == "win").astype(int)
    d["bucket"] = pd.cut(d["model_prob"].astype(float), PROB_BINS, right=False)
    g = d.groupby("bucket", observed=True).agg(n=("won", "size"), predicted=("model_prob", "mean"),
                                               actual=("won", "mean")).reset_index()
    return g[cols]


def calibration_score(prob: float, table: pd.DataFrame, min_n: int = 30) -> float:
    """0-1. 0.7 = neutral/unknown (not enough history). Penalises buckets that historically
    won less often than the model claimed; mildly rewards ones that matched."""
    if table is None or table.empty:
        return 0.7
    row = table[table["bucket"].apply(lambda b: prob >= b.left and prob < b.right)]
    if row.empty or int(row.iloc[0]["n"]) < min_n:
        return 0.7
    gap = float(row.iloc[0]["actual"]) - float(row.iloc[0]["predicted"])   # negative = overconfident
    return float(np.clip(0.85 + gap * 6, 0.0, 1.0))


# --------------------------------------------------------------------------
# Confidence / data quality / bet score
# --------------------------------------------------------------------------
def confidence_score(*, games_played_prior, projection, resid_std, market, recent_form, career_avg,
                     weeks_since_last_game, injury_status, calib_score, matchup_adjusted=True):
    """0-100, independent of EV. Returns (score, component breakdown)."""
    inj = INJURY_FACTOR.get((injury_status or "unknown").lower(), 0.6)
    sample = min(games_played_prior / 16.0, 1.0)
    cv = resid_std / max(abs(projection), 1.0)
    vol = float(np.clip(1 - (cv - 0.25) / 0.75, 0, 1))
    rel = MARKET_REL_ERROR.get(market, 60.0)
    mkt = float(np.clip(1 - (rel - 25) / 50, 0, 1))
    role = 1 - min(abs(recent_form - career_avg) / max(abs(career_avg), 1.0), 1.0)
    fresh = float(np.clip(1 - (weeks_since_last_game - 1) / 5.0, 0, 1))
    parts = {"sample": 20 * sample, "volatility": 20 * vol, "market_reliability": 15 * mkt,
             "role_stability": 10 * role, "freshness": 10 * fresh, "injury": 15 * inj,
             "calibration": 10 * calib_score}
    score = sum(parts.values())
    if not matchup_adjusted:
        score *= 0.85       # projection built on last game's context, not this week's opponent
    if (injury_status or "").lower() == "out":
        score = 0.0
    return float(np.clip(score, 0, 100)), parts


def data_quality(*, games_played_prior, injury_status, weeks_since_last_game, matchup_adjusted):
    """'good' / 'warn' / 'poor' plus the reasons."""
    reasons = []
    inj = (injury_status or "unknown").lower()
    level = "good"
    if games_played_prior < 3 or inj == "out":
        level = "poor"; reasons.append("fewer than 3 games on record" if inj != "out" else "player ruled out")
    if games_played_prior < 6 and level != "poor":
        level = "warn"; reasons.append("small sample (<6 games)")
    if inj == "unknown" and level == "good":
        level = "warn"; reasons.append("injury status not confirmed")
    if inj in INJURY_BLOCKS_PARLAY and level != "poor":
        level = "warn"; reasons.append(f"injury status: {inj}")
    if weeks_since_last_game > 3 and level == "good":
        level = "warn"; reasons.append("hasn't played in 3+ weeks")
    if not matchup_adjusted:
        if level == "good": level = "warn"
        reasons.append("projection not adjusted for this week's opponent")
    return level, reasons


def bet_score(*, ev, model_prob, confidence, dq, calib_score, avg_clv_pct, market, cv):
    """0-100 ranking aid. EV is shown separately and never replaced by this."""
    rel = MARKET_REL_ERROR.get(market, 60.0)
    mkt = float(np.clip(1 - (rel - 25) / 50, 0, 1))
    parts = {
        "ev": 30 * float(np.clip(ev / 15.0, 0, 1)),
        "probability": 10 * float(np.clip((model_prob - 0.5) / 0.3, 0, 1)),
        "confidence": 25 * confidence / 100,
        "data_quality": 10 * {"good": 1.0, "warn": 0.5, "poor": 0.0}[dq],
        "calibration": 10 * calib_score,
        "clv": 5 * float(np.clip(0.5 + (avg_clv_pct or 0) / 10, 0, 1)),
        "market_quality": 5 * mkt,
        "volatility": 5 * float(np.clip(1 - (cv - 0.25) / 0.75, 0, 1)),
    }
    return float(sum(parts.values())), parts


# --------------------------------------------------------------------------
# Staking
# --------------------------------------------------------------------------
def current_bankroll(settings: dict, realised_live_pl: float = 0.0) -> float:
    ov = float(settings.get("current_bankroll_override") or 0)
    return ov if ov > 0 else float(settings["starting_bankroll"]) + realised_live_pl


def recommend_stake(p: float, dec_odds: float, confidence: float, bankroll: float, settings: dict,
                    bet_type: str = "single") -> dict:
    """Fractional Kelly scaled by confidence, hard-capped. A huge EV can't create a huge stake."""
    b = dec_odds - 1
    full_kelly = max((p * dec_odds - 1) / b, 0.0) if b > 0 else 0.0
    frac = float(settings["kelly_fraction"]) * (0.5 if bet_type != "single" else 1.0)
    pct = full_kelly * frac * (confidence / 100) * 100
    cap = float(settings["max_single_pct"] if bet_type == "single" else settings["max_parlay_pct"])
    pct = min(pct, cap)
    stake = round(bankroll * pct / 100, 2)
    unit = bankroll * float(settings["unit_pct"]) / 100
    return {"stake": stake, "pct_bankroll": round(pct, 3), "units": round(stake / unit, 2) if unit else 0.0,
            "capped": pct >= cap and full_kelly > 0}


def apply_daily_cap(recs: pd.DataFrame, bankroll: float, settings: dict, already_staked: float = 0.0) -> pd.DataFrame:
    """Walk recommendations best-first and trim stakes once the daily exposure cap is hit."""
    recs = recs.sort_values("bet_score", ascending=False).copy()
    room = bankroll * float(settings["max_daily_exposure_pct"]) / 100 - already_staked
    out = []
    for s in recs["stake"]:
        take = max(min(s, room), 0.0)
        out.append(round(take, 2)); room -= take
    recs["stake_after_cap"] = out
    return recs


# --------------------------------------------------------------------------
# Correlation / exposure
# --------------------------------------------------------------------------
def leg_correlation(a: dict, b: dict):
    """Returns (label, note, jointly_modelled). Joint probability for same-game legs is NOT modelled."""
    if a["player"] == b["player"]:
        return "HIGH", "same player", False
    if a["game_key"] == b["game_key"]:
        if a["team"] == b["team"]:
            return "HIGH", "same team, same game", False
        return "MEDIUM", "same game, opposing teams", False
    return "LOW", "different games", True


CORR_ICON = {"LOW": "🟢 LOW", "MEDIUM": "🟡 MEDIUM", "HIGH": "🔴 HIGH"}


def exposure_summary(open_bets: pd.DataFrame) -> dict:
    """Open-stake exposure by several dimensions, plus same-game correlation warnings."""
    if open_bets is None or open_bets.empty:
        return {"tables": {}, "warnings": []}
    rows = []
    for _, r in open_bets.iterrows():
        stake = float(r.get("actual_stake") or r.get("recommended_stake") or 0)
        legs = r.get("legs_json") or []
        if r["bet_type"] != "single" and legs:
            share = stake / len(legs)
            for l in legs:
                rows.append({"game": l.get("game_key"), "team": l.get("team"), "player": l.get("player"),
                             "market": l.get("market"), "position": l.get("position"),
                             "bet_type": r["bet_type"], "stake": share, "bet_id": r["bet_id"]})
        else:
            rows.append({"game": r.get("game"), "team": r.get("team"), "player": r.get("player"),
                         "market": r.get("market"), "position": r.get("position"),
                         "bet_type": r["bet_type"], "stake": stake, "bet_id": r["bet_id"]})
    ex = pd.DataFrame(rows)
    tables = {k: ex.groupby(k, dropna=False)["stake"].sum().sort_values(ascending=False).reset_index()
              for k in ["game", "team", "player", "market", "position", "bet_type"]}
    warnings = []
    for game, grp in ex.groupby("game", dropna=True):
        if grp["bet_id"].nunique() > 1 or len(grp) > 1:
            warnings.append(f"{game}: {len(grp)} positions in one game (£{grp['stake'].sum():.2f}) - "
                            f"these outcomes are correlated, treat as one bigger bet.")
    for player, grp in ex.groupby("player", dropna=True):
        if grp["bet_id"].nunique() > 1:
            warnings.append(f"{player}: in {grp['bet_id'].nunique()} separate bets (£{grp['stake'].sum():.2f}).")
    return {"tables": tables, "warnings": warnings}


# --------------------------------------------------------------------------
# 2-Leg Parlay Hunter
# --------------------------------------------------------------------------
def parlay_metrics(p_comb: float, dec_odds_comb: float) -> dict:
    return {"combined_prob": p_comb, "parlay_odds": dec_odds_comb,
            "fair_odds": 1 / p_comb if p_comb > 0 else float("inf"),
            "implied_prob": 1 / dec_odds_comb, "prob_edge_pts": (p_comb - 1 / dec_odds_comb) * 100,
            "ev_pct": ev_pct(p_comb, dec_odds_comb)}


def leg_failures(leg: dict, min_prob: float, min_ev: float, min_conf: float) -> list:
    """Why a leg does NOT qualify (empty list = qualifies)."""
    why = []
    if leg["model_prob"] < min_prob: why.append(f"probability {leg['model_prob']*100:.0f}% < {min_prob*100:.0f}%")
    if leg["ev_pct"] < min_ev: why.append(f"EV {leg['ev_pct']:+.1f}% < {min_ev:.0f}%")
    if leg["confidence"] < min_conf: why.append(f"confidence {leg['confidence']:.0f} < {min_conf:.0f}")
    if leg["data_quality"] == "poor": why.append("data quality poor")
    if str(leg.get("injury_status", "unknown")).lower() in INJURY_BLOCKS_PARLAY:
        why.append(f"injury status: {leg['injury_status']}")
    return why


def parlay_score(l1: dict, l2: dict, m: dict, corr: str, calib_avg: float) -> float:
    """0-100. Payout is gated by probability so a long-shot price can't inflate it."""
    prob = 30 * float(np.clip(m["combined_prob"] / 0.55, 0, 1))
    ev = 20 * float(np.clip(m["ev_pct"] / 30.0, 0, 1))
    leg_ev = 10 * float(np.clip(min(l1["ev_pct"], l2["ev_pct"]) / 15.0, 0, 1))
    conf = 15 * min(l1["confidence"], l2["confidence"]) / 100
    dq = 5 * np.mean([{"good": 1.0, "warn": 0.5, "poor": 0.0}[l["data_quality"]] for l in (l1, l2)])
    cor = 10 * {"LOW": 1.0, "MEDIUM": 0.4, "HIGH": 0.0}[corr]
    cal = 5 * calib_avg
    gate = float(np.clip(m["combined_prob"] / 0.35, 0, 1))
    pay = 5 * float(np.clip(m["parlay_odds"] / 6.0, 0, 1)) * gate
    return float(prob + ev + leg_ev + conf + dq + cor + cal + pay)


def _pair_rows(legs: list, s: dict, bankroll: float, overrides: dict):
    rows = []
    for a, b in itertools.combinations(legs, 2):
        corr, note, modelled = leg_correlation(a, b)
        if corr != "LOW" and not s.get("allow_same_game"):
            continue
        key = tuple(sorted([a["leg_id"], b["leg_id"]]))
        odds = overrides.get(key, a["odds"] * b["odds"])
        p = a["model_prob"] * b["model_prob"]
        m = parlay_metrics(p, odds)
        calib_avg = np.mean([a.get("calib_score", 0.7), b.get("calib_score", 0.7)])
        score = parlay_score(a, b, m, corr, calib_avg)
        conf = min(a["confidence"], b["confidence"])
        stake = recommend_stake(p, odds, conf, bankroll, s, bet_type="parlay2")
        rows.append({"leg1": a, "leg2": b, "metrics": m, "correlation": corr, "corr_note": note,
                     "jointly_modelled": modelled, "parlay_score": score, "stake": stake,
                     "pair_key": key, "min_conf": conf,
                     "flag": None if modelled else "CORRELATION NOT FULLY MODELLED - combined probability is NOT a product of the legs"})
    return rows


def hunt_two_leg_parlays(legs_df: pd.DataFrame, settings: dict, bankroll: float, overrides: dict = None) -> dict:
    """
    Scan every pair of priced props. Three different objectives, not "top two EVs":
      safest      - maximise P(both win), strict legs, low correlation only
      best_value  - maximise Parlay Score (balance of probability, EV, confidence, correlation)
      big_payout  - maximise combined EV subject to a minimum price and probability, still +EV legs
    """
    s = {**DEFAULT_SETTINGS, **settings}
    overrides = overrides or {}
    legs = legs_df.to_dict("records") if legs_df is not None and not legs_df.empty else []

    def pool(min_p, min_e, min_c):
        return [l for l in legs if not leg_failures(l, min_p, min_e, min_c)]

    out = {"safest": None, "best_value": None, "big_payout": None, "diagnostics": {}}
    used = set()

    # SAFEST
    p_safe = pool(s["safest_min_prob"], s["safest_min_ev"], s["safest_min_conf"])
    cands = [r for r in _pair_rows(p_safe, {**s, "allow_same_game": False}, bankroll, overrides)
             if r["metrics"]["ev_pct"] > 0 and r["jointly_modelled"]]
    cands.sort(key=lambda r: (r["metrics"]["combined_prob"], r["parlay_score"]), reverse=True)
    out["diagnostics"]["safest_pool"] = len(p_safe); out["diagnostics"]["safest_pairs"] = len(cands)
    if cands:
        out["safest"] = cands[0]; used.add(cands[0]["pair_key"])

    # BEST VALUE
    p_val = pool(s["leg_min_prob"], s["leg_min_ev"], s["leg_min_conf"])
    cands = [r for r in _pair_rows(p_val, s, bankroll, overrides) if r["metrics"]["ev_pct"] > 0 and r["pair_key"] not in used]
    cands.sort(key=lambda r: r["parlay_score"], reverse=True)
    out["diagnostics"]["value_pool"] = len(p_val); out["diagnostics"]["value_pairs"] = len(cands)
    if cands:
        out["best_value"] = cands[0]; used.add(cands[0]["pair_key"])

    # BIG PAYOUT
    p_big = pool(s["big_min_prob"], s["big_min_ev"], s["big_min_conf"])
    cands = [r for r in _pair_rows(p_big, s, bankroll, overrides)
             if r["metrics"]["ev_pct"] > 0 and r["metrics"]["parlay_odds"] >= s["big_min_odds"]
             and r["metrics"]["combined_prob"] >= s["big_min_combined_prob"] and r["pair_key"] not in used]
    cands.sort(key=lambda r: (r["metrics"]["ev_pct"], r["parlay_score"]), reverse=True)
    out["diagnostics"]["big_pool"] = len(p_big); out["diagnostics"]["big_pairs"] = len(cands)
    if cands:
        out["big_payout"] = cands[0]
    return out
