"""Two real environments, identical forecasts/pricing; activation is a separate approval."""

import argparse
from datetime import UTC, datetime

from release_utils import read_json, runtime_versions, sha256
from research_platform.enhanced_engine import price, select
from research_platform.weekly_frame import build
from research_platform.weekly_serving import (
    CANDIDATES,
    PROFILE,
    RELEASE,
    inputs,
    signature,
)
from weekly_learning.store import encoded


def checks(cloud, directory=RELEASE, profile=PROFILE):
    if cloud:
        from research_platform.weekly_serving import validate

        inference = validate(directory, replay=True)
    else:
        from weekly_learning.contract import validate_operational

        inference = validate_operational(directory, directory.parents[1], replay=True)
    frame, fixtures = build(directory, profile)
    samples = []
    for market, g in frame.groupby("market", sort=True):
        row = g.iloc[0].to_dict()
        line = max(0.5, int(row["enhanced_projection"]) + 0.5)
        samples.append(
            {
                "market": market,
                "line_type": "synthetic certification query, not bookmaker quote",
                "line": line,
                "pricing": price(row, line),
            }
        )
    top, two = select(frame)
    return {
        "inference": inference,
        "frame_signature": signature(frame),
        "selection_rows": len(frame),
        "complete_fixtures": int(frame.game_id.nunique()),
        "roof_only_fixtures": sorted(set(fixtures.game_id) - set(frame.game_id)),
        "forecast_only_top": top[["game_id", "player_id", "market"]].to_dict("records"),
        "forecast_only_two": two[["game_id", "player_id", "market"]].to_dict("records"),
        "pricing_checks": samples,
    }


def run(baseline=False, verify=False, profile=PROFILE, directory=None):
    if directory is None:
        directory = CANDIDATES[profile]
    elif profile not in CANDIDATES:
        from weekly_learning.authority import paths

        profile, directory = paths(profile, directory)
        import shutil

        from weekly_learning.authority import PATH

        if not (profile / "authority.json").exists():
            profile.mkdir(exist_ok=True)
            shutil.copyfile(PATH, profile / "authority.json")
    profile.mkdir(exist_ok=True)
    if baseline:
        plan = profile / "selection_build.json"
        if not plan.exists():
            if verify:
                raise ValueError("Missing selection build provenance")
            plan.write_text(
                encoded(
                    {
                        "built_at": datetime.now(UTC).isoformat(),
                        "parent_manifest_sha256": sha256(directory / "manifest.json"),
                        "models_fitted": False,
                    }
                )
            )
        result = {
            "runtime": runtime_versions(directory.parents[1]),
            "checks": checks(False, directory, profile),
            "validated_at": datetime.now(UTC).isoformat(),
        }
        path = profile / "baseline.json"
        if path.exists():
            old = read_json(path)
            if (
                result["checks"] != old["checks"]
                or result["runtime"]["packages"] != old["runtime"]["packages"]
            ):
                raise ValueError("Original baseline replay changed")
        elif verify:
            raise ValueError("Missing original-runtime validation")
        else:
            path.write_text(encoded(result))
    else:
        from research_platform.cloud_runtime import runtime
        from research_platform.weekly_serving import admit

        actual = runtime()
        current = checks(True, directory, profile)
        old = read_json(profile / "baseline.json")
        if current != old["checks"]:
            raise ValueError("Cross-runtime numerical replay differs")
        if not verify:
            certificate = {
                "schema": 1,
                "status": "passed",
                "release_id": read_json(directory / "manifest.json")["release_id"],
                "manifest_sha256": sha256(directory / "manifest.json"),
                "runtime": actual,
                "checks": current,
                "validated_at": datetime.now(UTC).isoformat(),
                "files": inputs(profile, directory),
            }
            (profile / "certificate.json").write_text(encoded(certificate))
        admit(profile, directory)
    print("Weekly serving validation: PASS; not selected or activated")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument(
        "--profile", choices=[p.name for p in CANDIDATES], default=PROFILE.name
    )
    a = p.parse_args()
    run(a.baseline, a.verify, next(p for p in CANDIDATES if p.name == a.profile))
