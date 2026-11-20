"""Targeted roster timing/identity checks; no publication policy or live requests."""

import unittest
from datetime import UTC, datetime

import pandas as pd

from research_platform.roster_reconciliation import reconcile_flagged

NOW = datetime(2026, 11, 20, 10, tzinfo=UTC)


class ReconciliationTests(unittest.TestCase):
    def run_case(self, roster, available=NOW):
        rows = pd.DataFrame(
            [
                {
                    "player_id": "synthetic",
                    "player": "Synthetic",
                    "market": "Receptions",
                    "game_id": "future",
                    "team": "KC",
                    "season": 2026,
                    "week": 11,
                    "gate": "team_conflict",
                }
            ]
        )
        games = pd.DataFrame(
            [
                {
                    "game_id": "future",
                    "home_team": "KC",
                    "away_team": "ARI",
                    "kickoff_at": "2026-11-22T18:00:00Z",
                    "season": 2026,
                    "week": 11,
                },
                {
                    "game_id": "past",
                    "home_team": "HOU",
                    "away_team": "IND",
                    "kickoff_at": "2026-11-20T01:15:00Z",
                    "season": 2026,
                    "week": 11,
                },
            ]
        )
        return reconcile_flagged(
            rows,
            pd.DataFrame(
                roster, columns=["gsis_id", "team", "status", "season", "week"]
            ),
            games,
            available,
            NOW,
        ).iloc[0]

    def test_old_active_row_cannot_confirm_current_eligibility(self):
        self.assertEqual(
            self.run_case([["synthetic", "KC", "ACT", 2026, 9]]).decision, "unresolved"
        )

    def test_missing_is_not_inactive(self):
        self.assertEqual(self.run_case([]).decision, "unresolved")

    def test_practice_squad_is_currently_not_roster_eligible_not_gameday_inactive(self):
        r = self.run_case([["synthetic", "KC", "DEV", 2026, 11]])
        self.assertEqual(r.decision, "currently_roster_ineligible")
        self.assertFalse(r.gameday_active_confirmed)

    def test_current_team_with_past_fixture_does_not_keep_old_team_forecast(self):
        r = self.run_case([["synthetic", "HOU", "ACT", 2026, 11]])
        self.assertEqual(r.current_team, "HOU")
        self.assertEqual(r.decision, "ineligible_current_fixture")

    def test_active_roster_not_guaranteed_active_on_game_day(self):
        r = self.run_case([["synthetic", "KC", "ACT", 2026, 11]])
        self.assertEqual(r.decision, "confirmed_roster_eligible")
        self.assertFalse(r.gameday_active_confirmed)

    def test_future_evidence_rejected(self):
        with self.assertRaises(ValueError):
            self.run_case([], datetime(2026, 11, 21, tzinfo=UTC))

    def test_conflicting_current_memberships_stay_unresolved(self):
        self.assertEqual(
            self.run_case(
                [
                    ["synthetic", "KC", "ACT", 2026, 11],
                    ["synthetic", "HOU", "ACT", 2026, 11],
                ]
            ).decision,
            "unresolved",
        )

    def test_saved_44_row_evidence_replays_without_publishing_or_gameday_claim(self):
        import hashlib
        import json
        from pathlib import Path

        root = (
            Path(__file__).resolve().parents[1]
            / "research_inputs/week11_reconciliation/20261120"
        )
        manifest = json.loads((root / "evidence_manifest.json").read_text())
        for name, digest in manifest["files"].items():
            self.assertEqual(
                hashlib.sha256((root / name).read_bytes()).hexdigest(), digest
            )
        summary = json.loads((root / "reconciliation_summary.json").read_text())
        actual = reconcile_flagged(
            pd.read_csv(root / "flagged_rows.csv"),
            pd.read_csv(root / "roster_evidence.csv"),
            pd.read_csv(root / "fixture_evidence.csv"),
            summary["source_available_at"],
            summary["reconciliation_at"],
        )
        self.assertEqual(
            actual.decision.value_counts().to_dict(),
            {
                "currently_roster_ineligible": 30,
                "unresolved": 12,
                "ineligible_current_fixture": 2,
            },
        )
        self.assertFalse(actual.gameday_active_confirmed.any())
        self.assertEqual(len(actual), 44)
        self.assertEqual(summary["published_rows"], 0)
