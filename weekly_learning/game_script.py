"""Current-fixture descriptive research from admitted historical observations only."""

import numpy as np
import pandas as pd


def build_game_research(features, schedule, manifest):
    cutoff = pd.Timestamp(manifest["feature_data_cutoff"])
    f = features[pd.to_datetime(features.completed_at, utc=True) < cutoff]
    totals = f.groupby(["game_id", "team"], as_index=False)[
        ["team_total_attempts", "team_total_carries"]
    ].first()
    past = schedule[pd.to_datetime(schedule.completed_at, utc=True) < cutoff]
    totals = totals.merge(
        past[["game_id", "kickoff_at", "home_team", "home_score", "away_score"]],
        on="game_id",
        validate="many_to_one",
    )
    totals["margin"] = np.where(
        totals.team.eq(totals.home_team),
        totals.home_score - totals.away_score,
        totals.away_score - totals.home_score,
    )
    output = []
    for gid in manifest["fixture_slate"]["game_ids"]:
        away, home = gid.split("_")[-2:]
        for team, opponent in [(away, home), (home, away)]:
            h = totals[totals.team.eq(team)].sort_values("kickoff_at").tail(8)
            recent = h.tail(3)

            def mean(frame, column):
                values = frame[column].dropna()
                return float(values.mean()) if len(values) else None

            states = []
            for name, mask in [
                ("finished_behind_by_8_plus", h.margin.lt(-7)),
                ("finished_within_7", h.margin.between(-7, 7)),
                ("finished_ahead_by_8_plus", h.margin.gt(7)),
            ]:
                group = h[mask]
                states.append(
                    {
                        "final_margin_group": name,
                        "games": len(group),
                        "pass_attempts": mean(group, "team_total_attempts"),
                        "carries": mean(group, "team_total_carries"),
                    }
                )
            output.append(
                {
                    "game_id": gid,
                    "team": team,
                    "opponent": opponent,
                    "recorded_games": len(h),
                    "recent_games": len(recent),
                    "pass_attempts_last3": mean(recent, "team_total_attempts"),
                    "carries_last3": mean(recent, "team_total_carries"),
                    "mean_margin_last8": mean(h, "margin"),
                    "historical_final_margin_groups": states,
                    "interpretation": "A lead may support carries and chasing points may support passing. These are conditional football hypotheses, not predicted game-state probabilities or player adjustments.",
                    "missing": [
                        "No calibrated lead/trail occupancy probabilities",
                        "No unverified scheme, injury or personnel claims",
                    ],
                }
            )
    return {
        "method": "admitted_team_descriptive_v1",
        "prediction_at": manifest["prediction_at"],
        "feature_data_cutoff": manifest["feature_data_cutoff"],
        "release_id": manifest["release_id"],
        "projection_adjustments": False,
        "fixtures": output,
    }
