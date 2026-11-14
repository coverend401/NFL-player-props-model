"""Reconcile event credits against frozen official totals without changing targets.

A missing box score is never a zero. Zero opportunity can be established only
from a complete, reconciled event ledger plus recorded participation. These
auxiliary diagnostics do not add or alter any scored player outcome.
"""

from pathlib import Path
import argparse, json
import numpy as np
import pandas as pd
from stage1b.artifacts import digest
from stage1b.data import read_development_snapshot
from stage1c.contracts import development_filters, assert_development, team

ROOT = Path(__file__).resolve().parents[1]
STATS = [
    "attempts",
    "completions",
    "passing_yards",
    "carries",
    "rushing_yards",
    "targets",
    "receptions",
    "receiving_yards",
]
CATEGORIES = {
    "pass": ["attempts", "completions", "passing_yards"],
    "rush": ["carries", "rushing_yards"],
    "rec": ["targets", "receptions", "receiving_yards"],
}
COLS = [
    "game_id",
    "play_id",
    "season",
    "week",
    "season_type",
    "posteam",
    "play_type",
    "play_deleted",
    "two_point_attempt",
    "pass_attempt",
    "rush_attempt",
    "sack",
    "complete_pass",
    "incomplete_pass",
    "interception",
    "qb_spike",
    "passer_player_id",
    "rusher_player_id",
    "receiver_player_id",
    "lateral_rusher_player_id",
    "lateral_receiver_player_id",
    "passing_yards",
    "rushing_yards",
    "receiving_yards",
    "lateral_rushing_yards",
    "lateral_receiving_yards",
]


def event_credits(pbp):
    assert_development(pbp)
    if pbp.duplicated(["game_id", "play_id"]).any():
        raise ValueError("Duplicate event identity")
    d = pbp[
        pbp.posteam.notna()
        & pbp.play_type.ne("no_play")
        & pbp.play_deleted.ne(1)
        & pbp.two_point_attempt.ne(1)
    ].copy()
    d["team"] = d.posteam.map(team)
    credits = []

    def add(rows, idcol, stat, value):
        if rows.empty:
            return
        x = (
            rows[["game_id", "play_id", "team", idcol]]
            .rename(columns={idcol: "player_id"})
            .copy()
        )
        x["stat"] = stat
        x["value"] = np.asarray(value) if not np.isscalar(value) else value
        x["actor_missing"] = x.player_id.isna()
        x["credit_missing"] = x.value.isna()
        credits.append(x)

    passes = d[d.pass_attempt.eq(1) & d.sack.ne(1)]
    add(passes, "passer_player_id", "attempts", 1.0)
    add(passes[passes.complete_pass.eq(1)], "passer_player_id", "completions", 1.0)
    py = passes.passing_yards.copy()
    known_incomplete = passes.complete_pass.eq(0) & (
        passes.incomplete_pass.eq(1) | passes.interception.eq(1) | passes.qb_spike.eq(1)
    )
    py = py.mask(py.isna() & known_incomplete, 0.0)
    add(passes, "passer_player_id", "passing_yards", py)
    rush = d[d.rush_attempt.eq(1)]
    add(rush, "rusher_player_id", "carries", 1.0)
    add(rush, "rusher_player_id", "rushing_yards", rush.rushing_yards)
    targets = passes[passes.receiver_player_id.notna()]
    add(targets, "receiver_player_id", "targets", 1.0)
    catches = targets[targets.complete_pass.eq(1)]
    add(catches, "receiver_player_id", "receptions", 1.0)
    add(catches, "receiver_player_id", "receiving_yards", catches.receiving_yards)
    # Laterals receive yards but do not manufacture an extra carry/target/catch.
    for actor, stat, field in [
        ("lateral_rusher_player_id", "rushing_yards", "lateral_rushing_yards"),
        ("lateral_receiver_player_id", "receiving_yards", "lateral_receiving_yards"),
    ]:
        rows = d[d[actor].notna() | d[field].fillna(0).ne(0)]
        add(rows, actor, stat, rows[field])
    return pd.concat(credits, ignore_index=True)


