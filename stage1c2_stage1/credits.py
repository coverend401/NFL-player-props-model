"""Narrow, evidence-bound additions to a new research ledger, never old labels."""

import json
from pathlib import Path
import pandas as pd
from stage1c1.reconcile import event_credits
from stage1c.contracts import assert_development, team

DECISIONS = Path(__file__).with_name("decisions.json")


def repair(pbp, source, decisions=None):
    assert_development(pbp)
    spec = decisions or json.loads(DECISIONS.read_text())
    d = pbp.copy()
    records = []
    identity = source.copy()
    identity["team"] = identity.team.map(team)
    ids = identity.set_index(["game_id", "team", "player_id"])

    def reviewed(patch):
        match = d[d.game_id.eq(patch["game_id"]) & d.play_id.eq(patch["play_id"])]
        if len(match) != 1:
            raise ValueError("Reviewed play absent or duplicated")
        r = match.iloc[0]
        if (
            r.play_deleted == 1
            or r.two_point_attempt == 1
            or team(r.posteam) != patch["team"]
        ):
            raise ValueError("Reviewed play is deleted, two-point or wrong team")
        if any(fragment not in r.desc for fragment in patch["fragments"]):
            raise ValueError("Source description changed")
        key = (patch["game_id"], patch["team"], patch["actor"])
        if key not in ids.index or ids.index.duplicated().any():
            raise ValueError("Reviewed historical player identity is not unique")
        records.append(
            dict(
                game_id=patch["game_id"],
                team=patch["team"],
                play_id=patch["play_id"],
                player_id=patch["actor"],
                player_name=ids.loc[key, "player_display_name"],
                description=r.desc,
                evidence_tier="unambiguous_description_plus_frozen_box_internal_not_independent",
                publication_verified=False,
            )
        )
        return r

    for p in spec["event_inclusions"]:
        r = reviewed(p)
        actor = "rusher_player_id" if p["type"] == "run" else "passer_player_id"
        opportunity = "rush_attempt" if p["type"] == "run" else "pass_attempt"
        if (
            r.play_type != "no_play"
            or r[actor] != p["actor"]
            or r[opportunity] != 1
            or r.sack == 1
        ):
            raise ValueError("Reviewed event flags/actor changed")
        if p["type"] == "run" and r.rushing_yards != p["yards"]:
            raise ValueError("Reviewed rushing credit changed")
        if p["type"] == "pass" and not (
            r.incomplete_pass == 1 and r.complete_pass == 0
        ):
            raise ValueError("Reviewed incompletion changed")
        d.loc[r.name, "play_type"] = p["type"]
    credits = event_credits(d)
    additions = []
    for p in spec["missing_lateral_credits"]:
        r = reviewed(p)
        if (
            r.play_type == "no_play"
            or r.complete_pass != 1
            or sum(p["segments"]) != p["value"]
        ):
            raise ValueError("Invalid lateral evidence")
        if r.lateral_receiver_player_id == p["actor"]:
            raise ValueError(
                "Do not duplicate an already structured final-lateral credit"
            )
        additions.append(
            dict(
                game_id=p["game_id"],
                team=p["team"],
                play_id=p["play_id"],
                player_id=p["actor"],
                stat="receiving_yards",
                value=float(p["value"]),
                actor_missing=False,
                credit_missing=False,
            )
        )
    if additions:
        credits = pd.concat([credits, pd.DataFrame(additions)], ignore_index=True)
    return credits, pd.DataFrame(records)
