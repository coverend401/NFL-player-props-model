"""Research registry promotion only after statistical and existing release gates."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research_platform.inference_release import validate_inference
from stage1b.data import MARKETS

from .store import ROOT, encoded, sha


def promote(store, candidate, release_path, current_models, policy):
    """Caller holds Store.transaction. Never writes app pointers or production."""
    if not candidate.get("accepted") or not candidate.get("statistical_gate"):
        raise ValueError("Challenger did not pass statistical gates")
    h = candidate.get("holdout", {})
    registry = store.root / "holdouts" / (h.get("block", "") + ".json")
    if not registry.is_file():
        raise ValueError("No prospectively registered holdout")
    registered = json.loads(registry.read_text())
    if (
        not registered.get("fresh")
        or registered.get("replay_only")
        or h.get("replay_only")
    ):
        raise ValueError("Consumed or non-fresh holdout cannot support promotion")
    if registered.get("protocol_sha256") != candidate.get("plan_sha256"):
        raise ValueError("Candidate differs from preregistration")
    if not registered.get("registered_at") or pd.Timestamp(
        registered["registered_at"]
    ) >= pd.Timestamp(candidate["first_holdout_kickoff"]) - pd.Timedelta(minutes=60):
        raise ValueError("Candidate not registered before holdout")
    if candidate.get("baseline_models") != current_models:
        raise ValueError("Evaluation baseline is not the current champion")
    if registered.get("baseline_models") != current_models or registered.get(
        "challenger_models"
    ) != candidate.get("challenger_models"):
        raise ValueError("Evaluation models differ from frozen holdout registration")
    if {r["market"] for r in candidate["markets"]} != set(MARKETS):
        raise ValueError("Promotion requires all nine market evaluations")
    for row in candidate["markets"]:
        if (
            row["weeks"] < policy["minimum_holdout_weeks"]
            or row["baseline"]["n"] < policy["minimum_market_rows"]
            or row["relative_mae_gain"] < -policy["maximum_market_mae_regression"]
        ):
            raise ValueError("Sample-size or all-market regression gate failed")
        if (
            row["probability_scores"]["candidate"]["brier"]
            > row["probability_scores"]["baseline"]["brier"]
            or row["probability_scores"]["candidate"]["log_loss"]
            > row["probability_scores"]["baseline"]["log_loss"]
        ):
            raise ValueError("Probability scores regressed")
    primary = next(r for r in candidate["markets"] if r["market"] == "passing_yards")
    if (
        not primary["holm_rejects_no_improvement"]
        or primary["relative_mae_gain"] < policy["minimum_mae_gain"]
    ):
        raise ValueError("Primary-market paired improvement gate failed")
    consumed = store.root / "holdouts" / (h["block"] + ".promoted.json")
    if consumed.exists():
        raise ValueError("Holdout already used for promotion")
    path = Path(release_path).resolve()
    path.relative_to(ROOT / "research_inference_releases")
    checks = validate_inference(path, ROOT, replay=True)
    manifest = json.loads((path / "manifest.json").read_text())
    if candidate.get("challenger_models") != manifest["models"]:
        raise ValueError("Certified challenger differs from evaluated models")
    if candidate.get("candidate_release_sha256") != sha(path / "manifest.json"):
        raise ValueError("Challenger certification identity mismatch")
    record = {
        "promoted_at": datetime.now(UTC).isoformat(),
        "release_id": manifest["release_id"],
        "path": str(path.relative_to(ROOT)),
        "models": manifest["models"],
        "rollback_models": current_models,
        "checks": checks,
        "plan_sha256": candidate["plan_sha256"],
        "holdout": h,
    }
    with consumed.open("x") as f:
        f.write(
            encoded(
                {
                    "candidate_release_sha256": sha(path / "manifest.json"),
                    "plan_sha256": candidate["plan_sha256"],
                }
            )
        )
    store.publish(
        "champions", manifest["release_id"], documents={"champion.json": record}
    )
    pointer = store.root / "champion.json"
    temp = store.root / ".champion.next.json"
    with temp.open("x") as f:
        f.write(encoded(record))
    os.replace(temp, pointer)
    store.audit(
        "research_champion_promoted",
        {"release_id": record["release_id"], "rollback_models": current_models},
    )
    return record
