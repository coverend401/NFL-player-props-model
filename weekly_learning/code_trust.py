"""Reuse green code evidence across data-only publications, never across code changes."""

import hashlib
import json
import subprocess

from .store import ROOT, sha


def code_paths():
    names = []
    for folder in [
        "weekly_learning",
        "selection_learning",
        "research_platform",
        "season_intelligence",
        "scripts",
    ]:
        names += [str(p.relative_to(ROOT)) for p in (ROOT / folder).glob("*.py")]
    names += [
        "research_access.py",
        "odds_value_research.py",
        "release_utils.py",
        "requirements.txt",
        "requirements-production.lock",
        "research_runtime_profiles/week11-certifi-20261120-v1/requirements.lock",
        "weekly_learning/standing_authority.json",
        ".github/workflows/routine_learning.yml",
        ".github/workflows/weekly_learning.yml",
        ".github/workflows/tests.yml",
    ]
    return sorted(set(names))


def fingerprint():
    return hashlib.sha256(
        json.dumps({n: sha(ROOT / n) for n in code_paths()}, sort_keys=True).encode()
    ).hexdigest()


def approved_code(store):
    paths = code_paths() + ["weekly_learning/standing_authority.json"]
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--", *paths], cwd=ROOT, text=True
    )
    if dirty:
        raise ValueError("Publication blocked: uncommitted operational code")
    identity = fingerprint()
    existing = store.root / "code_approvals" / identity[:24]
    if existing.exists():
        store.validate(existing)
        revision = json.loads((existing / "approval.json").read_text())["revision"]
    else:
        revision = subprocess.check_output(
            ["git", "log", "-1", "--format=%H", "--", *paths], cwd=ROOT, text=True
        ).strip()
    result = json.loads(
        subprocess.check_output(
            [
                "gh",
                "api",
                f"repos/coverend401/NFL-player-props-model/commits/{revision}/check-runs",
            ],
            cwd=ROOT,
            text=True,
        )
    )
    checks = {r["name"]: r.get("conclusion") for r in result.get("check_runs", [])}
    if any(
        checks.get(name) != "success"
        for name in ["cycle", "regression (3.12)", "regression (3.14)"]
    ):
        raise ValueError(
            "Publication blocked: approved code revision does not have all required green checks"
        )
    if not existing.exists():
        with store.transaction():
            store.publish(
                "code_approvals",
                identity[:24],
                documents={
                    "approval.json": {
                        "fingerprint": identity,
                        "revision": revision,
                        "checks": checks,
                    }
                },
            )
    return revision
