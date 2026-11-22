"""Explicit serving recertification; original runtime admission remains strict."""

import copy
import importlib.metadata
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from release_utils import read_json, runtime_versions, sha256
from research_platform import cloud_runtime as cloud
from scripts.certify_cloud_runtime import check_generated

TARGET = (
    sys.version_info[:2] == (3, 14)
    and importlib.metadata.version("certifi") == "2026.11.20"
)


class ServingContractTests(unittest.TestCase):
    def test_derived_validators_have_only_declared_runtime_changes(self):
        check_generated()

    def test_full_serving_lock_has_only_the_approved_certifi_change(self):
        old = cloud.pins(cloud.ROOT / "requirements-production.lock")
        new = cloud.pins(cloud.DIRECTORY / "requirements.lock")
        self.assertEqual(old.keys(), new.keys())
        self.assertEqual({k for k in old if old[k] != new[k]}, {"certifi"})
        self.assertEqual(new["certifi"], "2026.11.20")
        self.assertFalse((cloud.ROOT / "uv.toml").exists())

    def test_original_manifest_and_forecast_hashes_are_unchanged(self):
        self.assertEqual(
            sha256(
                cloud.ROOT
                / "research_inference_releases/research-week11-frozen-20261120-r2/manifest.json"
            ),
            "2ef8e0a19da56705e31d3af0f72b1b4dd71bd3a3a5d5a8c8fc4a5016d0e1a021",
        )
        baseline = read_json(cloud.DIRECTORY / "baseline_validation.json")
        certificate = read_json(cloud.DIRECTORY / "certificate.json")
        self.assertEqual(certificate["checks"], baseline["checks"])
        self.assertEqual(certificate["checks"]["forecasts"], 522)
        self.assertEqual(
            certificate["training_runtime"]["packages"]["certifi"], "2026.10.23"
        )
        self.assertEqual(
            certificate["serving_runtime"]["packages"]["certifi"], "2026.11.20"
        )

    def test_original_runtime_guard_is_not_weakened(self):
        if TARGET or sys.version_info[:2] != (3, 14):
            with self.assertRaises(ValueError):
                runtime_versions(cloud.ROOT)
        else:
            self.assertEqual(
                runtime_versions(cloud.ROOT)["packages"]["certifi"], "2026.10.23"
            )

    def test_unapproved_certifi_and_numerical_library_changes_are_rejected(self):
        original = importlib.metadata.version
        for package, version in [("certifi", "2026.10.23"), ("numpy", "0.0.0")]:

            def changed(name, package=package, version=version):
                if name == package:
                    return version
                return "2026.11.20" if name == "certifi" else original(name)

            with (
                patch("importlib.metadata.version", side_effect=changed),
                self.assertRaisesRegex(ValueError, "Serving runtime package mismatch"),
            ):
                cloud.runtime()

    def test_pending_incomplete_or_false_certificate_is_rejected(self):
        certificate_path = cloud.DIRECTORY / "certificate.json"
        original = cloud.read_json
        for kind in ["pending", "missing_file", "false_replay", "schema", "no_replay"]:
            certificate = copy.deepcopy(original(certificate_path))
            if kind == "pending":
                certificate["status"] = "pending"
            elif kind == "missing_file":
                certificate["files"].pop(next(iter(certificate["files"])))
            elif kind == "false_replay":
                certificate["checks"]["top2"] = 19
            elif kind == "schema":
                certificate["schema"] = 2
            else:
                certificate["checks"]["inference"]["exact_replay"] = False
            with (
                patch.object(
                    cloud,
                    "read_json",
                    side_effect=lambda p, certificate=certificate: (
                        certificate if Path(p) == certificate_path else original(p)
                    ),
                ),
                self.assertRaises(ValueError),
            ):
                cloud.admit()

    def test_changed_model_bytes_cannot_be_admitted(self):
        original = cloud.sha256
        with (
            patch.object(
                cloud,
                "sha256",
                side_effect=lambda p: (
                    "0" * 64
                    if Path(p).name == "model_rushing_yards.joblib"
                    else original(p)
                ),
            ),
            self.assertRaisesRegex(ValueError, "artifact/source mismatch"),
        ):
            cloud.admit()


@unittest.skipUnless(
    TARGET,
    "Serving UI is tested explicitly in CI after installing its exact Python 3.14 lock",
)
class CloudHostedTests(unittest.TestCase):
    def test_actual_serving_admission_authenticated_ui_and_manual_price(self):
        from datetime import UTC, datetime

        from streamlit.testing.v1 import AppTest

        directory, release = cloud.admit()
        self.assertEqual(
            release["serving_runtime"]["packages"]["certifi"], "2026.11.20"
        )
        self.assertEqual(len(pd.read_parquet(directory / "slate.parquet")), 618)
        at = datetime(2026, 11, 22, 18, 1, tzinfo=UTC)
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic-cloud-profile-only",
                    "NFL_RESEARCH_INFERENCE_POINTER": "",
                    "SPORTSGAMEODDS_API_KEY": "",
                    "SGO_GITHUB_QUOTA_TOKEN": "",
                    "SGO_RESEARCH_STORE": str(Path(tmp) / "cache.sqlite"),
                },
            ),
            patch("research_platform.enhanced_ui.datetime") as ui_clock,
            patch("research_platform.r8.datetime") as app_clock,
            patch("research_platform.selection_integrity.datetime") as audit_clock,
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            ui_clock.now.return_value = at
            app_clock.now.return_value = at
            audit_clock.now.return_value = at
            audit_clock.fromisoformat.side_effect = datetime.fromisoformat
            app = AppTest.from_file(
                str(cloud.ROOT / "odds_value_research.py"),
                default_timeout=180,
            ).run()
            app.text_input(key="research_password").input(
                "synthetic-cloud-profile-only"
            )
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertFalse(app.error)
            self.assertEqual(
                sum("enhanced-research-card" in x.value for x in app.markdown), 12
            )
            app.number_input(key="enhanced_top_line").set_value(5.5)
            app.number_input(key="enhanced_top_odds").set_value(2.0)
            app.run()
            self.assertTrue(
                any("Estimated research EV" in x.value for x in app.markdown)
            )
            next(x for x in app.selectbox if x.label == "Workspace").select(
                "Top 2 by Game"
            ).run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(
                sum("enhanced-research-card" in x.value for x in app.markdown), 20
            )
            self.assertTrue(
                any("HISTORICAL PRE-KICKOFF" in x.value for x in app.caption)
            )
            self.assertTrue(any("TEN at DAL" in x.value for x in app.markdown))
            self.assertTrue(any("unresolved roof" in x.value for x in app.info))
            for section in [
                "Player Intelligence",
                "Game Intelligence",
                "Model Performance",
                "Weekly Learning",
                "Data & Safety",
                "Parlay Research",
                "Market Intelligence",
            ]:
                next(x for x in app.selectbox if x.label == "Workspace").select(
                    section
                ).run()
                self.assertFalse(app.exception, app.exception)
            get.assert_not_called()
            request.assert_not_called()
