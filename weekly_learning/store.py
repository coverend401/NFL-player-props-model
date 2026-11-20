"""Immutable bundles and append-only hash-chain audit, protected by a local lock.

Scheduled persistence uses normal non-force git push; a concurrent remote commit
rejects the push rather than overwriting it. An interrupted local lock fails closed.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False, default=str) + "\n"
    )


def safe_id(value):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}", value):
        raise ValueError("Unsafe state ID")
    return value


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if self.root.is_relative_to(ROOT) and not self.root.is_relative_to(
            ROOT / "weekly_learning_state"
        ):
            raise ValueError(
                "Repository learning writes must stay under weekly_learning_state"
            )
        if (
            self.root == ROOT
            or self.root.is_relative_to(ROOT / "data")
            or self.root.is_relative_to(ROOT / "release_candidates")
        ):
            raise ValueError("Learning state must be isolated from production")
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def transaction(self):
        lock = self.root / ".writer.lock"
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            yield
        finally:
            lock.unlink()

    def validate(self, path):
        path = Path(path)
        m = json.loads((path / "manifest.json").read_text())
        for name, digest in m["files"].items():
            if Path(name).name != name or sha(path / name) != digest:
                raise ValueError("Learning bundle integrity mismatch")
        if {p.name for p in path.iterdir()} != set(m["files"]) | {"manifest.json"}:
            raise ValueError("Unexpected learning bundle files")
        return m

    def publish(self, kind, name, frames=None, documents=None, copies=None):
        target = self.root / safe_id(kind) / safe_id(name)
        if target.exists():
            raise ValueError("Immutable learning bundle already exists")
        target.parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent, prefix=".stage-") as temp:
            stage = Path(temp) / "bundle"
            stage.mkdir()
            for n, frame in (frames or {}).items():
                if Path(n).name != n:
                    raise ValueError("Unsafe file name")
                frame.to_parquet(stage / n, index=False)
            for n, value in (documents or {}).items():
                if Path(n).name != n:
                    raise ValueError("Unsafe document name")
                (stage / n).write_text(encoded(value))
            for n, source in (copies or {}).items():
                if Path(n).name != n:
                    raise ValueError("Unsafe copy name")
                shutil.copyfile(source, stage / n)
            m = {
                "schema": 1,
                "kind": kind,
                "id": name,
                "files": {p.name: sha(p) for p in sorted(stage.iterdir())},
            }
            (stage / "manifest.json").write_text(encoded(m))
            self.validate(stage)
            stage.rename(target)
        self.audit(
            "bundle_committed",
            {
                "kind": kind,
                "id": name,
                "manifest_sha256": sha(target / "manifest.json"),
            },
        )
        return target

    def audit(self, action, details):
        folder = self.root / "audit"
        folder.mkdir(exist_ok=True)
        files = sorted(folder.glob("*.json"))
        previous = None
        for file in files:
            event = json.loads(file.read_text())
            if event["previous_sha256"] != previous:
                raise ValueError("Audit hash chain mismatch")
            previous = sha(file)
        event = {
            "at": datetime.now(UTC).isoformat(),
            "action": action,
            "details": details,
            "previous_sha256": previous,
        }
        path = folder / f"{len(files):06d}.json"
        with path.open("x") as f:
            f.write(encoded(event))

    def reserve_holdout(
        self, block, protocol_sha, *, fresh=False, registered_before=None
    ):
        folder = self.root / "holdouts"
        folder.mkdir(exist_ok=True)
        path = folder / (safe_id(block) + ".json")
        if path.exists():
            old = json.loads(path.read_text())
            if old["protocol_sha256"] != protocol_sha:
                raise ValueError(
                    "Holdout already consumed by another protocol; no new test"
                )
            return {**old, "replay_only": True}
        if fresh and (
            registered_before is None
            or datetime.now(UTC) >= datetime.fromisoformat(registered_before)
        ):
            raise ValueError(
                "Fresh holdout must be registered before its first decision"
            )
        record = {
            "registered_at": datetime.now(UTC).isoformat(),
            "block": block,
            "protocol_sha256": protocol_sha,
            "fresh": bool(fresh),
            "registered_before": registered_before,
            "replay_only": False,
        }
        with path.open("x") as f:
            f.write(encoded(record))
        self.audit("holdout_reserved", record)
        return record
