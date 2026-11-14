"""Load immutable inputs and construct controlled legacy/reconciled fixture states."""

import json
from pathlib import Path
import pandas as pd
from stage1b.artifacts import digest
from stage1b.data import read_development_snapshot, prepare_panel, STATS
from stage1c.artifacts import validate as validate_c0
from stage1b1.artifacts import validate as validate_b1
from stage1c.context import states, FAMILIES, OPPORTUNITY, EFFICIENCY, SCHEDULE

CONTEXTS = {
    **FAMILIES,
    "c1_only": list(dict.fromkeys(OPPORTUNITY + EFFICIENCY + SCHEDULE)),
}
ROOT = Path(__file__).resolve().parents[1]


def load(root=ROOT):
    root = Path(root).resolve()
    p = json.loads((root / "stage1c1/protocol.json").read_text())
    b1 = root / "experiments/stage1b1/improvements-20261113-v1"
    bm = validate_b1(b1, root)
    c0 = root / "experiments/stage1c/c0-c2-20261113-v1"
    validate_c0(c0, root)
    old = root / "research_inputs/stage1c/public-20261113-v3"
    recovered = root / p["input_bundle"]
    im = json.loads((recovered / "manifest.json").read_text())
    if (
        im["source_player_sha256"] != bm["input_sha256"]
        or digest(old / "manifest.json") != im["legacy_input_manifest_sha256"]
        or not im["final_period_sealed"]
    ):
        raise ValueError("Reconciliation provenance mismatch")
    if im["evidence_tier"] != "retrospective_reconciled_not_publication_verified":
        raise ValueError("Unsupported evidence claim")
    required = {
        "position_totals.parquet",
        "player_reconciliation.parquet",
        "team_reconciliation.parquet",
        "unresolved_events.parquet",
    }
    if set(im["files"]) != required:
        raise ValueError("Incomplete reconciliation manifest")
    for name, h in im["files"].items():
        if digest(recovered / name) != h:
            raise ValueError("Reconciliation payload changed")
    games = pd.read_parquet(old / "team_games.parquet")
    legacy = pd.read_parquet(old / "position_totals.parquet")
    rates = pd.read_parquet(recovered / "position_totals.parquet")
    contexts = {
        "legacy": states(games, legacy, p["context_lag_hours"]),
        "reconciled": states(games, rates, p["context_lag_hours"]),
    }
    cols = (
        [
            "player_id",
            "player_display_name",
            "position",
            "team",
            "season",
            "week",
            "game_id",
            "kickoff_at",
            "completed_at",
            "offense_pct",
            "stats_observed",
        ]
        + STATS
        + ["team_total_attempts", "team_total_carries", "team_total_targets"]
    )
    source = read_development_snapshot(root / bm["input_path"], p)[cols].copy()
    panel = prepare_panel(source, p)
    return p, b1, c0, recovered, games, rates, contexts, source, panel
