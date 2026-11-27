"""Bounded public play-by-play targets and strictly lagged pregame fixture states."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from stage1c.contracts import assert_development, team
from weekly_learning.store import ROOT, encoded, sha

PROTOCOL = ROOT / "script_adjustment/protocol.json"
COLUMNS = [
    "game_id",
    "play_id",
    "season",
    "week",
    "season_type",
    "posteam",
    "defteam",
    "play_type",
    "pass_attempt",
    "rush_attempt",
    "sack",
    "qb_scramble",
    "qb_kneel",
    "two_point_attempt",
    "score_differential",
    "game_seconds_remaining",
    "qtr",
]
ACTIONS = ["attempt", "designed_carry", "scramble", "kneel", "other"]
BASE = [
    "plays",
    "attempts",
    "carries",
    "margin",
    "points_for",
    "points_against",
    "pass_rate",
    "scramble_rate",
    "leading_share",
    "tied_share",
    "trailing_share",
    "pace",
    "allowed_plays",
    "allowed_attempts",
    "allowed_carries",
]


def sealed_filters():
    return [
        [("season", "<", 2026), ("season_type", "==", "REG")],
        [("season", "==", 2026), ("week", "<", 11), ("season_type", "==", "REG")],
    ]


def operational_scope(d, admission):
    from weekly_learning.admission import validate_receipt
    from weekly_learning.engine import POLICY

    receipt = validate_receipt(ROOT, admission, json.loads(POLICY.read_text()))
    protected = d[d.season.eq(2026) & d.week.ge(11)]
    if (
        d.season.gt(2026).any()
        or (d.season.eq(2026) & d.week.gt(receipt["through_week"])).any()
        or not set(protected.game_id)
        <= {g["game_id"] for g in receipt["allowed_games"]}
    ):
        raise ValueError("Operational script input exceeds admitted final games")
    return receipt


def aggregate(d, admission=None):
    if admission is None:
        assert_development(d)
    else:
        operational_scope(d, admission)
    if d.duplicated(["game_id", "play_id"]).any():
        raise ValueError("Duplicate play identity")
    d = d[
        d.play_type.isin(["pass", "run", "qb_kneel", "qb_spike"])
        & d.two_point_attempt.ne(1)
        & d.posteam.notna()
        & d.defteam.notna()
    ].copy()
    if d.score_differential.isna().any() or d.game_seconds_remaining.isna().any():
        raise ValueError("Missing pre-play clock/score target")
    d["cell"] = np.select(
        [d.game_seconds_remaining.gt(2700), d.game_seconds_remaining.gt(900)],
        [0, 1],
        default=2,
    ) * 5 + np.select(
        [
            d.score_differential.lt(-7),
            d.score_differential.lt(0),
            d.score_differential.eq(0),
            d.score_differential.le(7),
        ],
        [0, 1, 2, 3],
        default=4,
    )
    d["action"] = np.select(
        [
            d.qb_kneel.eq(1),
            d.qb_scramble.eq(1),
            d.pass_attempt.eq(1) & d.sack.ne(1),
            d.rush_attempt.eq(1),
        ],
        ["kneel", "scramble", "attempt", "designed_carry"],
        default="other",
    )
    d["team"] = d.posteam.map(team)
    return (
        d.groupby(
            ["game_id", "team", "season", "week", "cell", "action"], as_index=False
        )
        .size()
        .rename(columns={"size": "n"})
    )


def collect(output, cache=Path("/tmp/nfl-script-adjustment-pbp")):
    output, cache = Path(output), Path(cache)
    if output.exists():
        m = json.loads((output / "manifest.json").read_text())
        if any(sha(output / n) != h for n, h in m["files"].items()):
            raise ValueError("Input pack changed")
        return output
    cache.mkdir(parents=True, exist_ok=True)
    records = []
    frames = []
    for year in range(2019, 2027):
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.parquet"
        path = (
            Path("/tmp/sunday-research/pbp2026.parquet")
            if year == 2026
            else cache / f"{year}.parquet"
        )
        if not path.exists():
            if year == 2026:
                raise ValueError("Use existing pre-seal cached2026 PBP only")
            with requests.get(url, stream=True, timeout=(5, 60)) as r:
                r.raise_for_status()
                size = 0
                with path.open("xb") as f:
                    for block in r.iter_content(1024 * 1024):
                        size += len(block)
                        if size > 64 * 1024 * 1024:
                            raise ValueError("PBP source exceeds64MiB; no retry")
                        f.write(block)
        frame = pd.read_parquet(path, columns=COLUMNS, filters=sealed_filters())
        frames.append(aggregate(frame))
        records.append(
            {
                "url": url,
                "sha256": sha(path),
                "bytes": path.stat().st_size,
                "retrieved_at": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat(),
                "publication_history_verified": False,
                "materialisation": "REG season<2026 or2026week<11; selected columns before outcomes",
            }
        )
        print("PBP", year, len(frame), flush=True)
    cells = pd.concat(frames, ignore_index=True)
    old = ROOT / "research_inputs/stage1c/public-20261113-v3/team_games.parquet"
    games = pd.read_parquet(
        old,
        filters=[[("season", "<", 2026)], [("season", "==", 2026), ("week", "<", 11)]],
    )
    assert_development(games)
    games["team"] = games.team.map(team)
    games["opponent"] = games.opponent.map(team)
    output.mkdir(parents=True)
    cells.to_parquet(output / "cells.parquet", index=False)
    games.to_parquet(output / "games.parquet", index=False)
    m = {
        "schema": 1,
        "protocol_sha256": sha(PROTOCOL),
        "sources": records,
        "team_source": {"path": str(old.relative_to(ROOT)), "sha256": sha(old)},
        "evidence_tier": "retrospective_not_publication_verified",
        "attribution": "nflverse/nflfastR public play-by-play; no sportsbook or paid inputs",
        "final_period_sealed": True,
        "files": {n: sha(output / n) for n in ["cells.parquet", "games.parquet"]},
    }
    (output / "manifest.json").write_text(encoded(m))
    return output


def team_panel(games, cells, fixtures=None, as_of=None, admission=None):
    """Historical targets never enter the same game's feature vector."""
    p = json.loads(PROTOCOL.read_text())
    games = games.copy()
    if admission is None:
        assert_development(games)
    else:
        operational_scope(games, admission)
    totals = cells.pivot_table(
        index=["game_id", "team"],
        columns="action",
        values="n",
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=ACTIONS, fill_value=0)
    totals["plays"] = totals[ACTIONS].sum(axis=1)
    totals["attempts"] = totals.attempt
    totals["carries"] = totals[["designed_carry", "scramble", "kneel"]].sum(axis=1)
    selected = ["plays", "attempts", "carries", "scramble"]
    games = games.drop(columns=["plays"], errors="ignore").merge(
        totals[selected], on=["game_id", "team"], how="left", validate="one_to_one"
    )
    # Older warmup has no state targets, but genuine known team totals/margins.
    games["plays"] = games.plays.fillna(games.dropbacks + games.rushes)
    games["attempts"] = games.attempts.fillna(games.dropbacks)
    games["carries"] = games.carries.fillna(games.rushes)
    games["pass_rate"] = games.attempts / games.plays
    games["scramble_rate"] = games.scramble / games.plays
    state_counts = (
        cells.groupby(["game_id", "team", "cell"])
        .n.sum()
        .unstack(fill_value=0)
        .reindex(columns=range(15), fill_value=0)
    )
    for label, indices in [
        ("leading", [3, 4, 8, 9, 13, 14]),
        ("tied", [2, 7, 12]),
        ("trailing", [0, 1, 5, 6, 10, 11]),
    ]:
        value = (state_counts[indices].sum(axis=1) / state_counts.sum(axis=1)).rename(
            label + "_share"
        )
        games = games.merge(
            value, on=["game_id", "team"], how="left", validate="one_to_one"
        )
    games["pace"] = games.pace_sum / games.pace_n.replace(0, np.nan)
    counterpart = games[["game_id", "team", "plays", "attempts", "carries"]].rename(
        columns={
            "team": "opponent",
            "plays": "allowed_plays",
            "attempts": "allowed_attempts",
            "carries": "allowed_carries",
        }
    )
    games = games.merge(counterpart, on=["game_id", "opponent"], validate="one_to_one")
    games["available_at"] = pd.concat(
        [
            pd.to_datetime(games.completed_at, utc=True),
            pd.to_datetime(games.kickoff_at, utc=True)
            + pd.Timedelta(hours=p["historical_availability_lag_hours"]),
        ],
        axis=1,
    ).max(axis=1)
    if admission is not None and "observed_available_at" in games:
        observed = pd.to_datetime(games.observed_available_at, utc=True)
        protected = games.season.eq(2026) & games.week.ge(11)
        if observed[protected].isna().any():
            raise ValueError("Missing operational PBP retrieval evidence")
        games.loc[protected, "available_at"] = pd.concat(
            [pd.to_datetime(games.completed_at, utc=True), observed], axis=1
        ).max(axis=1)[protected]
    requests_frame = games[
        ["game_id", "team", "opponent", "season", "week", "kickoff_at", "is_home"]
    ].copy()
    if fixtures is not None:
        requests_frame = pd.concat(
            [requests_frame, fixtures[requests_frame.columns]], ignore_index=True
        ).drop_duplicates(["game_id", "team"])
    histories = {}
    league = []
    updates = list(games.sort_values("available_at").to_dict("records"))
    i = 0
    rows = []
    for g in requests_frame.sort_values(["kickoff_at", "team"]).to_dict("records"):
        decision = pd.Timestamp(g["kickoff_at"]) - pd.Timedelta(minutes=60)
        if as_of is not None:
            decision = min(decision, pd.Timestamp(as_of))
        while i < len(updates) and pd.Timestamp(updates[i]["available_at"]) < decision:
            u = updates[i]
            histories.setdefault(u["team"], []).append(u)
            league.append(u)
            i += 1
        out = {
            **g,
            "prediction_at": decision,
            "history_available_at": max(
                [
                    pd.Timestamp(x["available_at"])
                    for t in [g["team"], g["opponent"]]
                    for x in histories.get(t, [])[-8:]
                ],
                default=pd.NaT,
            ),
        }
        for side, t in [("own", g["team"]), ("opp", g["opponent"])]:
            h = histories.get(t, [])[-8:]
            for col in BASE:
                population = pd.Series(
                    [x.get(col, np.nan) for x in league[-512:]], dtype=float
                ).dropna()
                fallback = float(population.mean()) if len(population) else np.nan
                observed = pd.Series(
                    [x.get(col, np.nan) for x in h], dtype=float
                ).dropna()
                out[f"{side}_{col}"] = (
                    float(observed.sum()) + p["team_shrink_games"] * fallback
                ) / (len(observed) + p["team_shrink_games"])
            out[f"{side}_n"] = len(h)
        rows.append(out)
    frame = pd.DataFrame(rows)
    frame = frame.merge(
        games[
            [
                "game_id",
                "team",
                "available_at",
                "margin",
                "plays",
                "attempts",
                "carries",
                "points_for",
                "points_against",
            ]
        ],
        on=["game_id", "team"],
        how="left",
        validate="one_to_one",
    )
    counts = (
        cells.groupby(["game_id", "team", "cell"])
        .n.sum()
        .unstack(fill_value=0)
        .reindex(columns=range(15), fill_value=0)
    )
    counts.columns = [f"cell_{j}" for j in counts.columns]
    frame = frame.merge(
        counts, on=["game_id", "team"], how="left", validate="one_to_one"
    )
    return frame


def player_source():
    from release_utils import resolve_release

    data, _ = resolve_release(ROOT)
    path = data / "player_features.parquet"
    return path, pd.read_parquet(
        path,
        filters=[[("season", "<", 2026)], [("season", "==", 2026), ("week", "<", 11)]],
    )
