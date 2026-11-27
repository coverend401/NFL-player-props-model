"""Frozen weekly release admission and quote routing; no genuine prices or network."""

import copy
import importlib.metadata
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from research_platform import weekly_serving as serving
from scripts.generate_weekly_serving import generated

TARGET = (
    sys.version_info[:2] == (3, 14)
    and importlib.metadata.version("certifi") == "2026.11.20"
)


class DerivationTests(unittest.TestCase):
    def test_contract_is_exact_declared_runtime_only_derivation(self):
        self.assertEqual(
            (serving.ROOT / "research_platform/cloud_weekly_contract.py").read_text(),
            generated(),
        )
        original = (serving.ROOT / "weekly_learning/contract.py").read_text()
        derived = generated()
        for guard in [
            "Frozen model artifact changed",
            "Eligibility decisions differ from versioned source replay",
            "Future starter evidence",
            "Missing complete markets or scenario-only Top Picks",
            "Inference source/code mismatch",
        ]:
            self.assertIn(guard, original)
            self.assertIn(guard, derived)
        self.assertNotIn("check_runtime=False", original)

    def test_activation_is_not_implicit(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(serving, "ACTIVE", Path(tmp) / "absent.json"),
        ):
            self.assertIsNone(serving.selected())


class PrivateProbeTests(unittest.TestCase):
    def test_storage_probe_cas_readback_does_not_write_selection_or_quota(self):
        import base64
        from unittest.mock import Mock

        from selection_learning.probe import FILE, probe

        journal = Mock()
        saved = {}

        def call(method, path, payload=None):
            self.assertEqual(path, "/contents/" + FILE)
            if method == "PUT":
                self.assertEqual(payload["sha"], "expected-version")
                saved.update(payload)
                return {}
            if not saved:
                return {"sha": "expected-version"}
            return {"content": saved["content"]}

        journal.call.side_effect = call
        result = probe(journal)
        self.assertEqual(result["read_backs"], 2)
        self.assertEqual(result["selection_records_created"], 0)
        self.assertEqual(journal.read.call_count, 1)
        self.assertNotIn("records", json.loads(base64.b64decode(saved["content"])))

    def test_conflict_is_not_retried(self):
        from unittest.mock import Mock

        from selection_learning.probe import probe

        journal = Mock()
        journal.call.side_effect = [None, ValueError("concurrent update")]
        with self.assertRaises(ValueError):
            probe(journal)
        self.assertEqual(journal.call.call_count, 2)


class FreezeBatchTests(unittest.TestCase):
    def test_reloading_same_observed_quote_is_not_a_new_selection(self):
        from selection_learning.engine import admit_quote
        from selection_learning.settlement import freeze
        from selection_learning.store import initial
        from tests.test_line_selections import AT, panel, quote, record

        a, _ = admit_quote(quote(), panel(), now=AT)
        b, _ = admit_quote(
            quote(quoted_at="2026-11-22T14:59:00+00:00", bookmaker="synthetic"),
            panel(),
            now="2026-11-22T15:01Z",
        )
        self.assertEqual(a["quote_id"], b["quote_id"])
        r = record()
        before = freeze(
            initial(),
            [r],
            now=AT,
            release_id="test",
            forecast_manifest_sha256="synthetic",
        )
        with self.assertRaises(ValueError):
            freeze(
                before,
                [{**r, "quote_id": "different-legacy-id"}],
                now=AT,
                release_id="test",
                forecast_manifest_sha256="synthetic",
            )

    def test_new_low_rank_batch_does_not_become_top_two_by_itself(self):
        from selection_learning.settlement import freeze
        from selection_learning.store import initial
        from tests.test_line_selections import AT, record

        base = record()
        a = {**base, "quote_id": "first", "player_id": "one", "hit_probability": 0.85}
        b = {**base, "quote_id": "second", "player_id": "two", "hit_probability": 0.8}
        third = {
            **base,
            "quote_id": "third",
            "player_id": "three",
            "hit_probability": 0.65,
        }
        before = freeze(
            initial(),
            [a, b],
            now=AT,
            release_id="test",
            forecast_manifest_sha256="synthetic",
        )
        after = freeze(
            before,
            [third],
            now=AT,
            release_id="test",
            forecast_manifest_sha256="synthetic",
        )
        self.assertEqual(after["events"][-1]["payload"]["top2"][base["game_id"]], [])
        self.assertEqual(before["events"], after["events"][:-1])


