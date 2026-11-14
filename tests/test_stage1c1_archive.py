"""Committed diagnostics require the exact validated production-target runtime."""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import pandas as pd

from stage1b.artifacts import digest
from stage1c1.artifacts import validate

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "experiments/stage1c1/controlled-20261114-v1"


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Pinned research archives require Python 3.14"
)
class ArchiveTests(unittest.TestCase):
    def test_complete_model_matrix_and_population(self):
        audit = validate(ARCHIVE, ROOT)
        self.assertEqual(audit["models"], 360)
        self.assertEqual(audit["versions"], 9)
        self.assertEqual(audit["player_market_games"], 55303)
        self.assertTrue(audit["final_sealed"])
        self.assertTrue(audit["oracle_outputs_separate"])

    def test_payload_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "archive"
            shutil.copytree(ARCHIVE, target)
            with (target / "accuracy.csv").open("a") as handle:
                handle.write("tampered\n")
            with self.assertRaisesRegex(ValueError, "payload mismatch"):
                validate(target, ROOT)

    def test_oracle_cannot_be_relabelled_as_forecast_even_with_new_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "archive"
            shutil.copytree(ARCHIVE, target)
            path = target / "oracle_diagnostics.parquet"
            d = pd.read_parquet(path)
            d.loc[0, "candidate_forecast"] = True
            d.to_parquet(path, index=False)
            manifest = target / "manifest.json"
            m = json.loads(manifest.read_text())
            m["files"][path.name] = digest(path)
            manifest.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, "Oracle/forecast separation"):
                validate(target, ROOT)


if __name__ == "__main__":
    unittest.main()
