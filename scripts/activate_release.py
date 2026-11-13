"""Validate a future approved selection. Default is dry-run; never pushes or deploys."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_release import validate_bundle
from release_utils import checked_path, select_release, rollback_release

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("candidate", nargs="?")
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--expected-current", required=True)
    p.add_argument(
        "--write-pointer",
        action="store_true",
        help="Only after explicit release approval; writes a local reviewable file",
    )
    args = p.parse_args()
    if args.rollback:
        if not args.write_pointer:
            raise SystemExit(
                "Rollback requires explicit --write-pointer after approval"
            )
        print(rollback_release(ROOT, args.expected_current))
        raise SystemExit(0)
    if not args.candidate:
        raise SystemExit("A candidate path is required")
    path = checked_path(ROOT, args.candidate)
    from release_utils import read_json

    manifest = read_json(path / "manifest.json")
    if datetime.now(timezone.utc) >= datetime.fromisoformat(
        manifest["activate_before"]
    ):
        raise SystemExit("Candidate deadline has passed; regenerate before activation")
    pointer = ROOT / "active_release.json"
    actual = read_json(pointer)["release_id"] if pointer.exists() else "legacy"
    if actual != args.expected_current:
        raise SystemExit("Current selection changed; review the expected release ID")
    validate_bundle(path, app_smoke=True)
    if args.write_pointer:
        print(select_release(ROOT, args.candidate, args.expected_current))
        print("Local pointer written. No commit, push, merge or deployment performed.")
    else:
        print("DRY RUN passed. No selection file changed.")
