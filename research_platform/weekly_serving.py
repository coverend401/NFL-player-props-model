"""Separate admission for a frozen weekly inference release under Cloud's exact lock."""

from datetime import UTC, datetime

from release_utils import read_json, sha256
from weekly_learning.store import ROOT

from .cloud_runtime import pins, runtime

RELEASE = ROOT / "research_inference_releases/weekly-week12-schemafix-20261124"
PROFILE = ROOT / "research_runtime_profiles/week12-certifi-20261120-v1"
ACTIVE = ROOT / "research_weekly_serving_active.json"
OPERATIONAL = ROOT / "weekly_learning_state/selected_research.json"
REMAINING_RELEASE = (
    ROOT / "research_inference_releases/weekly-week12-remaining-20261127"
)
REMAINING_PROFILE = (
    ROOT / "research_runtime_profiles/week12-remaining-certifi-20261120-v1"
)
CANDIDATES = {REMAINING_PROFILE: REMAINING_RELEASE, PROFILE: RELEASE}


def inputs(profile=PROFILE, directory=RELEASE):
    files = [
        "research_platform/weekly_serving.py",
        "research_platform/weekly_frame.py",
        "research_platform/weekly_ui.py",
        "research_platform/cloud_weekly_contract.py",
        "scripts/generate_weekly_serving.py",
        "scripts/certify_weekly_serving.py",
        "scripts/select_weekly_serving.py",
        "research_platform/cloud_runtime.py",
        "research_platform/cloud_dashboard.py",
        "research_access.py",
        "weekly_learning_state/readiness/week12-independent-fixtures-20261124/fixture_verification.json",
        "weekly_learning_state/readiness/week12-independent-fixtures-20261124/manifest.json",
        "season_intelligence/data.py",
        "season_intelligence/models.py",
        "season_intelligence/probability.py",
        "research_platform/enhanced_engine.py",
        "research_platform/enhanced_ui.py",
        "research_inputs/script_adjustment/pbp-20261121-v2/games.parquet",
        "docs/season-intelligence-probability-uncertainty.csv",
        "research_runtime_profiles/week11-certifi-20261120-v1/requirements.lock",
    ]
    if (profile / "authority.json").exists():
        files += [
            str((profile / p).relative_to(ROOT))
            for p in ["authority.json", "fixture_verification.json"]
        ]
        files += ["weekly_learning/authority.py", "weekly_learning/publication.py"]
    files.extend(
        str((profile / p).relative_to(ROOT))
        for p in ["selection_build.json", "baseline.json"]
    )
    files += [
        str(p.relative_to(ROOT)) for p in (ROOT / "selection_learning").glob("*.py")
    ]
    for folder in [
        directory,
        ROOT / "experiments/season_intelligence/sunday-20261121-v1",
        ROOT / "research_selection_releases/enhanced-sunday-20261121-v1",
    ]:
        manifest = read_json(folder / "manifest.json")
        files.append(str((folder / "manifest.json").relative_to(ROOT)))
        files += [str((folder / name).relative_to(ROOT)) for name in manifest["files"]]
    return {name: sha256(ROOT / name) for name in sorted(set(files))}


def validate(directory=RELEASE, *, replay=False):
    from scripts.generate_weekly_serving import generated

    if (ROOT / "research_platform/cloud_weekly_contract.py").read_text() != generated():
        raise ValueError("Derived weekly validator changed beyond runtime substitution")
    runtime()  # Checks every package and Python 3.14, with only the declared certifi substitution.
    from .cloud_weekly_contract import validate_operational

    return validate_operational(directory, ROOT, replay=replay)


