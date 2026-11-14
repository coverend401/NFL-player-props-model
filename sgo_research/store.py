"""Private development store. Never uses production Supabase or bankroll tables.

SQLite is durable only on an explicitly approved persistent volume. Community
Cloud ephemeral files are not certified: its UI is cache-only by default.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from .contracts import Unavailable, utc

ROOT = Path(__file__).resolve().parents[1]


class Store:
    def __init__(self, path, *, persistent=False):
        self.path = Path(path).expanduser().resolve()
        if self.path == ROOT or ROOT in self.path.parents:
            raise Unavailable("Research store must be outside the repository")
        self.persistent = persistent
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        with self.connection() as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS calls(at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS controls(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reservations(id INTEGER PRIMARY KEY, window TEXT NOT NULL, at TEXT NOT NULL, objects INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, at TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, at TEXT NOT NULL, payload TEXT NOT NULL, hash TEXT NOT NULL);""")

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=10)
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def http_slot(self, now):
        if not self.persistent:
            raise Unavailable("Persistent private quota store is not approved")
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT 1 FROM controls WHERE key='halt'").fetchone():
                raise Unavailable("Research collector halted; manual review required")
            n = c.execute(
                "SELECT COUNT(*) FROM calls WHERE at>?",
                ((now - timedelta(seconds=60)).isoformat(),),
            ).fetchone()[0]
            if n >= 6:
                raise Unavailable("Conservative six-request/minute limit reached")
            c.execute("INSERT INTO calls VALUES (?)", (now.isoformat(),))

    def halt(self, reason):
        with self.connection() as c:
            c.execute("INSERT OR REPLACE INTO controls VALUES ('halt',?)", (reason,))

    def reserve(self, limits, objects, now, *, cap=2000, headroom=200):
        if not self.persistent:
            raise Unavailable(
                "Live collection requires an approved persistent private volume"
            )
        month = limits["per-month"]
        end = utc(month["end"])
        if (
            end <= now
            or objects < 1
            or objects > 16
            or cap < 1
            or cap > 2000
            or headroom < 200
        ):
            raise Unavailable("Invalid quota reservation or expired provider interval")
        maximum = min(cap, month["max_entities"] - headroom, 2500 - headroom)
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            last = c.execute(
                "SELECT window FROM reservations ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if last and last[0] != end.isoformat() and utc(last[0]) > now:
                raise Unavailable(
                    "Provider interval changed before expiry; no budget reset"
                )
            if type(month.get("max_requests")) is int:
                if type(month.get("used_requests")) is not int:
                    raise Unavailable("Monthly request usage unavailable")
                local_requests = c.execute(
                    "SELECT COUNT(*) FROM calls WHERE at>?",
                    ((end - timedelta(days=30)).isoformat(),),
                ).fetchone()[0]
                if month["used_requests"] + local_requests + 1 > month["max_requests"]:
                    raise Unavailable("Free monthly request limit reached")
            reserved = c.execute(
                "SELECT COALESCE(SUM(objects),0) FROM reservations WHERE window=?",
                (end.isoformat(),),
            ).fetchone()[0]
            # Deliberate over-counting: do not refund on errors, empty responses,
            # process failure or eventually-consistent provider usage.
            if month["used_entities"] + reserved + objects > maximum:
                raise Unavailable(
                    "Free object budget/headroom reached; collection stopped"
                )
            for name, duration in [
                ("per-minute", 60),
                ("per-hour", 3600),
                ("per-day", 86400),
            ]:
                rule = limits.get(name, {})
                for limit_name, usage_name in [
                    ("max_requests", "used_requests"),
                    ("max_entities", "used_entities"),
                ]:
                    if (
                        type(rule.get(limit_name)) is int
                        and type(rule.get(usage_name)) is not int
                    ):
                        raise Unavailable("Finite account limit lacks current usage")
                local = c.execute(
                    "SELECT COUNT(*),COALESCE(SUM(objects),0) FROM reservations WHERE at>?",
                    ((now - timedelta(seconds=duration)).isoformat(),),
                ).fetchone()
                req_cap = 6 if name == "per-minute" else None
                if type(rule.get("max_requests")) is int:
                    req_cap = min(req_cap or rule["max_requests"], rule["max_requests"])
                used = (
                    rule.get("used_requests")
                    if type(rule.get("used_requests")) is int
                    else 0
                )
                if req_cap is not None and used + local[0] + 1 > req_cap:
                    raise Unavailable("Free request rate reached; no retry")
                if type(rule.get("max_entities")) is int:
                    used_obj = (
                        rule.get("used_entities")
                        if type(rule.get("used_entities")) is int
                        else 0
                    )
                    if used_obj + local[1] + objects > rule["max_entities"]:
                        raise Unavailable("Free interval object limit reached")
            c.execute(
                "INSERT INTO reservations(window,at,objects) VALUES (?,?,?)",
                (end.isoformat(), now.isoformat(), objects),
            )

    def cached(self, key, now, ttl=600):
        with self.connection() as c:
            c.execute(
                "DELETE FROM cache WHERE at<?",
                ((now - timedelta(hours=24)).isoformat(),),
            )
            row = c.execute("SELECT at,body FROM cache WHERE key=?", (key,)).fetchone()
        return (
            json.loads(row[1])
            if row and 0 <= (now - utc(row[0])).total_seconds() < ttl
            else None
        )

    def save_cache(self, key, payload, now):
        with self.connection() as c:
            c.execute(
                "DELETE FROM cache WHERE at<?",
                ((now - timedelta(hours=24)).isoformat(),),
            )
            c.execute(
                "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                (key, now.isoformat(), json.dumps(payload, allow_nan=False)),
            )

    def freeze_paper(self, decision):
        raise Unavailable(
            "Paper archival disabled pending separate retention and sealed-data policy approval"
        )

    def settle(self, *args, **kwargs):
        raise Unavailable(
            "Settlement is not authorised; sealed outcomes remain inaccessible"
        )
