"""Negative fixtures: exercise the unchanged validator, never create a release.

Copies of the real bundle isolate two early provenance gates. Fixture table
metadata is changed only inside TemporaryDirectory; models stay byte-identical.
These are not Week 11 predictions, and neither fixture can pass certification.
"""

import json
import shutil
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from release_utils import DATA_FILES, sha256
from scripts.validate_release import validate_bundle

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Pinned release requires Python 3.14"
)
class FrozenModelPublicationContractTests(unittest.TestCase):
    def rejected_fixture(self, new_identity):
        pointer = json.loads((ROOT / "active_release.json").read_text())
        base = ROOT / pointer["path"]
        before = {p.name: sha256(p) for p in (base / "data").glob("*.joblib")}
        self.assertEqual(len(before), 9)
        with tempfile.TemporaryDirectory(prefix="negative-frozen-provenance-") as temp:
            candidate = Path(temp) / "negative-test-only"
            shutil.copytree(base, candidate)
            manifest_path = candidate / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            rid = (
                "negative-new-release-identity"
                if new_identity
                else manifest["release_id"]
            )
            prediction = datetime.now(UTC).isoformat()
            for name in DATA_FILES:
                if not name.endswith(".parquet"):
                    continue
                path = candidate / "data" / name
                frame = pd.read_parquet(path)
                frame["release_id"] = rid
                if name == "slate.parquet":
                    frame["prediction_at"] = prediction
                    frame["completed_before"] = "2026-11-19T00:00:00+00:00"
                frame.to_parquet(path, index=False)
                manifest["files"][f"data/{name}"] = {
                    "sha256": sha256(path),
                    "bytes": path.stat().st_size,
                }
            manifest.update(
                release_id=rid,
                build_started_at=prediction,
                built_at=datetime.now(UTC).isoformat(),
                validation_status="pending",
                negative_test_only=True,
            )
            manifest_path.write_text(json.dumps(manifest))
            error = (
                "Mixed or legacy model"
                if new_identity
                else "Future/stale build provenance"
            )
            # All existing integrity, source/runtime and model gates stay enabled.
            with self.assertRaisesRegex(ValueError, error) as caught:
                validate_bundle(candidate, repo=ROOT, allow_pending=True)
            self.assertEqual(
                before,
                {p.name: sha256(p) for p in (candidate / "data").glob("*.joblib")},
            )
        self.assertEqual(
            before, {p.name: sha256(p) for p in (base / "data").glob("*.joblib")}
        )
        return str(caught.exception)

    def test_new_release_rejects_unchanged_frozen_model_identity(self):
        self.assertIn("Mixed or legacy model:", self.rejected_fixture(True))

    def test_old_release_identity_does_not_make_old_training_a_new_build(self):
        self.assertIn("Future/stale build provenance:", self.rejected_fixture(False))
