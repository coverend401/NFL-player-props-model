"""Offline installer regression using synthetic wheels, never application packages."""

import base64
import hashlib
import importlib.metadata
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from research_platform import startup_diagnostics as diagnostics

ROOT = Path(__file__).resolve().parents[1]


class CloudDependencyTests(unittest.TestCase):
    def test_constraint_matches_original_approved_lock(self):
        cfg = tomllib.loads((ROOT / "uv.toml").read_text())
        pins = (ROOT / "requirements-production.lock").read_text().splitlines()
        self.assertEqual(
            cfg["constraint-dependencies"],
            [next(x for x in pins if x.startswith("certifi=="))],
        )

    def test_all_runtime_mismatches_are_reported_together(self):
        original = importlib.metadata.version

        def changed(name):
            return {"certifi": "2026.11.20", "joblib": "0.0.0"}.get(name) or original(
                name
            )

        with (
            patch("importlib.metadata.version", side_effect=changed),
            patch(
                "research_platform.inference_release.resolve_research_release",
                side_effect=ValueError(
                    "Runtime package mismatch: certifi: expected 2026.10.23, found 2026.11.20"
                ),
            ),
        ):
            result = diagnostics.preflight()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(
            {x["package"] for x in result["package_mismatches"]}, {"certifi", "joblib"}
        )

    def test_late_uv_upgrade_cannot_escape_approved_constraint(self):
        uv = shutil.which("uv")
        self.assertIsNotNone(
            uv, "Install the pinned CI-only uv tool to exercise deployment resolution"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                **os.environ,
                "UV_CACHE_DIR": str(root / "cache"),
                "UV_PYTHON_DOWNLOADS": "never",
            }
            for key in [
                "UV_CONFIG_FILE",
                "UV_NO_CONFIG",
                "UV_CONSTRAINT",
                "UV_OVERRIDE",
            ]:
                env.pop(key, None)

            def command(args, succeeds=True):
                p = subprocess.run(
                    [uv, *args],
                    check=False,
                    cwd=root,
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=60,
                )
                self.assertEqual(p.returncode == 0, succeeds, p.stdout + p.stderr)

            def version():
                return subprocess.check_output(
                    [
                        str(python),
                        "-c",
                        "import importlib.metadata;print(importlib.metadata.version('certifi'))",
                    ],
                    text=True,
                ).strip()

            for value in ["2026.10.23", "2026.11.20"]:
                dist = f"certifi-{value}.dist-info"
                files = {
                    "certifi/__init__.py": f"__version__ = {value!r}\n".encode(),
                    dist
                    + "/METADATA": f"Metadata-Version: 2.1\nName: certifi\nVersion: {value}\n".encode(),
                    dist
                    + "/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                }
                record = "".join(
                    f"{name},sha256={base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')},{len(data)}\n"
                    for name, data in files.items()
                )
                files[dist + "/RECORD"] = (record + dist + "/RECORD,,\n").encode()
                with zipfile.ZipFile(
                    root / f"certifi-{value}-py3-none-any.whl", "w"
                ) as z:
                    for name, data in files.items():
                        z.writestr(name, data)
            target = root / "venv"
            python = target / "bin/python"
            command(["--no-config", "venv", "--python", sys.executable, str(target)])
            install = [
                "pip",
                "install",
                "--python",
                str(python),
                "--no-index",
                "--find-links",
                str(root),
                "--upgrade",
            ]
            command(["--no-config", *install, "certifi"])
            self.assertEqual(version(), "2026.11.20")
            shutil.copyfile(ROOT / "uv.toml", root / "uv.toml")
            command([*install, "certifi"])
            self.assertEqual(version(), "2026.10.23")
            command([*install, "certifi"])
            self.assertEqual(version(), "2026.10.23")
            command([*install, "certifi==2026.11.20"], succeeds=False)
            self.assertEqual(version(), "2026.10.23")
