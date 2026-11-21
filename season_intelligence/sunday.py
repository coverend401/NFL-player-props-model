"""Fresh research overlay; certified slate/model/probability files are read-only."""

import json
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd

from scripts.build_slate import MARKETS as LABELS
from stage1b.data import MARKETS
from weekly_learning.store import encoded, sha

from .data import (
    CERTIFIED,
    STATS,
    history_features,
    market_data,
    reconciled_source,
    team_features,
)
from .models import PointModel


def build(panel, models, laws, choices, output):
    now = pd.Timestamp(datetime.now(UTC))
    manifest = json.loads((CERTIFIED / "manifest.json").read_text())
    slate = pd.read_parquet(CERTIFIED / "slate.parquet")
    slate = slate[slate.projection_status.eq("complete")].copy()
    slate = slate[
        slate.game_id.map(manifest["game_kickoffs"])
        .map(pd.Timestamp)
        .gt(now + pd.Timedelta(minutes=60))
    ]
    schedule = pd.read_parquet(
        CERTIFIED / "schedule.parquet",
        columns=["game_id", "home_team", "away_team", "gameday"],
    )
    sunday_ids = set(schedule[schedule.gameday.astype(str).eq("2026-11-22")].game_id)
    slate = slate[slate.game_id.isin(sunday_ids)]
    if slate.empty:
        raise ValueError("No eligible Sunday slate before T-60")
    eligibility = json.loads((CERTIFIED / "eligibility.json").read_text())
    evidence = {r["player_id"]: r for r in eligibility["players"]}
    for r in slate.itertuples():
        e = evidence[r.player_id]
        if (
            e["status"] != "eligible"
            or e["team"] != r.team
            or pd.Timestamp(e["available_at"]) > now
        ):
            raise ValueError("Current certified identity/eligibility mismatch")
    source, source_audit = reconciled_source()
    source = source[source.season.ge(2019)].copy()
    last = pd.to_datetime(source.completed_at, utc=True)
    if not last.dropna().lt(pd.Timestamp(manifest["feature_data_cutoff"])).all():
        raise ValueError("Source exceeds certified cutoff")
    requests = (
        slate[
            ["player_id", "team", "opponent", "position", "season", "week", "game_id"]
        ]
        .drop_duplicates(["game_id", "player_id"])
        .rename(columns={"opponent": "opponent_team"})
    )
    requests["kickoff_at"] = requests.game_id.map(manifest["game_kickoffs"]).map(
        pd.Timestamp
    )
    requests["completed_at"] = pd.NaT
    requests["offense_pct"] = np.nan
    requests["stats_observed"] = False
    for stat in STATS:
        requests[stat] = np.nan
    requests["is_home"] = requests.apply(
        lambda r: float(
            r.team == schedule[schedule.game_id.eq(r.game_id)].home_team.iloc[0]
        ),
        axis=1,
    )
    histories = history_features(pd.concat([source, requests], ignore_index=True))
    current = histories[histories.game_id.isin(slate.game_id.unique())]
    teams = team_features(source, requests)
    current = current.drop(
        columns=[c for c in teams if c in current and c not in ["game_id", "team"]],
        errors="ignore",
    ).merge(teams, on=["game_id", "team"], how="left", validate="many_to_one")
    reverse = {v: k for k, v in LABELS.items()}
    slate["market"] = slate.market.map(reverse)
    rows = []
    line_rows = []
    fitted = {}
    final_laws = {}
    for market, (target, positions, _, count) in MARKETS.items():
        base = slate[slate.market.eq(market)]
        if base.empty:
            continue
        d = market_data(current, market)
        g = base.merge(
            d,
            on=["game_id", "player_id"],
            suffixes=("", "_history"),
            validate="many_to_one",
        )
        training = market_data(panel[panel.position.isin(positions)], market)
        available = pd.concat(
            [
                pd.to_datetime(training.completed_at, utc=True),
                training.kickoff_at + pd.Timedelta(hours=36),
            ],
            axis=1,
        ).max(axis=1)
        training = training[
            training.offense_pct.gt(0)
            & training.stats_observed.eq(True)
            & training[target].notna()
            & training.history_n.ge(3)
            & available.lt(now)
        ]
        training["available_at"] = available.loc[training.index]
        family = choices[market]["family"]
        m = PointModel(market, family).fit(training)
        g["enhanced_candidate"] = m.predict(g)
        fitted[market] = m
        # Frozen 2026 evaluation law predates every 2026 result, keeping its provenance explicit.
        final_laws[market] = laws[(market, 2026)]
        g["research_point"] = (
            g.enhanced_candidate
            if choices[market]["retrospective_point_gate"]
            else g.projection
        )
        for r in g.itertuples():
            line = float(np.floor(r.projection) + 0.5)
            probabilities = final_laws[market].price(
                r.research_point, r.position, count, line
            )
            row = {
                "game_id": r.game_id,
                "player_id": r.player_id,
                "player": r.player,
                "team": r.team,
                "opponent": r.opponent,
                "position": r.position,
                "market": market,
                "baseline": float(r.projection),
                "enhanced_candidate": float(r.enhanced_candidate),
                "candidate_delta": float(r.enhanced_candidate - r.projection),
                "research_point": float(r.research_point),
                "point_family": family,
                "point_gate_passed": choices[market]["retrospective_point_gate"],
                "probability_gate_passed": choices[market][
                    "retrospective_probability_gate"
                ],
                "status": "EXPERIMENTAL MODEL RESEARCH — NO VERIFIED BOOKMAKER VALUE",
                "hypothetical_line": line,
                "p_over": probabilities["over"],
                "p_under": probabilities["under"],
                "p_push": probabilities["push"],
                "q05": probabilities["q05"],
                "q95": probabilities["q95"],
                "last3": float(getattr(r, target + "_last3")),
                "last5": float(getattr(r, target + "_last5")),
                "season_mean": float(getattr(r, target + "_season")),
                "recent_snap_share": float(r.offense_pct_last3),
                "recent_opportunities": float(
                    getattr(r, MARKETS[market][2] + "_last3")
                ),
                "role_share3": float(getattr(r, MARKETS[market][2] + "_share3")),
                "opponent_attempts_allowed": float(r.opp_allowed_attempts),
                "opponent_carries_allowed": float(r.opp_allowed_carries),
                "team_recent_plays": float(r.own_plays),
                "prediction_at": now.isoformat(),
                "feature_cutoff": manifest["feature_data_cutoff"],
                "eligibility_available_at": evidence[r.player_id]["available_at"],
                "kickoff_at": manifest["game_kickoffs"][r.game_id],
                "original_baseline_prediction_at": manifest["prediction_at"],
                "training_outcomes_before": m.fit_before,
                "model_promoted": False,
                "prices_verified": False,
            }
            row["explanation"] = (
                f"{r.player} averaged {row['last3']:.1f} in this market over his last three participating games and {row['last5']:.1f} over his last five, "
                f"with {row['recent_opportunities']:.1f} recent {MARKETS[market][2]} per game. "
                f"{r.opponent}'s opponents averaged {row['opponent_attempts_allowed']:.1f} pass attempts and {row['opponent_carries_allowed']:.1f} carries over the available prior eight games; these describe volume, not a proven individual matchup advantage. "
                f"The research estimate is {row['enhanced_candidate']:.1f} versus the unchanged {row['baseline']:.1f} baseline. Availability is based on the dated certified roster, not live injury news; no bookmaker value is established."
            )
            rows.append(row)
            for offset in [-0.5, 0, 0.5]:
                hypothetical = float(
                    np.floor(r.projection + offset * r.resid_std) + 0.5
                )
                p = final_laws[market].price(
                    r.research_point, r.position, count, hypothetical
                )
                line_rows.append(
                    {
                        "game_id": r.game_id,
                        "player_id": r.player_id,
                        "market": market,
                        "line": hypothetical,
                        "line_type": "HYPOTHETICAL_NOT_BOOKMAKER",
                        **p,
                    }
                )
    forecasts = pd.DataFrame(rows)
    metrics = pd.read_csv(output / "probability_metrics.csv")
    prior = metrics[
        (metrics.season == 2025) & metrics.method.eq("research_empirical")
    ].set_index("market")
    forecasts["validation_brier"] = forecasts.market.map(prior.brier.to_dict())
    forecasts["selection_log_loss"] = forecasts.market.map(prior.log_loss.to_dict())
    rank = forecasts.sort_values(
        [
            "probability_gate_passed",
            "validation_brier",
            "recent_snap_share",
            "player",
            "market",
        ],
        ascending=[False, True, False, True, True],
    )
    # Research priority only: never rank absent prices by fabricated EV.
    top2 = (
        rank.drop_duplicates(["game_id", "player_id"])
        .groupby("game_id", sort=False)
        .head(2)
        .copy()
    )
    shortlist = rank.drop_duplicates("player_id").head(12).copy()
    for d in [shortlist, top2]:
        d["ranking_basis"] = (
            "2025 calibration, established recent participation; no odds or profitability claim"
        )
    forecasts.to_parquet(output / "sunday_forecasts.parquet", index=False)
    shortlist.to_csv(output / "sunday_shortlist.csv", index=False)
    top2.to_csv(output / "sunday_top2.csv", index=False)
    pd.DataFrame(line_rows).to_csv(
        output / "sunday_hypothetical_lines.csv", index=False
    )
    joblib.dump({"points": fitted, "laws": final_laws}, output / "sunday_models.joblib")
    current.to_parquet(output / "sunday_feature_states.parquet", index=False)
    (output / "sunday_provenance.json").write_text(
        encoded(
            {
                "build_at": now.isoformat(),
                "baseline_release_id": manifest["release_id"],
                "baseline_manifest_sha256": sha(CERTIFIED / "manifest.json"),
                "feature_source_sha256": sha(CERTIFIED / "features.parquet"),
                "eligibility_sha256": sha(CERTIFIED / "eligibility.json"),
                "baseline_model_hashes": manifest["models"],
                "all_original_files_unchanged": True,
                "certified": False,
                "probability_training": "2022-2025 annual out-of-sample residuals; no2026 outcomes fitted into this law",
                "fresh_fit_scope": "Research point models refitted on permitted completed outcomes through2026week10 only",
                "source_reconciliation": source_audit,
                "missing_data": "No routes, injuries or upcoming active-teammate list fabricated",
            }
        )
    )
    return forecasts, shortlist, top2