def admit(profile=PROFILE, directory=RELEASE):
    runtime()
    certificate = read_json(profile / "certificate.json")
    baseline = read_json(profile / "baseline.json")
    if (
        certificate["schema"] != 1
        or certificate["status"] != "passed"
        or certificate["release_id"]
        != read_json(directory / "manifest.json")["release_id"]
        or certificate["manifest_sha256"] != sha256(directory / "manifest.json")
        or certificate["files"] != inputs(profile, directory)
        or certificate["checks"] != baseline["checks"]
        or baseline["runtime"]["packages"]
        != pins(ROOT / "requirements-production.lock")
        or certificate["runtime"]["packages"] != runtime()["packages"]
    ):
        raise ValueError("Weekly serving certificate/provenance mismatch")
    proof = (
        read_json(profile / "fixture_verification.json")
        if (profile / "fixture_verification.json").exists()
        else read_json(
            ROOT
            / "weekly_learning_state/readiness/week12-independent-fixtures-20261124/fixture_verification.json"
        )
    )
    from weekly_learning.admission import utc

    expected = read_json(directory / "manifest.json")["game_kickoffs"]
    observed = {r["game_id"]: r["kickoff_at"] for r in proof["fixtures_verified"]}
    if (
        proof["status"] != "PASS"
        or set(expected)
        != {
            g
            for g, t in observed.items()
            if utc(t)
            > utc(read_json(directory / "manifest.json")["prediction_at"])
            + __import__("pandas").Timedelta(minutes=60)
        }
        or any(utc(t) != utc(observed[g]) for g, t in expected.items())
    ):
        raise ValueError("Independent fixture timing verification mismatch")
    build = read_json(profile / "selection_build.json")
    if (
        build["parent_manifest_sha256"] != sha256(directory / "manifest.json")
        or build["models_fitted"] is not False
        or not utc(baseline["validated_at"])
        <= utc(certificate["validated_at"])
        <= utc(datetime.now(UTC))
        or not utc(build["built_at"]) <= utc(baseline["validated_at"])
        or baseline["runtime"]["python_minor"] != "3.14"
        or certificate["runtime"]["python_minor"] != "3.14"
    ):
        raise ValueError("Serving timestamp/runtime provenance mismatch")
    checks = validate(directory)
    recorded = certificate["checks"]["inference"]
    if not recorded.get("exact_replay") or {
        k: v for k, v in checks.items() if k != "exact_replay"
    } != {k: v for k, v in recorded.items() if k != "exact_replay"}:
        raise ValueError("Weekly serving population/replay proof mismatch")
    from .weekly_frame import build

    frame, fixtures = build(directory, profile)
    if signature(frame) != certificate["checks"]["frame_signature"]:
        raise ValueError("Weekly selection-frame replay mismatch")
    release = read_json(directory / "manifest.json")
    return (
        frame,
        fixtures,
        {
            **release,
            "serving_runtime_profile": profile.name,
            "selection_manifest_path": str(
                (directory / "manifest.json").relative_to(ROOT)
            ),
        },
    )


def signature(frame):
    import hashlib

    return hashlib.sha256(
        frame.to_json(orient="records", double_precision=15).encode()
    ).hexdigest()


def selected():
    if not ACTIVE.exists():
        return None
    pointer = read_json(ACTIVE)
    matches = [
        (p, d)
        for p, d in CANDIDATES.items()
        if str(p.relative_to(ROOT)) == pointer.get("profile")
    ]
    if not matches:
        catalog = read_json(ROOT / "weekly_learning_state/serving_catalog.json")
        entry = catalog["releases"].get(pointer.get("profile"))
        if entry is None or catalog["schema"] != 1:
            raise ValueError("Unknown weekly serving profile")
        from weekly_learning.authority import paths

        profile, directory = paths(ROOT / entry["profile"], ROOT / entry["path"])
        if entry["certificate_sha256"] != pointer["certificate_sha256"] or entry[
            "authority_sha256"
        ] != sha256(profile / "authority.json"):
            raise ValueError("Routine publication catalogue changed")
        matches = [(profile, directory)]
    if len(matches) != 1:
        raise ValueError("Unknown weekly serving profile")
    profile, directory = matches[0]
    if pointer != {
        "release_id": read_json(directory / "manifest.json")["release_id"],
        "profile": str(profile.relative_to(ROOT)),
        "certificate_sha256": sha256(profile / "certificate.json"),
    }:
        raise ValueError("Weekly serving selection pointer mismatch")
    operational = read_json(OPERATIONAL)
    if (
        operational["release_id"] != pointer["release_id"]
        or operational["path"] != str(directory.relative_to(ROOT))
        or operational["manifest_sha256"] != sha256(directory / "manifest.json")
        or operational["checks"]
        != read_json(profile / "certificate.json")["checks"]["inference"]
    ):
        raise ValueError("Operational and serving selections are inconsistent")
    return admit(profile, directory)
