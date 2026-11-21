"""Focused inference contract tests; no fitting, downloads, odds or production writes."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from release_utils import resolve_release as resolve_training_release
from release_utils import sha256, validate_manifest
from research_platform.inference_builder import derive_eligibility, eligibility_map
from research_platform.inference_release import (
    resolve_research_release,
    validate_inference,
)

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "research_inference_releases/research-week11-frozen-20261120-r2"
POINTER = str(CANDIDATE.relative_to(ROOT) / "selection.json")


class EligibilityInputTests(unittest.TestCase):
    def inputs(self, status="DEV", at="2026-11-20T10:00:00Z", team="KC"):
        state = pd.DataFrame(
            [
                {
                    "player_id": "synthetic",
                    "player_display_name": "Synthetic",
                    "team": "KC",
                }
            ]
        )
        roster = pd.DataFrame(
            [
                {
                    "gsis_id": "synthetic",
                    "team": team,
                    "status": status,
                    "season": 2026,
                    "week": 11,
                }
            ]
        )
        games = pd.DataFrame(
            [
                {
                    "game_id": "future",
                    "game_type": "REG",
                    "season": 2026,
                    "week": 11,
                    "home_team": "KC",
                    "away_team": "ARI",
                    "kickoff_at": "2026-11-22T18:00:00Z",
                    "home_score": None,
                    "away_score": None,
                }
            ]
        )
        source = {
            "retrieved_at": at,
            "url": "https://example.test/roster",
            "sha256": "a" * 64,
        }
        return state, roster, games, source

    def test_practice_squad_can_be_superseded_by_documented_elevation(self):
        s, r, g, source = self.inputs()
        first = derive_eligibility(s, r, g, "2026-11-20T12:00Z", source)
        self.assertEqual(first["players"][0]["status"], "ineligible")
        r["status"] = "ACT"
        source["retrieved_at"] = "2026-11-21T10:00Z"
        raised = derive_eligibility(s, r, g, "2026-11-21T12:00Z", source)
        self.assertEqual(raised["players"][0]["status"], "eligible")
        with self.assertRaises(ValueError):
            derive_eligibility(s, r, g, "2026-11-20T12:00Z", source)

    def test_stale_roster_or_absence_stays_explicitly_unresolved(self):
        s, r, g, source = self.inputs("ACT")
        r["week"] = 9
        d = derive_eligibility(s, r, g, "2026-11-20T12:00Z", source)
        self.assertEqual(d["players"][0]["status"], "unresolved")
        self.assertIsNone(d["players"][0]["team"])

    def test_current_identity_does_not_rewrite_historical_team(self):
        s, r, g, source = self.inputs("ACT", team="HOU")
        d = derive_eligibility(s, r, g, "2026-11-20T12:00Z", source)
        self.assertEqual(d["players"][0]["team"], "HOU")
        self.assertEqual(d["players"][0]["status"], "ineligible")
        self.assertEqual(s.iloc[0].team, "KC")

    def test_duplicate_future_and_unsupported_status_evidence_rejected(self):
        s, r, g, source = self.inputs("ACT")
        doc = derive_eligibility(s, r, g, "2026-11-20T12:00Z", source)
        doc["players"].append(dict(doc["players"][0]))
        with self.assertRaises(ValueError):
            eligibility_map(doc, "2026-11-20T12:00Z")
        doc["players"] = doc["players"][:1]
        doc["players"][0]["effective_at"] = "2026-11-21T00:00Z"
        with self.assertRaises(ValueError):
            eligibility_map(doc, "2026-11-20T12:00Z")


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Immutable parent uses Python 3.14"
)
class CertifiedInferenceTests(unittest.TestCase):
    def clone(self):
        temp = tempfile.TemporaryDirectory(prefix="negative-inference-")
        self.addCleanup(temp.cleanup)
        p = Path(temp.name) / "candidate"
        shutil.copytree(CANDIDATE, p)
        return p

    def manifest(self, directory, mutate):
        path = directory / "manifest.json"
        m = json.loads(path.read_text())
        mutate(m)
        path.write_text(json.dumps(m))

    def rehash_test_input(self, directory, name):
        # Negative fixture only: test semantic guards behind file integrity.
        self.manifest(
            directory,
            lambda m: m["files"].update(
                {
                    name: {
                        "sha256": sha256(directory / name),
                        "bytes": (directory / name).stat().st_size,
                    }
                }
            ),
        )

    def test_actual_forecasts_and_top_picks_exact_replay_without_global_mutation(self):
        from scripts import build_slate as original

        before = dict(original.build_slate.__globals__)
        report = validate_inference(CANDIDATE, ROOT, replay=True)
        self.assertEqual(report["forecast_rows"], 618)
        self.assertEqual(report["fixtures"], 12)
        self.assertEqual(report["top_picks"], 22)
        self.assertEqual(report["models_verified"], 9)
        self.assertTrue(report["exact_replay"])
        self.assertIs(
            before["upcoming_player_state"],
            original.build_slate.__globals__["upcoming_player_state"],
        )
        self.assertIs(
            before["get_upcoming_week"],
            original.build_slate.__globals__["get_upcoming_week"],
        )

    def test_old_training_contract_is_not_used_or_changed(self):
        with self.assertRaisesRegex(
            ValueError, "Unsupported or incomplete release manifest"
        ):
            validate_manifest(CANDIDATE, ROOT)
        m = json.loads((CANDIDATE / "manifest.json").read_text())
        parent = ROOT / m["model_parent"]["path"]
        pm = json.loads((parent / "manifest.json").read_text())
        for name, digest in pm["source_sha256"].items():
            self.assertEqual(sha256(ROOT / name), digest)
        for entry in m["models"].values():
            self.assertLess(
                pd.Timestamp(entry["training_as_of"]),
                pd.Timestamp(m["forecast_build_started_at"]),
            )

    def test_frozen_model_hash_and_training_timestamp_tampering_rejected(self):
        for field, value in [
            ("sha256", "0" * 64),
            ("training_as_of", "2026-11-20T00:00:00Z"),
        ]:
            with self.subTest(field=field):
                p = self.clone()
                self.manifest(
                    p,
                    lambda m, field=field, value=value: m["models"][
                        "passing_yards"
                    ].update({field: value}),
                )
                with self.assertRaises(ValueError):
                    validate_inference(p, ROOT)

    def test_unresolved_cannot_be_silently_promoted_to_eligible(self):
        p = self.clone()
        d = json.loads((p / "eligibility.json").read_text())
        e = next(x for x in d["players"] if x["status"] == "unresolved")
        e.update(
            status="eligible", team=e["historical_team"], effective_at=e["available_at"]
        )
        (p / "eligibility.json").write_text(json.dumps(d))
        self.rehash_test_input(p, "eligibility.json")
        with self.assertRaisesRegex(ValueError, "Eligibility decisions differ"):
            validate_inference(p, ROOT)

    def test_nikko_and_unresolved_are_absent_and_no_started_fixtures_exist(self):
        m = json.loads((CANDIDATE / "manifest.json").read_text())
        doc = json.loads((CANDIDATE / "eligibility.json").read_text())
        rows = {r["player_id"]: r for r in doc["players"]}
        nikko = rows["00-0038519"]
        self.assertEqual(nikko["team"], "HOU")
        self.assertEqual(nikko["status"], "ineligible")
        slate = pd.read_parquet(CANDIDATE / "slate.parquet")
        self.assertNotIn("00-0038519", set(slate.player_id))
        for pid in ["00-0035662", "00-0036893", "00-0037258", "00-0040218"]:
            self.assertEqual(rows[pid]["status"], "unresolved")
            self.assertNotIn(pid, set(slate.player_id))
        self.assertTrue(
            all(rows[pid]["status"] == "eligible" for pid in slate.player_id)
        )
        self.assertTrue(
            all(
                pd.Timestamp(k)
                > pd.Timestamp(m["prediction_at"]) + pd.Timedelta(minutes=60)
                for k in m["game_kickoffs"].values()
            )
        )

    def test_exact_replay_rejects_changed_forecast_or_top_pick(self):
        for name, column in [
            ("slate.parquet", "projection"),
            ("top_picks.parquet", "confidence"),
        ]:
            with self.subTest(artifact=name):
                p = self.clone()
                frame = pd.read_parquet(p / name)
                frame.loc[0, column] += 0.01
                frame.to_parquet(p / name, index=False)
                self.rehash_test_input(p, name)
                with self.assertRaises(AssertionError):
                    validate_inference(p, ROOT, replay=True)

    def test_integrity_and_missing_replay_certificate_fail_closed(self):
        p = self.clone()
        with (p / "slate.parquet").open("ab") as f:
            f.write(b"synthetic corruption")
        with self.assertRaisesRegex(ValueError, "integrity"):
            validate_inference(p, ROOT)
        p = self.clone()
        self.manifest(
            p, lambda m: m["certification"]["checks"].update(exact_replay=False)
        )
        with self.assertRaisesRegex(ValueError, "exact-replay certified"):
            validate_inference(p, ROOT)

    def test_sealed_outcomes_and_unavailable_history_rejected(self):
        for kind in ["sealed_history", "late_history", "fixture_outcome"]:
            with self.subTest(kind=kind):
                p = self.clone()
                name = (
                    "schedule.parquet"
                    if kind == "fixture_outcome"
                    else "features.parquet"
                )
                frame = pd.read_parquet(p / name)
                if kind == "sealed_history":
                    frame.loc[0, ["season", "week"]] = [2026, 11]
                elif kind == "late_history":
                    frame.loc[0, "completed_at"] = pd.Timestamp("2026-11-20T00:00Z")
                else:
                    index = frame.index[frame.season.eq(2026) & frame.week.eq(11)][0]
                    frame.loc[index, "home_score"] = (
                        7  # synthetic negative fixture only
                    )
                frame.to_parquet(p / name, index=False)
                self.rehash_test_input(p, name)
                with self.assertRaises(ValueError):
                    validate_inference(p, ROOT)

    def test_missing_candidate_eligibility_cannot_be_hidden(self):
        p = self.clone()
        d = json.loads((p / "eligibility.json").read_text())
        d["players"].pop()
        (p / "eligibility.json").write_text(json.dumps(d))
        self.rehash_test_input(p, "eligibility.json")
        with self.assertRaises(ValueError):
            validate_inference(p, ROOT)

    def test_research_default_is_week11_and_production_default_stays_week10(self):
        _, old = resolve_training_release(ROOT)
        self.assertEqual(old["release_id"], "stage1a-20261113-py314-arrow24-r2")
        with patch.dict(os.environ, {"NFL_RESEARCH_INFERENCE_POINTER": ""}):
            _, selected = resolve_research_release(ROOT)
        self.assertEqual(selected["release_id"], "research-week11-frozen-20261120-r2")
        directory, m = resolve_research_release(ROOT, pointer=POINTER)
        self.assertEqual(directory, CANDIDATE)
        self.assertEqual(m["release_type"], "research_frozen_model_inference_v1")

    def test_real_authenticated_research_entrypoint_loads_current_candidate(self):
        from streamlit.testing.v1 import AppTest

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "NFL_RESEARCH_INFERENCE_POINTER": "",
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic_inference_test",
                    "SPORTSGAMEODDS_API_KEY": "",
                    "SGO_RESEARCH_STORE": str(Path(tmp) / "cache.sqlite"),
                },
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            app = AppTest.from_file(
                str(ROOT / "odds_value_research.py"), default_timeout=90
            ).run()
            app.text_input(key="research_password").input("synthetic_inference_test")
            app.button[0].click().run(timeout=90)
            self.assertFalse(app.exception, app.exception)
            self.assertFalse(
                any("Stale forecast slate" in w.value for w in app.warning)
            )
            self.assertTrue(any("Eligible: 10" in c.value for c in app.caption))
            self.assertTrue(
                any("NO VERIFIED BOOKMAKER VALUE" in t.value for t in app.markdown)
            )
            next(x for x in app.selectbox if x.label == "Workspace").select(
                "Top 2 by Game"
            ).run(timeout=90)
            self.assertFalse(app.exception, app.exception)
            cards = [e for e in app.markdown if '<article class="desk-card' in e.value]
            self.assertEqual(len(cards), 20)
            get.assert_not_called()
            request.assert_not_called()
