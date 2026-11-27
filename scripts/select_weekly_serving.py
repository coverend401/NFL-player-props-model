"""Explicit owner-approved selection only; this command never merges or updates production."""

import argparse
import json
import os
from datetime import UTC, datetime

import pandas as pd

from release_utils import read_json, sha256
from research_platform.weekly_serving import (
    ACTIVE,
    CANDIDATES,
    OPERATIONAL,
    PROFILE,
    admit,
)
from weekly_learning.store import ROOT, Store, encoded


def select(approved_release, expected_certificate, approval_reference, profile=PROFILE):
    directory = CANDIDATES[profile]
    _frame, _fixtures, release = admit(profile, directory)
    if (
        approved_release != release["release_id"]
        or expected_certificate != sha256(profile / "certificate.json")
        or not approval_reference.strip()
    ):
        raise ValueError("Explicit release/certificate/owner approval required")
    now = datetime.now(UTC)
    if not all(
        pd.Timestamp(now) < pd.Timestamp(t) - pd.Timedelta(minutes=60)
        for t in release["game_kickoffs"].values()
    ):
        raise ValueError("Activation deadline passed; prepare a new candidate")
    pointer = {
        "release_id": approved_release,
        "profile": str(profile.relative_to(ROOT)),
        "certificate_sha256": expected_certificate,
    }
    from research_access import secret
    from selection_learning.probe import probe
    from selection_learning.store import GitHubJournal

    storage = probe(
        GitHubJournal(
            secret("NFL_SELECTION_GITHUB_REPOSITORY"),
            secret("NFL_SELECTION_GITHUB_TOKEN"),
        )
    )
    now = datetime.now(UTC)
    if not all(
        pd.Timestamp(now) < pd.Timestamp(t) - pd.Timedelta(minutes=60)
        for t in release["game_kickoffs"].values()
    ):
        raise ValueError("Activation deadline passed during storage verification")
    previous = read_json(ACTIVE) if ACTIVE.exists() else None
    previous_operational = read_json(OPERATIONAL) if OPERATIONAL.exists() else None
    operational = {
        "path": str(directory.relative_to(ROOT)),
        "release_id": approved_release,
        "manifest_sha256": sha256(directory / "manifest.json"),
        "selected_at": now.isoformat(),
        "checks": read_json(profile / "certificate.json")["checks"]["inference"],
    }
    store = Store(ROOT / "weekly_learning_state")
    with store.transaction():
        if (read_json(ACTIVE) if ACTIVE.exists() else None) != previous or (
            read_json(OPERATIONAL) if OPERATIONAL.exists() else None
        ) != previous_operational:
            raise ValueError("Concurrent release selection changed; stop")
        store.publish(
            "serving_selections",
            approved_release,
            documents={
                "selection.json": pointer,
                "approval.json": {
                    "reference": approval_reference,
                    "at": now.isoformat(),
                    "previous": previous,
                    "previous_operational": previous_operational,
                    "private_storage_verified": storage,
                },
            },
        )
        operational_temp = OPERATIONAL.with_name(".selected_research.next.json")
        with operational_temp.open("x") as out:
            out.write(encoded(operational))
        os.replace(operational_temp, OPERATIONAL)
        temp = ACTIVE.with_name(".research_weekly_serving.next.json")
        with temp.open("x") as out:
            out.write(encoded(pointer))
        os.replace(temp, ACTIVE)
    return pointer


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--approved-release", required=True)
    p.add_argument("--expected-certificate", required=True)
    p.add_argument("--approval-reference", required=True)
    p.add_argument(
        "--profile", choices=[p.name for p in CANDIDATES], default=PROFILE.name
    )
    a = p.parse_args()
    print(
        json.dumps(
            select(
                a.approved_release,
                a.expected_certificate,
                a.approval_reference,
                next(p for p in CANDIDATES if p.name == a.profile),
            )
        )
    )