@unittest.skipUnless(TARGET, "Separate Python 3.14 Cloud serving lock required")
class ServingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.fixtures, cls.release = serving.admit()

    def test_population_roof_identity_and_build_timing(self):
        frame = self.frame
        self.assertEqual(
            (len(frame), frame.game_id.nunique(), len(self.fixtures)), (651, 12, 16)
        )
        self.assertTrue(
            pd.to_datetime(frame.selection_built_at, utc=True)
            .ge(pd.Timestamp(self.release["prediction_at"]))
            .all()
        )
        self.assertFalse(
            frame.game_id.isin(
                [
                    "2026_12_BAL_HOU",
                    "2026_12_NYG_IND",
                    "2026_12_PHI_DAL",
                    "2026_12_WAS_ARI",
                ]
            ).any()
        )
        schedule = self.fixtures.set_index("game_id")
        for r in frame.itertuples():
            g = schedule.loc[r.game_id]
            self.assertEqual({r.team, r.opponent}, {g.home_team, g.away_team})
        self.assertFalse(frame.prices_verified.any())

    def test_certificate_fails_for_missing_binding_fake_schema_or_failed_replay(self):
        path = serving.PROFILE / "certificate.json"
        real = serving.read_json
        for field in ["files", "schema", "checks"]:
            certificate = copy.deepcopy(real(path))
            if field == "files":
                certificate["files"].pop(next(iter(certificate["files"])))
            elif field == "schema":
                certificate["schema"] = 99
            else:
                certificate["checks"]["inference"]["exact_replay"] = False
            with (
                self.subTest(field=field),
                patch.object(
                    serving,
                    "read_json",
                    side_effect=lambda p, c=certificate: (
                        c if Path(p) == path else real(p)
                    ),
                ),
                self.assertRaises(ValueError),
            ):
                serving.admit()

    def test_expired_original_slate_cannot_activate_or_probe_storage(self):
        from release_utils import sha256
        from scripts.select_weekly_serving import select

        with (
            patch("selection_learning.probe.probe") as probe,
            self.assertRaisesRegex(ValueError, "Activation deadline passed"),
        ):
            select(
                self.release["release_id"],
                sha256(serving.PROFILE / "certificate.json"),
                "synthetic test approval",
            )
        probe.assert_not_called()

    def test_remaining_candidate_obeys_original_future_fixture_contract(self):
        frame, fixtures, release = serving.admit(
            serving.REMAINING_PROFILE, serving.REMAINING_RELEASE
        )
        self.assertEqual(
            (len(frame), frame.game_id.nunique(), len(fixtures)), (457, 9, 12)
        )
        self.assertTrue(
            pd.to_datetime(fixtures.kickoff_at, utc=True)
            .gt(pd.Timestamp(release["prediction_at"]) + pd.Timedelta(minutes=60))
            .all()
        )
        self.assertFalse(
            frame.game_id.isin(
                [
                    "2026_12_GB_LA",
                    "2026_12_CHI_DET",
                    "2026_12_KC_BUF",
                    "2026_12_PHI_DAL",
                ]
            ).any()
        )

    def test_real_line_price_calculation_without_claiming_live_quotes(self):
        from research_platform.enhanced_engine import price
        from selection_learning.engine import evaluate

        frame = self.frame
        row = frame[frame.probability_mode.eq("empirical")].iloc[0].to_dict()
        at = pd.Timestamp(row["selection_built_at"]) + pd.Timedelta(minutes=1)
        raw = {
            "game_id": row["game_id"],
            "player_id": row["player_id"],
            "market": row["market"],
            "side": "over",
            "line": float(int(row["enhanced_projection"]) + 0.5),
            "decimal_odds": 1.9,
            "bookmaker": "SYNTHETIC TEST ONLY",
            "source": "Not a genuine quote",
            "quoted_at": at.isoformat(),
            "settlement_rule": "offensive_participation_full_refund_push",
        }
        record = evaluate(raw, frame, now=at)
        expected = price(row, raw["line"], 1.9, "over")
        self.assertAlmostEqual(record["hit_probability"], expected["over"])
        self.assertAlmostEqual(
            record["expected_profit_per_unit"], expected["over"] * 1.9 - 1
        )
        self.assertEqual(record["outcome_interval90"], [row["q05"], row["q95"]])
        roof = {**raw, "game_id": "2026_12_BAL_HOU"}
        with self.assertRaises(ValueError):
            evaluate(roof, frame, now=at)

    def test_authenticated_real_entrypoint_all_workspaces_without_network(self):
        from streamlit.testing.v1 import AppTest

        from release_utils import sha256

        _, _, current_release = serving.admit(
            serving.REMAINING_PROFILE, serving.REMAINING_RELEASE
        )
        with tempfile.TemporaryDirectory() as tmp:
            active = Path(tmp) / "selected.json"
            active.write_text(
                json.dumps(
                    {
                        "release_id": current_release["release_id"],
                        "profile": str(
                            serving.REMAINING_PROFILE.relative_to(serving.ROOT)
                        ),
                        "certificate_sha256": sha256(
                            serving.REMAINING_PROFILE / "certificate.json"
                        ),
                    }
                )
            )
            operational = Path(tmp) / "operational.json"
            operational.write_text(
                json.dumps(
                    {
                        "path": str(
                            serving.REMAINING_RELEASE.relative_to(serving.ROOT)
                        ),
                        "release_id": current_release["release_id"],
                        "manifest_sha256": sha256(
                            serving.REMAINING_RELEASE / "manifest.json"
                        ),
                        "checks": serving.read_json(
                            serving.REMAINING_PROFILE / "certificate.json"
                        )["checks"]["inference"],
                    }
                )
            )
            with (
                patch.object(serving, "OPERATIONAL", operational),
                patch.object(serving, "ACTIVE", active),
                patch.dict(
                    os.environ,
                    {
                        "RESEARCH_PREVIEW_PASSWORD": "synthetic-week12-test-only",
                        "SPORTSGAMEODDS_API_KEY": "",
                    },
                ),
                patch("requests.get") as get,
                patch("requests.request") as request,
            ):
                app = AppTest.from_file(
                    str(serving.ROOT / "odds_value_research.py"), default_timeout=180
                ).run()
                app.text_input(key="research_password").input(
                    "synthetic-week12-test-only"
                )
                app.button[0].click().run()
                self.assertFalse(app.exception, app.exception)
                self.assertTrue(any("Week 12" in x.value for x in app.markdown))
                for section in app.selectbox[0].options:
                    app.selectbox[0].select(section).run()
                    self.assertFalse(app.exception, (section, app.exception))
                    if section == "Top 2 by Game":
                        text = " ".join(x.value for x in app.markdown)
                        for game in self.fixtures.itertuples():
                            self.assertIn(f"{game.away_team} at {game.home_team}", text)
                get.assert_not_called()
                request.assert_not_called()