def reconcile(credits, source, legacy, games):
    s = source.copy()
    s["team"] = s.team.map(team)
    if s.duplicated(["game_id", "team", "player_id"]).any():
        raise ValueError("Ambiguous historical player identity")
    ids = s[["game_id", "team", "player_id", "position"]]
    e = credits.merge(
        ids, on=["game_id", "team", "player_id"], how="left", validate="many_to_one"
    )
    e["position_missing"] = e.position.isna()
    e["position_bucket"] = e.position.where(
        e.position.isin(["QB", "RB", "WR", "TE"]), "OTHER"
    )
    valid = e[~e.actor_missing & ~e.credit_missing]
    wide = valid.pivot_table(
        index=["game_id", "team", "player_id"],
        columns="stat",
        values="value",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    for col in STATS:
        if col not in wide:
            wide[col] = 0.0
    player = s[
        ["game_id", "team", "player_id", "position", "offense_pct", "stats_observed"]
        + STATS
    ].merge(
        wide,
        on=["game_id", "team", "player_id"],
        how="outer",
        suffixes=("_official", "_event"),
        validate="one_to_one",
    )
    # Absence of an event is used for reconciliation; it is NOT an observed zero
    # unless that team/category later passes all completeness checks.
    audit = []
    event_groups = dict(tuple(e.groupby(["game_id", "team"], sort=False)))
    player_groups = dict(tuple(player.groupby(["game_id", "team"], sort=False)))
    official = legacy[legacy.kind.eq("pass")].set_index(["game_id", "team"])
    for (game, tm), row in official.iterrows():
        er = event_groups.get((game, tm), e.iloc[:0])
        pr = player_groups.get((game, tm), player.iloc[:0])
        a = {"game_id": game, "team": tm}
        for field in STATS:
            z = er[er.stat.eq(field)]
            total = z.value.sum(min_count=1) if len(z) else 0.0
            expected = row[field]
            obs = (
                pr.stats_observed.fillna(False).astype(bool)
                & pr[field + "_official"].notna()
            )
            delta = pr[field + "_event"].fillna(0) - pr[field + "_official"]
            a[field + "_diff"] = (
                float(total - expected) if pd.notna(expected) else np.nan
            )
            a[field + "_bad_credits"] = int(
                (z.actor_missing | z.credit_missing | z.position_missing).sum()
            )
            a[field + "_player_mismatch"] = int((obs & delta.abs().gt(1e-8)).sum())
            a[field + "_strict"] = bool(
                pd.notna(expected)
                and np.isfinite(total)
                and abs(total - expected) < 1e-8
                and a[field + "_bad_credits"] == 0
                and a[field + "_player_mismatch"] == 0
            )
        for cat, fields in CATEGORIES.items():
            a[cat + "_strict"] = all(a[x + "_strict"] for x in fields)
        audit.append(a)
    audit = pd.DataFrame(audit)
    # A category can be complete even if a different category has a mismatch.
    mapping = {
        "pass": "pass",
        "rush_QB": "rush",
        "rush_RB": "rush",
        "rec_RB": "rec",
        "rec_WR": "rec",
        "rec_TE": "rec",
    }
    expected = games[["game_id", "team"]].merge(
        pd.DataFrame({"kind": list(mapping)}), how="cross"
    )
    recovered = expected.merge(
        legacy, on=["game_id", "team", "kind"], how="left", validate="one_to_one"
    )
    recovered["original_complete"] = recovered.known_complete.fillna(False).astype(bool)
    checks = audit.set_index(["game_id", "team"])
    # Summation from event credits retains zero-yard and negative-yard events.
    totals = (
        e[~e.actor_missing & ~e.credit_missing & ~e.position_missing]
        .groupby(["game_id", "team", "position", "stat"])
        .value.sum()
        .to_dict()
    )
    recovered["recovered_from_events"] = False
    for i, r in recovered.iterrows():
        if r.original_complete or r.kind == "pass":
            continue
        key = (r.game_id, r.team)
        cat = mapping[r.kind]
        if key not in checks.index or not bool(checks.loc[key, cat + "_strict"]):
            continue
        position = r.kind.split("_")[1]
        for stat in CATEGORIES[cat]:
            recovered.loc[i, stat] = totals.get(
                (r.game_id, r.team, position, stat), 0.0
            )
        recovered.loc[i, "known_complete"] = True
        recovered.loc[i, "recovered_from_events"] = True
    recovered["known_complete"] = recovered.known_complete.fillna(False).astype(bool)
    safe = audit[["game_id", "team"] + [field + "_strict" for field in STATS]]
    player = player.merge(
        safe, on=["game_id", "team"], how="left", validate="many_to_one"
    )
    for field in STATS:
        field_ok = player[field + "_strict"].fillna(False)
        player[field + "_event_validated"] = player[field + "_event"].where(field_ok)
        participant = player.offense_pct.gt(0) | player[field + "_event"].fillna(0).ne(
            0
        )
        zero = field_ok & participant & player[field + "_event"].isna()
        player.loc[zero, field + "_event_validated"] = 0.0
    return recovered, audit, player, e


def build(output, cache):
    output = Path(output)
    cache = Path(cache)
    if output.exists():
        raise ValueError("Immutable reconciliation ID already exists")
    baseline = ROOT / "experiments/stage1b1/improvements-20261113-v1"
    bm = json.loads((baseline / "manifest.json").read_text())
    p = json.loads((ROOT / "stage1c/protocol.json").read_text())
    old = ROOT / p["input_bundle"]
    im = json.loads((old / "manifest.json").read_text())
    source = read_development_snapshot(ROOT / bm["input_path"], p)
    legacy = pd.read_parquet(old / "position_totals.parquet")
    games = pd.read_parquet(old / "team_games.parquet")
    allcredits = []
    raw = []
    for season in range(2019, 2027):
        path = cache / f"{season}.parquet"
        expected = next(
            r for r in im["source_records"] if r["url"].endswith(f"_{season}.parquet")
        )
        if not path.exists() or digest(path) != expected["sha256"]:
            raise ValueError(
                "Original PBP cache missing/changed; do not silently refresh sources"
            )
        data = pd.read_parquet(path, columns=COLS, filters=development_filters())
        allcredits.append(event_credits(data))
        raw.append(expected)
        print("CREDITS", season, flush=True)
    credits = pd.concat(allcredits, ignore_index=True)
    rates, audit, players, events = reconcile(credits, source, legacy, games)
    output.mkdir(parents=True)
    rates.to_parquet(output / "position_totals.parquet", index=False)
    audit.to_parquet(output / "team_reconciliation.parquet", index=False)
    players.to_parquet(output / "player_reconciliation.parquet", index=False)
    # Only unmapped/malformed event metadata, not a fabricated player observation.
    events[
        events.actor_missing | events.credit_missing | events.position_missing
    ].to_parquet(output / "unresolved_events.parquet", index=False)
    m = {
        "schema": 1,
        "scope": "opportunity diagnostic inputs, not replacement evaluation outcomes",
        "evidence_tier": "retrospective_reconciled_not_publication_verified",
        "source_player_sha256": bm["input_sha256"],
        "legacy_input_manifest_sha256": digest(old / "manifest.json"),
        "raw_sources": raw,
        "files": {
            n: digest(output / n)
            for n in [
                "position_totals.parquet",
                "team_reconciliation.parquet",
                "player_reconciliation.parquet",
                "unresolved_events.parquet",
            ]
        },
        "final_period_sealed": True,
        "note": "Totals share an upstream PBP source; reconciliation is internal consistency, not independent authenticity.",
    }
    (output / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    print("FROZEN", output, flush=True)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--cache", type=Path, default=Path("/tmp/stage1c-pbp"))
    args = a.parse_args()
    build(args.output, args.cache)
