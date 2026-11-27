"""Review-only decisions for flagged forecasts; does not select or publish rows."""

import pandas as pd

from scripts.forecast_features import utc_timestamp


def reconcile_flagged(flagged, roster, schedule, source_available_at, decision_at):
    available, decision = utc_timestamp(source_available_at), utc_timestamp(decision_at)
    if available > decision:
        raise ValueError("Roster evidence was not available at the decision timestamp")
    if flagged.duplicated(["player_id", "market", "game_id"]).any():
        raise ValueError("Duplicate flagged forecast rows")
    records = []
    for row in flagged.to_dict("records"):
        current = roster[
            roster.gsis_id.eq(row["player_id"])
            & roster.season.eq(row["season"])
            & roster.week.eq(row["week"])
        ][["team", "status"]].drop_duplicates()
        record = {
            k: row[k]
            for k in [
                "player_id",
                "player",
                "market",
                "game_id",
                "team",
                "season",
                "week",
                "gate",
            ]
        }
        record.update(
            evidence_available_at=available.isoformat(),
            reconciliation_at=decision.isoformat(),
            current_team=None,
            roster_status=None,
            decision="unresolved",
            reason="No unambiguous current-week roster evidence; older status is not current eligibility proof",
            gameday_active_confirmed=False,
        )
        fixture = schedule[schedule.game_id.eq(row["game_id"])]
        if len(fixture) != 1 or row["team"] not in [
            fixture.iloc[0].home_team,
            fixture.iloc[0].away_team,
        ]:
            raise ValueError("Draft forecast fixture/team identity mismatch")
        if len(current) == 1:
            team, status = current.iloc[0][["team", "status"]]
            record.update(current_team=team, roster_status=status)
            if status in ["DEV", "CUT"]:
                record.update(
                    decision="currently_roster_ineligible",
                    reason="Current-week practice-squad status, not active-roster confirmation"
                    if status == "DEV"
                    else "Current-week released status",
                )
            elif status == "ACT":
                remaining = schedule[
                    schedule.season.eq(row["season"])
                    & schedule.week.eq(row["week"])
                    & (schedule.home_team.eq(team) | schedule.away_team.eq(team))
                    & pd.to_datetime(schedule.kickoff_at, utc=True).gt(decision)
                ]
                if remaining.empty:
                    record.update(
                        decision="ineligible_current_fixture",
                        reason="Current club has no remaining pregame fixture in this week",
                    )
                elif team != row["team"]:
                    record.update(
                        reason="Current team verified, but forecast must be regenerated for its actual fixture; do not transplant an old-opponent projection"
                    )
                elif utc_timestamp(fixture.iloc[0].kickoff_at) <= decision:
                    record.update(
                        decision="ineligible_current_fixture",
                        reason="Forecast fixture has already kicked off",
                    )
                else:
                    record.update(
                        decision="confirmed_roster_eligible",
                        reason="Active current-week roster and matching future fixture; game-day inactives remain unconfirmed",
                    )
        records.append(record)
    return pd.DataFrame(records)
