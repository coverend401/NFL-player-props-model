"""Reconcile an already-admitted cycle against private frozen selections; no data fetch."""

import argparse
import json
import os

from .settlement import reconcile_cycle
from .store import GitHubJournal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle")
    parser.add_argument("--latest", action="store_true")
    args = parser.parse_args()
    cycle = args.cycle
    if args.latest:
        from weekly_learning.store import ROOT

        paths = sorted(
            (ROOT / "weekly_learning_state/cycles").glob("*/report.json"), reverse=True
        )
        paths = [
            p
            for p in paths
            if json.loads(p.read_text()).get("mode") == "operational"
            and json.loads(p.read_text()).get("admission_sha256")
        ]
        if not paths:
            print(json.dumps({"status": "waiting_for_admitted_results"}))
            return
        cycle = max(
            paths, key=lambda p: json.loads(p.read_text())["completed_at"]
        ).parent
    if not cycle:
        raise ValueError("Provide --cycle or --latest")
    from pathlib import Path

    metadata = json.loads((Path(cycle) / "report.json").read_text())
    game = next(iter(metadata["capture"]["game_kickoffs"]))
    season, week = map(int, game.split("_")[:2])
    journal = GitHubJournal(
        os.environ.get("NFL_SELECTION_GITHUB_REPOSITORY"),
        os.environ.get("NFL_SELECTION_GITHUB_TOKEN"),
        week=f"{season}-{week:02d}",
    )
    report = reconcile_cycle(journal, cycle)
    # Actions runs in the public model repository: private performance stays private.
    print(
        json.dumps(
            {
                "status": report["status"],
                "private_report_written": report["status"] == "reconciled",
            }
        )
    )


if __name__ == "__main__":
    main()
