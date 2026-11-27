"""Standing publication, availability and private calibration fail-closed gates."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from weekly_learning import authority, availability, publication
from weekly_learning.store import Store, encoded, sha


class AuthorityTests(unittest.TestCase):
    def test_authority_verifies_original_nine_and_rejects_scope(self):
        p = authority.validate()
        self.assertEqual(len(p["models"]), 9)
        m = {
            "model_parent": p["model_parent"],
            "models": p["models"],
            "fixture_slate": {"season": 2027, "week": 12},
        }
        with (
            patch.object(authority.json, "loads", side_effect=[p, m]),
            self.assertRaisesRegex(ValueError, "outside standing"),
        ):
            authority.validate(
                authority.ROOT
                / "research_inference_releases/weekly-week12-remaining-20261127"
            )

    def test_changed_critical_code_needs_owner_review(self):
        with (
            patch.object(authority, "sha", return_value="changed"),
            self.assertRaisesRegex(ValueError, "modelling code changed"),
        ):
            authority.validate()


class AvailabilityTests(unittest.TestCase):
    def test_missing_evidence_is_not_healthy_or_inactive(self):
        f = pd.DataFrame({"player_id": ["p"], "kickoff_at": ["2026-11-29T18:00Z"]})
        with (
            tempfile.TemporaryDirectory() as t,
            patch.object(availability, "POINTER", Path(t) / "absent"),
        ):
            out, status = availability.filter_frame(f, now="2026-11-27T12:00Z")
        self.assertEqual(len(out), 1)
        self.assertEqual(status["status"], "unverified")

    def test_explicit_out_only_blocks_future_not_archived_rows(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            state = root / "weekly_learning_state"
            store = Store(state)
            report = {
                "schema": 1,
                "source": availability.URL,
                "default_status": "unverified",
                "retrieved_at": "2026-11-27T11:00Z",
                "records": [
                    {
                        "player_id": "p",
                        "status": "Out",
                        "source_date": "2026-11-27T10:00Z",
                    }
                ],
            }
            with store.transaction():
                d = store.publish(
                    "availability", "test", documents={"report.json": report}
                )
            pointer = state / "availability_current.json"
            pointer.write_text(
                encoded(
                    {
                        "path": str(d.relative_to(root)),
                        "manifest_sha256": sha(d / "manifest.json"),
                    }
                )
            )
            f = pd.DataFrame(
                {
                    "player_id": ["p", "p", "unknown"],
                    "kickoff_at": [
                        "2026-11-22T18:00Z",
                        "2026-11-29T18:00Z",
                        "2026-11-29T18:00Z",
                    ],
                }
            )
            with (
                patch.object(availability, "ROOT", root),
                patch.object(availability, "POINTER", pointer),
            ):
                out, status = availability.filter_frame(f, now="2026-11-27T12:00Z")
            self.assertEqual(len(out), 2)
            self.assertEqual(status["withheld"], ["p"])

    def test_corrupt_evidence_blocks_pricing(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "pointer"
            p.write_text("{}")
            with (
                patch.object(availability, "POINTER", p),
                self.assertRaisesRegex(ValueError, "integrity"),
            ):
                availability.filter_frame(pd.DataFrame())


class PublicationTests(unittest.TestCase):
    def test_expired_candidate_cannot_change_pointers_or_touch_private_store(self):
        from research_platform import weekly_serving

        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            directory = root / "candidate"
            profile = root / "profile"
            directory.mkdir()
            profile.mkdir()
            (profile / "certificate.json").write_text("{}")
            store = Store(root / "state")
            with (
                patch.object(publication, "paths"),
                patch.object(publication, "validate", return_value={}),
                patch.object(
                    weekly_serving,
                    "admit",
                    return_value=(
                        None,
                        None,
                        {"game_kickoffs": {"past": "2020-01-01T18:00Z"}},
                    ),
                ),
                patch("selection_learning.probe.probe") as probe,
            ):
                with self.assertRaisesRegex(ValueError, "deadline passed"):
                    publication.publish_validated(
                        store, directory, profile, "revision", {"run_id": "test"}
                    )
                probe.assert_not_called()
            self.assertFalse((store.root / "routine_publications").exists())

    def test_dirty_code_is_not_publishable(self):
        from weekly_learning.code_trust import approved_code

        with (
            tempfile.TemporaryDirectory() as t,
            patch(
                "weekly_learning.code_trust.subprocess.check_output",
                return_value=" M operational.py",
            ),
            self.assertRaisesRegex(ValueError, "uncommitted"),
        ):
            approved_code(Store(t))


class ProbabilityShadowTests(unittest.TestCase):
    def test_duplicate_prices_do_not_supply_effective_sample(self):
        from selection_learning.calibration_learning import shadow

        events = []
        for i in range(120):
            events.append(
                {
                    "kind": "settlement",
                    "at": "2026-10-01T00:00Z",
                    "payload": {
                        "status": "win" if i % 2 else "loss",
                        "hit_probability": 0.7,
                        "game_id": f"2026_{1 + i % 4:02d}_A_B",
                        "player_id": "same-player",
                        "market": "receptions",
                        "quote_id": str(i),
                        "line": 4.5,
                    },
                }
            )
        result = shadow(
            {"events": events},
            {"game_id": "2026_12_A_B", "hit_probability": 0.7, "line": 4.5},
            "2026-11-27T12:00Z",
        )
        self.assertEqual(result["status"], "insufficient_genuine_prior_quotes")
        self.assertEqual(result["independent_player_games"], 4)


class AvailabilitySourceTests(unittest.TestCase):
    def test_official_player_card_id_maps_when_athlete_id_absent(self):
        payload = {
            "season": {"year": 2026},
            "timestamp": "2026-11-27T11:59Z",
            "injuries": [
                {
                    "injuries": [
                        {
                            "status": "Out",
                            "date": "2026-11-27T10:00Z",
                            "athlete": {
                                "links": [
                                    {
                                        "href": "https://www.espn.com/nfl/player/_/id/12345/test-player"
                                    }
                                ]
                            },
                        }
                    ]
                }
            ],
        }
        r = Mock()
        r.__enter__ = Mock(return_value=r)
        r.__exit__ = Mock(return_value=None)
        r.status_code = 200
        r.iter_content.return_value = [json.dumps(payload).encode()]
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            store = Store(root / "weekly_learning_state")
            fixed = Mock()
            fixed.now.return_value = pd.Timestamp("2026-11-27T12:00Z").to_pydatetime()
            with (
                patch.object(availability, "ROOT", root),
                patch.object(
                    availability, "POINTER", store.root / "availability_current.json"
                ),
                patch.object(availability, "datetime", fixed),
            ):
                result = availability.collect(
                    store, "test", {"12345": "gsis"}, get=Mock(return_value=r)
                )
            self.assertEqual(result["records"], 1)
            report = json.loads(
                (store.root / "availability/test/report.json").read_text()
            )
            self.assertEqual(report["records"][0]["player_id"], "gsis")
            self.assertNotIn("links", report["records"][0])


# The original and Cloud dependency sets are intentionally separate.
import importlib.metadata
import os
import sys

TARGET = (
    sys.version_info[:2] == (3, 14)
    and importlib.metadata.version("certifi") == "2026.11.20"
)


@unittest.skipUnless(TARGET, "Exact Python 3.14 Cloud serving environment required")
class RoutineEntrypointTests(unittest.TestCase):
    def test_real_admission_and_authenticated_entrypoint_all_workspaces(self):
        from streamlit.testing.v1 import AppTest

        from research_platform import weekly_serving as s

        directory = (
            s.ROOT / "research_inference_releases/weekly-routine-initial-20261127"
        )
        profile = (
            s.ROOT / "research_runtime_profiles/routine-weekly-routine-initial-20261127"
        )
        frame, fixtures, release = s.admit(profile, directory)
        self.assertEqual(
            (len(frame), len(fixtures), frame.game_id.nunique()), (457, 12, 9)
        )
        pointer = {
            "release_id": release["release_id"],
            "profile": str(profile.relative_to(s.ROOT)),
            "certificate_sha256": sha(profile / "certificate.json"),
        }
        operational = {
            "path": str(directory.relative_to(s.ROOT)),
            "release_id": release["release_id"],
            "manifest_sha256": sha(directory / "manifest.json"),
            "checks": json.loads((profile / "certificate.json").read_text())["checks"][
                "inference"
            ],
        }
        catalog = {
            "schema": 1,
            "releases": {
                pointer["profile"]: {
                    **pointer,
                    "path": operational["path"],
                    "authority_sha256": sha(profile / "authority.json"),
                }
            },
        }
        read = s.read_json

        def read_json(path):
            if path == s.ROOT / "weekly_learning_state/serving_catalog.json":
                return catalog
            return read(path)

        with tempfile.TemporaryDirectory() as t:
            active = Path(t) / "active.json"
            active.write_text(encoded(pointer))
            op = Path(t) / "selected.json"
            op.write_text(encoded(operational))
            with (
                patch.object(s, "ACTIVE", active),
                patch.object(s, "OPERATIONAL", op),
                patch.object(s, "read_json", side_effect=read_json),
                patch.dict(
                    os.environ,
                    {
                        "RESEARCH_PREVIEW_PASSWORD": "synthetic-routine-only",
                        "NFL_SELECTION_GITHUB_REPOSITORY": "",
                        "NFL_SELECTION_GITHUB_TOKEN": "",
                        "SPORTSGAMEODDS_API_KEY": "",
                    },
                ),
                patch("requests.get") as get,
                patch("requests.request") as request,
            ):
                self.assertEqual(s.selected()[2]["release_id"], release["release_id"])
                app = AppTest.from_file(
                    str(s.ROOT / "odds_value_research.py"), default_timeout=180
                ).run()
                app.text_input(key="research_password").input("synthetic-routine-only")
                app.button[0].click().run()
                self.assertFalse(app.exception, app.exception)
                self.assertFalse(app.error)
                self.assertTrue(
                    any(release["release_id"] in m.value for m in app.caption)
                )
                for section in app.selectbox[0].options:
                    app.selectbox[0].select(section).run()
                    self.assertFalse(app.exception, (section, app.exception))
                    if section == "Top 2 by Game":
                        text = " ".join(m.value for m in app.markdown)
                        for game in fixtures.itertuples():
                            self.assertIn(f"{game.away_team} at {game.home_team}", text)
                get.assert_not_called()
                request.assert_not_called()
