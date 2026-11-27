"""Read-only full-population audit; aggregated feeds cannot certify transactions.

Inputs are explicitly downloaded schedule/roster snapshots. Never reads sealed
Week 11 outcomes, contacts bookmakers, modifies forecasts or promotes a release.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research_platform.selection_integrity import ROOT, check_association, digest
from season_intelligence.data import reconciled_source


def run(roster_path, schedule_path, output):
    selected = ROOT / "research_selection_releases/enhanced-sunday-20261121-v1"
    parent = ROOT / "research_inference_releases/research-week11-frozen-20261120-r2"
    frame = pd.read_parquet(selected / "forecasts.parquet")
    fixtures = pd.read_csv(selected / "fixtures.csv")
    # Do not load fresh schedule scores or inspect any Week 11 outcomes.
    schedule = pd.read_csv(
        schedule_path,
        usecols=[
            "game_id",
            "season",
            "week",
            "gameday",
            "home_team",
            "away_team",
            "gametime",
        ],
    )
    schedule = schedule[schedule.season.eq(2026) & schedule.week.eq(11)].copy()
    roster = pd.read_parquet(
        roster_path,
        columns=[
            "gsis_id",
            "team",
            "status",
            "season",
            "week",
            "full_name",
            "first_name",
            "football_name",
            "last_name",
        ],
    )
    roster = roster[roster.season.eq(2026) & roster.week.eq(11)].copy()
    states = pd.read_parquet(
        ROOT
        / "experiments/season_intelligence/sunday-20261121-v1/sunday_feature_states.parquet"
    )
    states = states.set_index(["game_id", "player_id"], verify_integrity=True)
    eligibility = {
        x["player_id"]: x
        for x in json.loads((parent / "eligibility.json").read_text())["players"]
    }
    source, _ = reconciled_source()
    # Explicit pre-seal filters, in addition to the source loader's own filters.
    source = source[
        (source.season.lt(2026)) | (source.season.eq(2026) & source.week.le(10))
    ]
    raw = source.groupby(["game_id", "team"], as_index=False).first()
    raw["available"] = pd.concat(
        [
            pd.to_datetime(raw.completed_at, utc=True),
            pd.to_datetime(raw.kickoff_at, utc=True) + pd.Timedelta(hours=36),
        ],
        axis=1,
    ).max(axis=1)
    totals = raw.set_index(["game_id", "team"])
    rows = []
    for row in frame.to_dict("records"):
        errors = []
        association = check_association(row, schedule, roster)
        if association:
            errors.append(association)
        game = schedule[schedule.game_id.eq(row["game_id"])]
        if len(game) == 1:
            game = game.iloc[0]
            eastern = (
                pd.Timestamp(f"{game.gameday} {game.gametime}")
                .tz_localize("America/New_York")
                .tz_convert("UTC")
            )
            if eastern != pd.Timestamp(row["kickoff_at"]):
                errors.append("kickoff_mismatch")
        e = eligibility.get(row["player_id"], {})
        if e.get("team") != row["team"] or e.get("status") != "eligible":
            errors.append("eligibility_mismatch")
        if pd.Timestamp(e["available_at"]) > pd.Timestamp(row["prediction_at"]):
            errors.append("eligibility_after_prediction")
        state = states.loc[(row["game_id"], row["player_id"])]
        if state.team != row["team"] or state.opponent_team != row["opponent"]:
            errors.append("feature_identity_mismatch")
        cutoff = min(
            pd.Timestamp(row["feature_cutoff"]),
            pd.Timestamp(row["kickoff_at"]) - pd.Timedelta(minutes=60),
        )
        history = (
            raw[raw.team.eq(row["opponent"]) & raw.available.lt(cutoff)]
            .sort_values("available")
            .tail(8)
        )
        for field, target, feature in [
            (
                "team_total_attempts",
                "opponent_attempts_allowed",
                "opp_allowed_attempts",
            ),
            ("team_total_carries", "opponent_carries_allowed", "opp_allowed_carries"),
        ]:
            values = [
                totals.loc[(h.game_id, h.opponent_team), field]
                for h in history.itertuples()
                if (h.game_id, h.opponent_team) in totals.index
            ]
            expected = float(np.nanmean(values)) if values else np.nan
            if not np.isclose(expected, row[target], equal_nan=True) or not np.isclose(
                state[feature], row[target], equal_nan=True
            ):
                errors.append(target + "_wrong_opponent_or_history")
        rows.append(
            {
                **{
                    k: row[k]
                    for k in [
                        "game_id",
                        "player_id",
                        "player",
                        "team",
                        "opponent",
                        "market",
                    ]
                },
                "internal_errors": "|".join(errors),
                "internal_status": "FAIL" if errors else "PASS",
                "official_transactions": "UNVERIFIED_NETWORK_BLOCKED",
                "injuries_inactives": "UNVERIFIED_NOT_CONFIRMED_ACTIVE",
                "selection_admission": "BLOCKED",
            }
        )
    audit = pd.DataFrame(rows)
    output.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output / "forecasts.csv", index=False)
    roster[roster.gsis_id.isin(frame.player_id)].to_csv(
        output / "refreshed_roster.csv", index=False
    )
    schedule.to_csv(output / "refreshed_schedule.csv", index=False)
    comparisons = fixtures.merge(
        schedule,
        on="game_id",
        suffixes=("_bundle", "_fresh"),
        how="left",
        validate="one_to_one",
    )
    mismatch = comparisons.game_id[
        sum(
            comparisons[a + "_bundle"].ne(comparisons[a + "_fresh"])
            for a in ["home_team", "away_team", "gameday"]
        )
        > 0
    ].tolist()
    paths = [
        selected / x
        for x in [
            "forecasts.parquet",
            "top_picks.csv",
            "top2.csv",
            "fixtures.csv",
            "manifest.json",
        ]
    ]
    paths += [
        parent / x
        for x in ["eligibility.json", "roster_evidence.csv", "schedule.parquet"]
    ]
    paths += [
        ROOT
        / "experiments/season_intelligence/sunday-20261121-v1/sunday_feature_states.parquet"
    ]
    paths += [
        output / x
        for x in ["forecasts.csv", "refreshed_roster.csv", "refreshed_schedule.csv"]
    ]
    report = {
        "status": "FAIL",
        "release_id": parent.name,
        "created_at": datetime.now(UTC).isoformat(),
        "forecast_count": len(frame),
        "players": frame.player_id.nunique(),
        "forecast_fixtures": frame.game_id.nunique(),
        "sunday_schedule_fixtures": int(fixtures.gameday.eq("2026-11-22").sum()),
        "internal_error_rows": int(audit.internal_status.eq("FAIL").sum()),
        "fixture_feed_disagreements": mismatch,
        "authoritative_schedule_verified": False,
        "current_player_transactions_verified": False,
        "availability_review_complete": False,
        "opponent_features_verified": not audit.internal_errors.str.contains(
            "opponent|feature_identity"
        ).any(),
        "blocked_hosts": [
            "www.nfl.com",
            "www.chiefs.com",
            "www.raiders.com",
            "site.api.espn.com",
        ],
        "source_urls": [
            "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
            "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2026.parquet",
        ],
        "source_raw_sha256": {
            "roster": digest(roster_path),
            "schedule": digest(schedule_path),
        },
        "source_limitations": "Fresh aggregated feeds agree, but are not independent official schedule/transaction or game-day availability verification. Retrieval time is not publication time.",
        "files": {str(p.relative_to(ROOT)): digest(p) for p in paths},
    }
    (output / "integrity.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ["files", "source_raw_sha256"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--roster", required=True, type=Path)
    parser.add_argument("--schedule", required=True, type=Path)
    args = parser.parse_args()
    run(args.roster, args.schedule, ROOT / "research_audits/sunday-20261122")
