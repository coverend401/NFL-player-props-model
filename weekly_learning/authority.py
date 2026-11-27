"""Standing owner authority for data-only refreshes; never authorises a new model."""

import json
from pathlib import Path

from .store import ROOT, sha

PATH = ROOT / "weekly_learning/standing_authority.json"
MODELLING = [
    "research_platform/inference_builder.py",
    "research_platform/inference_release.py",
    "scripts/build_slate.py",
    "scripts/forecast_features.py",
    "scripts/train_all_markets.py",
    "weekly_learning/contract.py",
    "weekly_learning/policy.json",
    "research_platform/weekly_frame.py",
    "selection_learning/engine.py",
    "season_intelligence/models.py",
    "season_intelligence/data.py",
    "season_intelligence/probability.py",
    "research_platform/enhanced_engine.py",
]


def validate(directory=None):
    policy = json.loads(PATH.read_text())
    if policy["status"] != "authorised" or policy["research_only"] is not True:
        raise ValueError("Standing routine publication is not authorised")
    if policy["modelling_code_sha256"] != {n: sha(ROOT / n) for n in MODELLING}:
        raise ValueError("Approved modelling code changed; owner review required")
    if (
        sha(ROOT / policy["research_models"]["path"])
        != policy["research_models"]["sha256"]
    ):
        raise ValueError("Approved research models changed")
    parent = ROOT / policy["model_parent"]["path"]
    if sha(parent / "manifest.json") != policy["model_parent"]["manifest_sha256"]:
        raise ValueError("Approved champion parent changed")
    for market, expected in policy["models"].items():
        if sha(parent / "data" / f"model_{market}.joblib") != expected["sha256"]:
            raise ValueError("Approved champion model changed")
    if directory is not None:
        directory = Path(directory).resolve()
        directory.relative_to(ROOT / "research_inference_releases")
        m = json.loads((directory / "manifest.json").read_text())
        s = m["fixture_slate"]
        if (
            m["model_parent"] != policy["model_parent"]
            or m["models"] != policy["models"]
            or s["season"] != policy["season"]
            or not policy["first_week"] <= s["week"] <= policy["last_week"]
        ):
            raise ValueError("Candidate is outside standing model/season authority")
    return policy


def paths(profile, directory):
    profile, directory = Path(profile).resolve(), Path(directory).resolve()
    profile.relative_to(ROOT / "research_runtime_profiles")
    directory.relative_to(ROOT / "research_inference_releases")
    if profile.name != "routine-" + directory.name:
        raise ValueError("Routine serving profile identity mismatch")
    validate(directory)
    return profile, directory
