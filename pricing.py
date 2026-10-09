"""
Connects the EXISTING model to the betting engine.

Probability maths is unchanged from the existing Single Prop Lookup:
    P(Over line) = 1 - Normal_CDF(line; projection, residual_std)

Projection source, in order of preference:
  1. This week's slate row (already adjusted for the actual upcoming opponent, implied team total, home/away)
  2. Fallback: the player's latest historical row (what the old lookup used) - flagged as NOT matchup-adjusted
"""
import numpy as np
import pandas as pd
from scipy.stats import norm

import betting_engine as be
from odds_utils import parse_odds, implied_probability


def weeks_since_last_game(latest_row, upcoming_week, upcoming_season=None) -> int:
    if latest_row is None:
        return 99
    if upcoming_season is not None and int(latest_row["season"]) != int(upcoming_season):
        return 10
    return max(int(upcoming_week) - int(latest_row["week"]), 1)


def price_prop(*, market, file_label, player, side, line, odds_raw, odds_other_raw=None,
               injury_status="unknown", slate=None, latest_lookup=None, load_model=None,
               calib_table=None, avg_clv=0.0, settings=None, bankroll=1000.0):
    """Returns a dict with every number the dashboard / hunter / ledger needs, or {'error': ...}."""
    settings = {**be.DEFAULT_SETTINGS, **(settings or {})}
    try:
        dec = parse_odds(odds_raw)
    except (ValueError, TypeError) as e:
        return {"error": f"odds not understood: {e}"}

    latest = (latest_lookup or {}).get(player)

    row = None
    if slate is not None and len(slate):
        m = slate[(slate["market"] == market) & (slate["player"] == player)]
        if len(m):
            row = m.iloc[0]

    if row is not None:
        projection, resid_std = float(row["projection"]), float(row["resid_std"])
        recent, career = float(row["recent_form"]), float(row["career_avg"])
        games = int(row["games_played_prior"])
        team, opp = row["team"], row["opponent"]
        position = row["position"]
        week = int(row["week"])
        matchup_adjusted = True
    else:
        if load_model is None or latest is None:
            return {"error": "player has no projection this week and no history to fall back on"}
        bundle = load_model(file_label)
        if bundle is None:
            return {"error": f"no trained model for {market}"}
        cols = bundle["features"]
        if latest[cols].isna().any():
            return {"error": "not enough game history for this player yet"}
        projection = float(bundle["model"].predict(latest[cols].astype(float).to_frame().T)[0])
        resid_std = float(bundle["resid_std"])
        recent = float(latest[cols[1]]); career = float(latest[cols[0]])
        games = int(latest["games_played_prior"])
        team, opp = latest["team"], latest.get("opponent_team", "?")
        position = latest["position"]
        week = int(latest["week"]) + 1
        matchup_adjusted = False

    p_over = float(1 - norm.cdf(line, projection, resid_std))
    p = p_over if side == "Over" else 1 - p_over
    ev = be.ev_pct(p, dec)
    implied = implied_probability(dec)

    novig = None
    if odds_other_raw:
        try:
            other = parse_odds(odds_other_raw)
            novig = be.no_vig_probs(dec, other)[0]
        except (ValueError, TypeError):
            pass

    wsl = weeks_since_last_game(latest, week, None if latest is None else latest["season"])
    calib = be.calibration_score(p, calib_table)
    conf, conf_parts = be.confidence_score(
        games_played_prior=games, projection=projection, resid_std=resid_std, market=market,
        recent_form=recent, career_avg=career, weeks_since_last_game=wsl, injury_status=injury_status,
        calib_score=calib, matchup_adjusted=matchup_adjusted)
    dq, dq_reasons = be.data_quality(games_played_prior=games, injury_status=injury_status,
                                     weeks_since_last_game=wsl, matchup_adjusted=matchup_adjusted)
    cv = resid_std / max(abs(projection), 1.0)
    score, score_parts = be.bet_score(ev=ev, model_prob=p, confidence=conf, dq=dq, calib_score=calib,
                                      avg_clv_pct=avg_clv, market=market, cv=cv)
    cls = be.classify_bet(ev, conf, dq)
    stake = be.recommend_stake(p, dec, conf, bankroll, settings)
    if cls in ("PASS", "WATCH"):
        stake = {**stake, "stake": 0.0, "pct_bankroll": 0.0, "units": 0.0}

    game_key = "-".join(sorted([str(team), str(opp)])) if matchup_adjusted else f"UNKNOWN-{team}"
    return {
        "leg_id": f"{player}|{market}|{side}|{line}", "player": player, "market": market, "team": team,
        "opponent": opp, "position": position, "game_key": game_key,
        "game": f"{team} vs {opp}", "side": side, "line": line, "odds": dec,
        "projection": projection, "resid_std": resid_std, "recent_form": recent, "career_avg": career,
        "model_prob": p, "implied_prob": implied, "novig_prob": novig,
        "edge_pts": (p - (novig if novig else implied)) * 100,
        "ev_pct": ev, "confidence": conf, "confidence_parts": conf_parts,
        "data_quality": dq, "dq_reasons": dq_reasons, "injury_status": injury_status,
        "calib_score": calib, "bet_score": score, "bet_score_parts": score_parts,
        "class": cls, "stake": stake["stake"], "stake_pct": stake["pct_bankroll"], "units": stake["units"],
        "stake_capped": stake["capped"], "matchup_adjusted": matchup_adjusted, "games_played_prior": games,
    }
