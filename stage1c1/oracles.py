"""HINDSIGHT-ONLY opportunity error accounting, never candidate probabilities.

Unfitted five-game ratio strawmen diagnose error sources. They do not train an
allocation engine, normalise teammate shares, select a segment or create bets.
Oracle substitutions include observed outcomes and are not feasible forecasts.
"""

from itertools import permutations
import numpy as np
import pandas as pd
from stage1c.contracts import team, assert_development
from stage1b.data import MARKETS


def market_definition(market):
    if market in ["passing_yards", "passing_attempts", "completions"]:
        return "attempts", "attempts", "dropbacks", "expected_dropbacks"
    if "rushing" in market:
        return "carries", "carries", "plays", "expected_plays"
    return "targets", "targets", "dropbacks", "expected_dropbacks"


def substitutions(t_hat, s_hat, e_hat, t_actual, n_actual, y):
    # Undefined factors stay at their feasible estimates: a zero-opportunity
    # observation contains no evidence that efficiency was zero.
    s_actual = n_actual / t_actual if t_actual > 0 else s_hat
    e_actual = y / n_actual if n_actual > 0 else e_hat
    extra = y if n_actual == 0 else 0.0
    values = {}
    for mask in range(16):
        tv = t_actual if mask & 1 else t_hat
        sv = s_actual if mask & 2 else s_hat
        ev = e_actual if mask & 4 else e_hat
        values[mask] = tv * sv * ev + (extra if mask & 8 else 0.0)
    contribution = np.zeros(4)
    for order in permutations(range(4)):
        mask = 0
        before = abs(values[mask] - y)
        for factor in order:
            mask |= 1 << factor
            after = abs(values[mask] - y)
            contribution[factor] += (before - after) / 24
            before = after
    return values, contribution, s_actual, e_actual, extra


def build(frozen, source, games, official, context):
    assert_development(frozen)
    s = source.copy()
    s["team_key"] = s.team.map(team)
    s["available"] = pd.to_datetime(s.kickoff_at, utc=True) + pd.Timedelta(hours=36)
    s["available"] = pd.concat(
        [s.available, pd.to_datetime(s.completed_at, utc=True)], axis=1
    ).max(axis=1)
    if s.duplicated(["player_id", "game_id"]).any():
        raise ValueError("Ambiguous oracle source identity")
    source_lookup = s.set_index(["player_id", "game_id"])
    history = {
        key: g.sort_values("kickoff_at")
        for key, g in s[s.stats_observed.fillna(False) & s.offense_pct.gt(0)].groupby(
            "player_id"
        )
    }
    totals = official[official.kind.eq("pass")][
        ["game_id", "team", "attempts", "carries", "targets"]
    ]
    tg = games.merge(totals, on=["game_id", "team"], validate="one_to_one")
    tg["available"] = tg.kickoff_at + pd.Timedelta(hours=36)
    team_hist = {key: g.sort_values("kickoff_at") for key, g in tg.groupby("team")}
    team_actual = tg.set_index(["game_id", "team"])
    c = context[context.kind.eq("pass")].set_index(["game_id", "team"])
    pools = {}
    rows = []
    for market in MARKETS:
        target, positions, _, _ = MARKETS[market]
        opp, total, bridge, forecast = market_definition(market)
        group = frozen[frozen.market.eq(market)]
        for year in sorted(group.season.unique()):
            cutoff = s[s.season.eq(year - 1)].kickoff_at.min() - pd.Timedelta(hours=1)
            past = s[
                (s.available < cutoff)
                & s.stats_observed.fillna(False)
                & s.offense_pct.gt(0)
                & s.position.isin(positions)
                & s[target].notna()
                & s[opp].notna()
            ]
            team_past = tg[tg.available < cutoff]
            pool_bridge = team_past[total].sum() / team_past[bridge].sum()
            denominators = [
                team_actual.loc[(r.game_id, r.team_key), total]
                for r in past.itertuples()
            ]
            pool_share = (
                past[opp].sum() / np.sum(denominators)
                if np.sum(denominators) > 0
                else np.nan
            )
            pool_eff = (
                1.0
                if target == opp
                else past[target].sum() / past[opp].sum()
                if past[opp].sum() > 0
                else np.nan
            )
            pools[(market, year)] = (pool_bridge, pool_share, pool_eff)
        for r in group.itertuples():
            current = source_lookup.loc[(r.player_id, r.game_id)]
            tm = team(current.team)
            decision = r.prediction_at
            actual = team_actual.loc[(r.game_id, tm)]
            hh = history[r.player_id]
            hh = hh[
                (hh.available < decision) & hh[target].notna() & hh[opp].notna()
            ].tail(5)
            th = team_hist[tm]
            th = th[th.available < decision].tail(5)
            pool_bridge, pool_share, pool_eff = pools[(market, r.season)]
            denominator = th[bridge].sum()
            ratio = (th[total].sum() + 100 * pool_bridge) / (denominator + 100)
            t_hat = float(c.loc[(r.game_id, tm), forecast] * ratio)
            htot = np.sum(
                [
                    team_actual.loc[(v.game_id, v.team_key), total]
                    for v in hh.itertuples()
                ]
            )
            s_hat = float(hh[opp].sum() / htot) if htot > 0 else float(pool_share)
            e_hat = (
                1.0
                if target == opp
                else float(hh[target].sum() / hh[opp].sum())
                if hh[opp].sum() > 0
                else float(pool_eff)
            )
            n = float(current[opp])
            t_actual = float(actual[total])
            y = float(r.y)
            if not np.isfinite([n, t_actual, y, t_hat, s_hat, e_hat]).all():
                rows.append(
                    dict(
                        row_id=r.row_id,
                        market=market,
                        season=r.season,
                        week=r.week,
                        eligible=False,
                        reason="missing observed source/fallback",
                        y=y,
                        classification="HINDSIGHT_ONLY_ERROR_ACCOUNTING_NOT_FORECAST",
                        candidate_forecast=False,
                    )
                )
                continue
            predictions, contributions, s_actual, e_actual, exception = substitutions(
                t_hat, s_hat, e_hat, t_actual, n, y
            )
            records = dict(
                row_id=r.row_id,
                player_id=r.player_id,
                game_id=r.game_id,
                position=r.position,
                market=market,
                season=r.season,
                week=r.week,
                prediction_at=decision,
                y=y,
                eligible=True,
                reason="",
                T_hat=t_hat,
                S_hat=s_hat,
                E_hat=e_hat,
                T_actual=t_actual,
                N_actual=n,
                S_actual=s_actual,
                E_actual=e_actual,
                zero_opportunity=n == 0,
                exceptional_production=exception,
                actual_share_incoherent=(n > t_actual + 1e-8),
                forecast_share_incoherent=s_hat > 1 + 1e-8,
                history_n=len(hh),
                historical_information_max=hh.available.max(),
                team_information_max=th.available.max(),
                shapley_team_error_reduction=contributions[0],
                shapley_share_error_reduction=contributions[1],
                shapley_efficiency_error_reduction=contributions[2],
                shapley_exception_error_reduction=contributions[3],
                classification="HINDSIGHT_ONLY_ERROR_ACCOUNTING_NOT_FORECAST",
                candidate_forecast=False,
            )
            records.update({f"corner_{mask}": predictions[mask] for mask in range(16)})
            rows.append(records)
    return pd.DataFrame(rows)
