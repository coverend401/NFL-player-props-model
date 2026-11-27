"""Atomic research-only publication under standing authority; no main/production writes."""

import json
import os
from datetime import UTC, datetime

import pandas as pd

from .authority import PATH, paths, validate
from .store import ROOT, encoded, sha

CATALOG = ROOT / "weekly_learning_state/serving_catalog.json"


def publish_validated(store, directory, profile, revision, plan):
    paths(profile, directory)
    policy = validate(directory)
    from research_platform.weekly_serving import ACTIVE, OPERATIONAL, admit

    _, _, release = admit(profile, directory)
    certificate = json.loads((profile / "certificate.json").read_text())
    now = datetime.now(UTC)
    if not all(
        pd.Timestamp(now) < pd.Timestamp(t) - pd.Timedelta(minutes=60)
        for t in release["game_kickoffs"].values()
    ):
        raise ValueError(
            "Routine publication deadline passed; prepare a fresh future-only candidate"
        )
    before_active = json.loads(ACTIVE.read_text()) if ACTIVE.exists() else None
    before_operational = (
        json.loads(OPERATIONAL.read_text()) if OPERATIONAL.exists() else None
    )
    if before_operational:
        old = json.loads(
            (ROOT / before_operational["path"] / "manifest.json").read_text()
        )
        if pd.Timestamp(old["prediction_at"]) > pd.Timestamp(release["prediction_at"]):
            raise ValueError("Refusing to replace a newer forecast")
    if before_active and before_active.get("certificate_sha256") == sha(
        profile / "certificate.json"
    ):
        return {"status": "already_current", "release_id": release["release_id"]}
    storage = {
        "verified": False,
        "mode": "forecast_only",
        "reason": "Private quoted-selection storage is not configured",
    }
    from selection_learning.probe import probe
    from selection_learning.store import GitHubJournal

    if os.environ.get("NFL_SELECTION_GITHUB_REPOSITORY") and os.environ.get(
        "NFL_SELECTION_GITHUB_TOKEN"
    ):
        try:
            storage = {
                "verified": True,
                "mode": "quoted_research_enabled",
                **probe(
                    GitHubJournal(
                        os.environ["NFL_SELECTION_GITHUB_REPOSITORY"],
                        os.environ["NFL_SELECTION_GITHUB_TOKEN"],
                    )
                ),
            }
        except (ValueError, OSError, KeyError, TypeError):
            storage = {
                "verified": False,
                "mode": "forecast_only",
                "reason": "Private storage failed verification; no quoted selection recording permitted",
            }
    if not storage["verified"] and not policy["allow_forecast_only_publication"]:
        raise ValueError("Private storage verification required")
    now = datetime.now(UTC)
    if not all(
        pd.Timestamp(now) < pd.Timestamp(t) - pd.Timedelta(minutes=60)
        for t in release["game_kickoffs"].values()
    ):
        raise ValueError("Publication deadline passed during checks")
    entry = {
        "path": str(directory.relative_to(ROOT)),
        "release_id": release["release_id"],
        "profile": str(profile.relative_to(ROOT)),
        "manifest_sha256": sha(directory / "manifest.json"),
        "certificate_sha256": sha(profile / "certificate.json"),
        "authority_sha256": sha(profile / "authority.json"),
        "code_revision": revision,
        "published_at": now.isoformat(),
        "storage": storage,
    }
    pointer = {k: entry[k] for k in ["release_id", "profile", "certificate_sha256"]}
    operational = {
        "path": entry["path"],
        "release_id": release["release_id"],
        "manifest_sha256": entry["manifest_sha256"],
        "selected_at": now.isoformat(),
        "checks": certificate["checks"]["inference"],
    }
    catalog = (
        json.loads(CATALOG.read_text())
        if CATALOG.exists()
        else {"schema": 1, "releases": {}}
    )
    previous_catalog = json.loads(json.dumps(catalog))
    catalog["releases"][entry["profile"]] = entry
    with store.transaction():
        if (
            json.loads(ACTIVE.read_text()) if ACTIVE.exists() else None
        ) != before_active or (
            json.loads(OPERATIONAL.read_text()) if OPERATIONAL.exists() else None
        ) != before_operational:
            raise ValueError("Concurrent publication changed; stop without overwriting")
        store.publish(
            "routine_publications",
            plan["run_id"],
            documents={
                "publication.json": entry,
                "rollback.json": {
                    "active": before_active,
                    "operational": before_operational,
                    "catalog": previous_catalog,
                },
            },
        )
        for path, value in [
            (CATALOG, catalog),
            (OPERATIONAL, operational),
            (ACTIVE, pointer),
        ]:
            temp = path.with_name("." + path.name + ".next")
            with temp.open("x") as out:
                out.write(encoded(value))
            os.replace(temp, path)
        store.audit(
            "routine_forecast_published",
            {
                "release_id": release["release_id"],
                "code_revision": revision,
                "model_promoted": False,
                "authority": sha(PATH),
            },
        )
    return {
        "status": "published_to_research_worktree",
        "release_id": release["release_id"],
        "storage_mode": storage["mode"],
        "requires_normal_research_branch_push": True,
    }
