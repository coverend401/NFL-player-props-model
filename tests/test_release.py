"""Release guard tests: corrupt/missing files, runtime drift, switching and rollback.

Synthetic byte payloads exercise the fast startup integrity guard. Real parquet,
model and prediction replay checks run against every generated release in CI.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import tempfile
import unittest

from release_utils import (
    DATA_FILES,
    INPUT_FILES,
    SOURCE_FILES,
    sha256,
    runtime_versions,
    validate_manifest,
    select_release,
    rollback_release,
    resolve_release,
)

REPO = Path(__file__).resolve().parents[1]


class ReleaseGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in SOURCE_FILES:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, self.root / name)
        runtime = json.loads((self.root / "release_runtime.json").read_text())
        runtime["python"] = ".".join(platform.python_version_tuple()[:2])
        (self.root / "release_runtime.json").write_text(json.dumps(runtime))
        (self.root / "data").mkdir()
        for name in DATA_FILES:
            (self.root / "data" / name).write_bytes(b"legacy fixture")
        (self.root / "ledger_local.db").write_bytes(
            b"bet history must remain untouched"
        )
        self.a = self.make("a")
        self.b = self.make("b")

    def make(self, rid):
        directory = self.root / "release_candidates" / rid
        for name in [*[f"data/{n}" for n in DATA_FILES], *INPUT_FILES]:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((rid + name).encode())
        manifest = {
            "schema_version": 1,
            "release_id": rid,
            "validation_status": "passed",
            "built_at": datetime.now(timezone.utc).isoformat(),
            "activate_before": "2099-01-01T00:00:00+00:00",
            "runtime": runtime_versions(self.root),
            "source_sha256": {n: sha256(self.root / n) for n in SOURCE_FILES},
            "legacy_data_sha256": {
                n: sha256(self.root / "data" / n) for n in DATA_FILES
            },
            "files": {
                n: {
                    "sha256": sha256(directory / n),
                    "bytes": (directory / n).stat().st_size,
                }
                for n in [*[f"data/{f}" for f in DATA_FILES], *INPUT_FILES]
            },
        }
        (directory / "manifest.json").write_text(json.dumps(manifest))
        return directory

    def change_manifest(self, directory, change):
        path = directory / "manifest.json"
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value))

    def test_whole_bundle_validates(self):
        self.assertEqual(validate_manifest(self.a, self.root)["release_id"], "a")

    def test_missing_model_rejected(self):
        (self.a / "data/model_receptions.joblib").unlink()
        with self.assertRaisesRegex(ValueError, "Missing or unexpected"):
            validate_manifest(self.a, self.root)

    def test_mixed_or_modified_artifact_rejected(self):
        shutil.copyfile(
            self.b / "data/model_receptions.joblib",
            self.a / "data/model_receptions.joblib",
        )
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            validate_manifest(self.a, self.root)

    def test_no_ledger_or_extra_files_can_enter_data_bundle(self):
        (self.a / "data/ledger_local.db").write_bytes(b"private")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            validate_manifest(self.a, self.root)

    def test_pending_build_never_activates(self):
        self.change_manifest(self.a, lambda m: m.update(validation_status="pending"))
        with self.assertRaisesRegex(ValueError, "not passed"):
            select_release(self.root, "release_candidates/a", "legacy")
        self.assertFalse((self.root / "active_release.json").exists())

    def test_expired_candidate_cannot_be_selected(self):
        self.change_manifest(
            self.a, lambda m: m.update(activate_before="2020-01-01T00:00:00+00:00")
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            select_release(self.root, "release_candidates/a", "legacy")

    def test_runtime_drift_rejected(self):
        self.change_manifest(
            self.a, lambda m: m["runtime"]["packages"].update(streamlit="0.0")
        )
        with self.assertRaisesRegex(ValueError, "runtime mismatch"):
            validate_manifest(self.a, self.root)

    def test_code_drift_rejected(self):
        (self.root / "pricing.py").write_text("changed")
        with self.assertRaisesRegex(ValueError, "code mismatch"):
            validate_manifest(self.a, self.root)

    def test_pointer_digest_rejects_a_changed_manifest(self):
        select_release(self.root, "release_candidates/a", "legacy")
        self.change_manifest(self.a, lambda m: m.update(release_id="someone-else"))
        with self.assertRaisesRegex(ValueError, "pointer/manifest"):
            resolve_release(self.root)

    def test_no_path_escape_or_symlinked_artifact(self):
        with self.assertRaisesRegex(ValueError, "escapes"):
            select_release(self.root, "../outside", "legacy")
        path = self.a / "data/model_receptions.joblib"
        path.unlink()
        path.symlink_to(self.b / "data/model_receptions.joblib")
        with self.assertRaisesRegex(ValueError, "regular files"):
            validate_manifest(self.a, self.root)

    def test_only_one_concurrent_selection_wins(self):
        def choose(name):
            try:
                select_release(self.root, "release_candidates/" + name, "legacy")
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            out = list(pool.map(choose, ["a", "b"]))
        self.assertEqual(sum(out), 1)
        resolve_release(self.root)

    def test_switch_and_rollback_preserve_all_bets(self):
        select_release(self.root, "release_candidates/a", "legacy")
        self.assertEqual(resolve_release(self.root)[1]["release_id"], "a")
        select_release(self.root, "release_candidates/b", "a")
        with self.assertRaisesRegex(ValueError, "Active release changed"):
            rollback_release(self.root, "a")
        rollback_release(self.root, "b")
        self.assertEqual(resolve_release(self.root)[1]["release_id"], "a")
        rollback_release(self.root, "a")
        self.assertEqual(resolve_release(self.root), (self.root / "data", None))
        self.assertEqual(
            (self.root / "ledger_local.db").read_bytes(),
            b"bet history must remain untouched",
        )

    def test_changed_legacy_fallback_stops_rollback(self):
        select_release(self.root, "release_candidates/a", "legacy")
        (self.root / "data/slate.parquet").write_bytes(b"not the saved fallback")
        with self.assertRaisesRegex(ValueError, "Legacy fallback changed"):
            rollback_release(self.root, "a")
        self.assertEqual(resolve_release(self.root)[1]["release_id"], "a")


class DataRefreshSeasonTests(unittest.TestCase):
    def test_january_refresh_does_not_request_nonexistent_next_season(self):
        import contextlib
        from datetime import date
        import io
        from types import SimpleNamespace
        from unittest.mock import patch
        import pandas as pd
        from scripts.update_data import update_data

        class JanuaryDate(date):
            @classmethod
            def today(cls):
                return cls(2027, 1, 5)

        frame = pd.DataFrame({"passing_interceptions": [0], "season": [2026]})
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("nflreadpy.utils_date.date", JanuaryDate),
            patch(
                "scripts.update_data.nfl.load_player_stats",
                return_value=SimpleNamespace(to_pandas=lambda: frame),
            ) as load,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            update_data(tmp)
            load.assert_called_once_with(seasons=list(range(2019, 2027)))
            saved = pd.read_parquet(Path(tmp) / "weekly_player_data.parquet")
            self.assertEqual(saved.interceptions.tolist(), [0])
