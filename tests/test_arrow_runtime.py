"""Exercise the Arrow thread lifecycle reported in apache/arrow#50471."""

from pathlib import Path
import subprocess
import sys
import unittest


class ArrowRuntimeTests(unittest.TestCase):
    def test_short_lived_first_import_then_repeated_worker_allocations(self):
        # A fresh process matters: importing Arrow on the main thread would
        # conceal the upstream first-import-on-a-worker failure mechanism.
        result = subprocess.run(
            [sys.executable, "-c", """
import threading
errors = []
def first_import():
    try:
        import pyarrow
    except BaseException as e:
        errors.append(e)
t = threading.Thread(target=first_import)
t.start(); t.join()
def allocate():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        import pandas as pd
        import io
        table = pa.table({'name': ['player', None] * 5000,
                          'stat': [0.0, None] * 5000})
        data = io.BytesIO()
        pq.write_table(table, data)
        data.seek(0)
        restored = pq.read_table(data)
        assert restored.equals(table)
        frame = restored.to_pandas()
        assert frame.stat.isna().sum() == 5000
        assert (frame.stat == 0).sum() == 5000
    except BaseException as e:
        errors.append(e)
for _ in range(12):
    t = threading.Thread(target=allocate)
    t.start(); t.join()
assert not errors, repr(errors)
"""],
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cloud_supported_arrow_version_is_exactly_pinned(self):
        root = Path(__file__).resolve().parents[1]
        pins = (root / "requirements-production.lock").read_text().splitlines()
        self.assertEqual([p for p in pins if p.startswith("pyarrow==")],
                         ["pyarrow==24.0.0"])


if __name__ == "__main__":
    unittest.main()
