"""Current release must fail closed even though its internal replay is valid."""

import json
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from research_platform.selection_integrity import (
    ROOT,
    block_reason,
    check_association,
)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "game_id": "2026_11_ARI_KC",
            "player_id": "synthetic",
            "team": "KC",
            "opponent": "ARI",
        }
        self.schedule = pd.DataFrame(
            [
                {
                    "game_id": self.row["game_id"],
                    "season": 2026,
                    "week": 11,
                    "home_team": "KC",
                    "away_team": "ARI",
                }
            ]
        )
        self.roster = pd.DataFrame(
            [{"gsis_id": "synthetic", "team": "KC", "status": "ACT"}]
        )

    def test_valid_identity(self):
        self.assertIsNone(check_association(self.row, self.schedule, self.roster))

    def test_display_name_must_match_player_identifier(self):
        roster = self.roster.assign(full_name="Known Player III")
        self.assertEqual(
            check_association(
                {**self.row, "player": "Someone Else"}, self.schedule, roster
            ),
            "player_name_identifier_mismatch",
        )
        self.assertIsNone(
            check_association(
                {**self.row, "player": "Known Player"}, self.schedule, roster
            )
        )

    def test_wrong_team_or_opponent_is_rejected(self):
        for key, value in [("team", "SEA"), ("opponent", "DEN"), ("opponent", "KC")]:
            self.assertEqual(
                check_association({**self.row, key: value}, self.schedule, self.roster),
                "invalid_team_opponent_join",
            )

    def test_roster_identity_and_inactive_are_not_assumed(self):
        for roster in [
            self.roster.assign(team="SEA"),
            self.roster.iloc[:0],
            pd.concat([self.roster, self.roster.assign(team="SEA")]),
        ]:
            self.assertEqual(
                check_association(self.row, self.schedule, roster),
                "roster_missing_or_conflicting_team",
            )
        self.assertEqual(
            check_association(
                self.row, self.schedule, self.roster.assign(status="RES")
            ),
            "active_roster_not_confirmed",
        )

    def test_ambiguous_and_wrong_game_id(self):
        self.assertEqual(
            check_association(self.row, pd.concat([self.schedule] * 2), self.roster),
            "schedule_missing_or_ambiguous",
        )
        self.assertEqual(
            check_association(self.row, self.schedule.assign(week=12), self.roster),
            "invalid_fixture_identity",
        )

    def test_missing_failed_expired_and_unbound_audits_block(self):
        now = datetime.now(UTC)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.json"
            release = {"release_id": "synthetic"}
            self.assertIsNotNone(block_reason(release, path))
            report = {
                "status": "PASS",
                "release_id": "synthetic",
                "authoritative_schedule_verified": True,
                "current_player_transactions_verified": True,
                "availability_review_complete": True,
                "opponent_features_verified": True,
                "internal_error_rows": 0,
                "fixture_feed_disagreements": [],
                "valid_until": (now + timedelta(hours=1)).isoformat(),
                "files": json.loads(
                    (
                        ROOT / "research_audits/sunday-20261122/integrity.json"
                    ).read_text()
                )["files"],
            }
            path.write_text(json.dumps(report))
            self.assertIsNone(block_reason(release, path, now))
            for changes in [
                {"status": "FAIL"},
                {"release_id": "other"},
                {"authoritative_schedule_verified": False},
                {"current_player_transactions_verified": False},
                {"valid_until": now.isoformat()},
                {"files": {}},
                {"internal_error_rows": 1},
                {"fixture_feed_disagreements": ["bad-game"]},
                {"files": {"research_platform/selection_integrity.py": "bad"}},
            ]:
                path.write_text(json.dumps({**report, **changes}))
                self.assertIsNotNone(block_reason(release, path, now), changes)

    def test_real_audit_covers_every_forecast_and_blocks(self):
        report = json.loads(
            (ROOT / "research_audits/sunday-20261122/integrity.json").read_text()
        )
        self.assertEqual(report["forecast_count"], 522)
        audit = pd.read_csv(ROOT / "research_audits/sunday-20261122/forecasts.csv")
        self.assertEqual(len(audit), 522)
        self.assertFalse(audit.duplicated(["game_id", "player_id", "market"]).any())
        self.assertIsNotNone(block_reason({"release_id": report["release_id"]}))


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14),
    "Real frozen entrypoint requires its original Python 3.14 runtime",
)
class StartupTests(unittest.TestCase):
    def test_real_authenticated_entrypoint_blocks_before_cards_or_prices(self):
        from streamlit.testing.v1 import AppTest

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic-integrity-test",
                    "NFL_RESEARCH_INFERENCE_POINTER": "tests/fixtures/week11_research_pointer.json",
                    "SPORTSGAMEODDS_API_KEY": "",
                    "SGO_GITHUB_QUOTA_TOKEN": "",
                    "SGO_RESEARCH_STORE": str(Path(tmp) / "empty.sqlite"),
                },
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            app = AppTest.from_file(
                str(ROOT / "odds_value_research.py"), default_timeout=120
            ).run()
            app.text_input(key="research_password").input("synthetic-integrity-test")
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(
                any("INTEGRITY REVIEW — FAIL" in e.value for e in app.error)
            )
            self.assertFalse(
                any(
                    "desk-card" in x.value and "<article" in x.value
                    for x in app.markdown
                )
            )
            self.assertFalse(app.number_input)
            for section in [
                "Top 2 by Game",
                "Parlay Research",
                "Player Intelligence",
                "Game Intelligence",
                "Market Intelligence",
                "Data & Safety",
                "Top Picks",
            ]:
                next(x for x in app.selectbox if x.label == "Workspace").select(
                    section
                ).run()
                self.assertFalse(app.exception, app.exception)
                self.assertFalse(app.number_input)
                self.assertFalse(any("<article" in x.value for x in app.markdown))
            get.assert_not_called()
            request.assert_not_called()
