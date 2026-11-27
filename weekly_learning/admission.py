"""Prospective operational admission, separate from all sealed benchmark readers."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests

from .store import Store, encoded, sha

SCHEMA = "prospective_settlement_v1"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ALIASES = {"WSH": "WAS", "LAR": "LA", "OAK": "LV", "SD": "LAC"}


def utc(value):
    t = pd.Timestamp(value)
    if t.tzinfo is None or pd.isna(t):
        raise ValueError("Explicit UTC-compatible timestamp required")
    return t.tz_convert("UTC")


def time_gate(policy, season, week, *, capture=None, now=None):
    now = utc(now or datetime.now(UTC))
    scope = policy.get("operational_scope", {})
    if (
        not policy.get("operational_settlement_approved")
        or season != scope.get("season")
        or not scope.get("first_week", 99) <= week <= scope.get("last_week", -1)
    ):
        raise ValueError(
            "Operational settlement is not authorised for this season/week"
        )
    floor = utc(scope["not_before"])
    if capture is not None:
        if capture.get("capture_tier") != "genuine_predecision_capture":
            raise ValueError(
                "Settlement requires a genuinely frozen predecision capture"
            )
        latest = max(utc(v) for v in capture["game_kickoffs"].values())
        # Tuesday noon after the original slate; delayed fixtures also require finality.
        day = latest.normalize() + pd.Timedelta(
            days=(1 - latest.weekday()) % 7, hours=12
        )
        floor = max(floor, day, latest + pd.Timedelta(hours=8))
        frozen = utc(capture["frozen_at"])
        if any(
            frozen >= utc(t) - pd.Timedelta(minutes=60)
            for t in capture["game_kickoffs"].values()
        ):
            raise ValueError("Capture was late for at least one fixture")
    if now < floor:
        raise ValueError(
            f"Settlement window closed until {floor.isoformat()}; no results accessed"
        )
    return floor


def capture_check(repo, path, expected_sha=None):
    repo = Path(repo).resolve()
    path = (repo / path).resolve()
    path.relative_to(repo / "weekly_learning_state" / "captures")
    if expected_sha and sha(path / "manifest.json") != expected_sha:
        raise ValueError("Pregame capture manifest changed")
    Store(repo / "weekly_learning_state").validate(path)
    meta = json.loads((path / "capture.json").read_text())
    frame = pd.read_parquet(path / "forecasts.parquet")
    frozen = utc(meta["frozen_at"])
    if (
        meta["capture_tier"] != "genuine_predecision_capture"
        or not pd.to_datetime(frame.prediction_at, utc=True).le(frozen).all()
    ):
        raise ValueError("Invalid pregame capture timing")
    if not all(
        frozen < utc(t) - pd.Timedelta(minutes=60)
        for t in meta["game_kickoffs"].values()
    ):
        raise ValueError("Late pregame capture")
    return meta, frame


def scoreboard_finality(games, *, get=None, now=None):
    """One bounded public request. Retain selected final facts, never odds payloads."""
    supplied_now = now
    now = utc(now or datetime.now(UTC))
    get = get or requests.get
    times = pd.to_datetime(games.kickoff_at, utc=True)
    first = times.min() - pd.Timedelta(days=1)
    last = times.max() + pd.Timedelta(days=1)
    if last - first > pd.Timedelta(days=10):
        raise ValueError("Finality discovery window exceeds bound")
    scope = games.game_id.astype(str).str.extract(
        r"^(?P<season>\d{4})_(?P<week>\d{2})_[A-Z]{2,3}_[A-Z]{2,3}$"
    )
    if scope.isna().any().any() or len(scope.drop_duplicates()) != 1:
        raise ValueError("Finality requires one unambiguous NFL season/week")
    season, week = int(scope.iloc[0].season), int(scope.iloc[0].week)
    if not 1 <= week <= 18:
        raise ValueError("Unsupported regular-season finality week")
    params = {"dates": str(season), "seasontype": 2, "week": week, "limit": 100}
    with get(
        ESPN, params=params, stream=True, timeout=(5, 30), allow_redirects=False
    ) as response:
        if response.status_code != 200:
            raise ValueError(
                f"ESPN finality source unavailable (HTTP {response.status_code}); no retry"
            )
        chunks = []
        size = 0
        for block in response.iter_content(65536):
            size += len(block)
            if size > 4 * 1024 * 1024:
                raise ValueError("Finality response exceeds 4 MiB")
            chunks.append(block)
    import hashlib

    raw = b"".join(chunks)
    body = json.loads(raw)
    if (
        body.get("season", {}).get("year") != season
        or body.get("season", {}).get("type") != 2
        or body.get("week", {}).get("number") != week
    ):
        raise ValueError("ESPN returned a different or unverified season/week")
    events = body.get("events", [])
    if not isinstance(events, list) or len(events) > 100:
        raise ValueError("Unexpected finality envelope")
    matched = []
    for game in games.itertuples():
        matches = []
        for event in events:
            for competition in event.get("competitions", []):
                sides = {
                    c.get("homeAway"): c for c in competition.get("competitors", [])
                }
                if set(sides) != {"home", "away"}:
                    continue
                teams = {
                    s: ALIASES.get(
                        sides[s].get("team", {}).get("abbreviation"),
                        sides[s].get("team", {}).get("abbreviation"),
                    )
                    for s in sides
                }
                if teams != {"home": game.home_team, "away": game.away_team}:
                    continue
                if (
                    abs(
                        (
                            utc(competition.get("date", event.get("date")))
                            - utc(game.kickoff_at)
                        ).total_seconds()
                    )
                    > 300
                ):
                    continue
                status = competition.get("status", event.get("status", {})).get(
                    "type", {}
                )
                if status.get("completed") is not True or status.get("state") != "post":
                    raise ValueError("Fixture not confirmed final by ESPN")
                matches.append(sides)
        if len(matches) != 1:
            raise ValueError(
                f"Missing or ambiguous finality fixture match: {game.game_id}; frozen/source kickoff {utc(game.kickoff_at).isoformat()}"
            )
        matched.append((game, matches[0]))
    verified = [
        {
            "game_id": g.game_id,
            "week": int(g.week),
            "home_team": g.home_team,
            "away_team": g.away_team,
            "kickoff_at": utc(g.kickoff_at).isoformat(),
            "home_score": int(sides["home"]["score"]),
            "away_score": int(sides["away"]["score"]),
            "confirmed_final": True,
        }
        for g, sides in matched
    ]
    return {
        "url": ESPN + "?" + urlencode(params),
        "retrieved_at": utc(
            supplied_now if supplied_now is not None else datetime.now(UTC)
        ).isoformat(),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "games": verified,
    }


def prove_schedule(repo, source, capture_path, policy, *, now=None, get=None):
    repo = Path(repo).resolve()
    source = Path(source)
    meta, _ = capture_check(repo, capture_path)
    week = int(next(iter(meta["game_kickoffs"])).split("_")[1])
    season = int(next(iter(meta["game_kickoffs"])).split("_")[0])
    cutoff = time_gate(policy, season, week, capture=meta, now=now)
    from scripts.forecast_features import schedule_times

    from .sources import verify_snapshot

    records = verify_snapshot(source, max_age_hours=48)
    if utc(records["schedule"]["retrieved_at"]) < cutoff:
        raise ValueError("Schedule predates settlement cutoff")
    columns = [
        "game_id",
        "season",
        "week",
        "home_team",
        "away_team",
        "gameday",
        "gametime",
    ]
    metadata = pd.read_parquet(
        source / "schedule.parquet",
        columns=columns,
        filters=[
            ("season", "==", season),
            ("week", "==", week),
            ("game_type", "==", "REG"),
        ],
    )
    local = pd.to_datetime(
        metadata.gameday.astype(str) + " " + metadata.gametime.astype(str),
        errors="raise",
    )
    metadata["kickoff_at"] = local.dt.tz_localize(
        "America/New_York", ambiguous="raise", nonexistent="raise"
    ).dt.tz_convert("UTC")
    if (
        metadata.empty
        or metadata.game_id.duplicated().any()
        or not set(meta["game_kickoffs"]) <= set(metadata.game_id)
    ):
        raise ValueError("Incomplete captured fixture metadata")
    proof = scoreboard_finality(metadata, get=get, now=now)
    # Only now, after all final statuses passed, read NFL score fields.
    games = schedule_times(
        pd.read_parquet(
            source / "schedule.parquet",
            filters=[
                ("season", "==", season),
                ("week", "==", week),
                ("game_type", "==", "REG"),
            ],
        )
    )
    observed = utc(now or datetime.now(UTC))
    if (
        games.completed_at.isna().any()
        or not pd.to_datetime(games.completed_at, utc=True).lt(observed).all()
    ):
        raise ValueError("NFL completion/availability is not confirmed")
    ends = games.set_index("game_id").completed_at
    for g in proof["games"]:
        g["completed_at"] = utc(ends[g["game_id"]]).isoformat()
    _proof_check(proof, games, cutoff, observed)
    with (source / "finality.json").open("x") as f:
        f.write(encoded(proof))
    return proof


def seal_source_files(source, season, week, now):
    """Persist only admitted outcomes and future fixture/personnel metadata."""
    import pyarrow.parquet as pq

    source = Path(source)
    records = json.loads((source / "sources.json").read_text())
    for name, r in records.items():
        path = source / (name + ".parquet")
        schema = pq.read_schema(path)
        if name == "players":
            continue
        value = (
            str(season)
            if "season" in schema.names and str(schema.field("season").type) == "string"
            else season
        )
        if name == "schedule":
            past = pd.read_parquet(
                path,
                filters=[
                    [("season", "<", season)],
                    [("season", "==", season), ("week", "<=", week)],
                ],
            )
            columns = [
                c
                for c in [
                    "season",
                    "week",
                    "game_type",
                    "game_id",
                    "gameday",
                    "gametime",
                    "home_team",
                    "away_team",
                    "spread_line",
                    "total_line",
                    "roof",
                ]
                if c in schema.names
            ]
            future = pd.read_parquet(
                path,
                columns=columns,
                filters=[("season", "==", season), ("week", ">", week)],
            )
            frame = pd.concat([past, future], ignore_index=True)
        elif name == "depth":
            frame = pd.read_parquet(path)
            frame = frame[pd.to_datetime(frame.dt, utc=True) <= now]
        elif name == "roster":
            frame = pd.read_parquet(
                path, filters=[("season", "==", value), ("week", "<=", week + 1)]
            )
        else:
            predicates = [
                ("season", "==", value),
                ("week", ">=", 1),
                ("week", "<=", week),
            ]
            if "season_type" in schema.names:
                predicates.append(("season_type", "==", "REG"))
            frame = pd.read_parquet(path, filters=predicates)
        original = sha(path)
        temporary = path.with_suffix(".scoped.parquet")
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
        r.update(
            download_sha256=original,
            sha256=sha(path),
            bytes=path.stat().st_size,
            materialized_through_week=week,
            scoped_at=now.isoformat(),
        )
    (source / "sources.json").write_text(encoded(records))


def approve_snapshot(repo, source, capture_path, policy, *, now=None, proof=None):
    """Run only after time gate; before any player/team result materialisation."""
    repo = Path(repo).resolve()
    source = Path(source).resolve()
    source.relative_to(repo / "weekly_learning_state" / "sources")
    if (source / "operational_admission.json").exists():
        raise ValueError("Admitted snapshots are immutable")
    supplied_now = now
    meta, _ = capture_check(repo, capture_path)
    week = int(max(g.split("_")[1] for g in meta["game_kickoffs"]))
    season = int(next(iter(meta["game_kickoffs"])).split("_")[0])
    now = utc(now or datetime.now(UTC))
    cutoff = time_gate(policy, season, week, capture=meta, now=now)
    from scripts.forecast_features import schedule_times

    from .sources import verify_snapshot

    records = verify_snapshot(source, max_age_hours=48)
    for key in ["player_stats", "team_stats", "schedule", "snaps"]:
        if utc(records[key]["retrieved_at"]) < cutoff:
            raise ValueError("Results snapshot predates settlement cutoff")
    if proof is None:
        prior_proof = source / "finality.json"
        if not prior_proof.exists():
            raise ValueError(
                "Protected source pack lacks a pre-statistics finality proof; collect with the two-phase fetcher"
            )
        proof = json.loads(prior_proof.read_text())
    for key in ["player_stats", "team_stats", "snaps"]:
        if utc(records[key]["retrieved_at"]) < utc(proof["retrieved_at"]):
            raise ValueError(
                "Player/team results were retrieved before finality confirmation"
            )
    schedule = schedule_times(
        pd.read_parquet(
            source / "schedule.parquet",
            filters=[
                ("season", "==", season),
                ("week", "==", week),
                ("game_type", "==", "REG"),
            ],
        )
    )
    now = utc(supplied_now if supplied_now is not None else datetime.now(UTC))
    _proof_check(proof, schedule, cutoff, now)
    seal_source_files(source, season, week, now)
    prior = []
    allowed = {}
    for path in sorted(
        (repo / "weekly_learning_state" / "sources").glob(
            "*/operational_admission.json"
        )
    ):
        old = json.loads(path.read_text())
        if old["season"] == season and old["through_week"] < week:
            validate_receipt(repo, path, policy, now=now)
            prior.append({"path": str(path.relative_to(repo)), "sha256": sha(path)})
            allowed.update({g["game_id"]: g for g in old["allowed_games"]})
    for game in proof["games"]:
        allowed[game["game_id"]] = game
    receipt = {
        "schema": SCHEMA,
        "season": season,
        "through_week": week,
        "target_week": week + 1,
        "created_at": now.isoformat(),
        "settlement_cutoff": cutoff.isoformat(),
        "policy_sha256": sha(repo / "weekly_learning" / "policy.json"),
        "capture_path": str(Path(capture_path)),
        "capture_manifest_sha256": sha(repo / capture_path / "manifest.json"),
        "models": meta["models"],
        "proof": proof,
        "previous_admissions": prior,
        "allowed_games": list(allowed.values()),
        "source_path": str(source.relative_to(repo)),
        "sources_sha256": sha(source / "sources.json"),
    }
    path = source / "operational_admission.json"
    with path.open("x") as f:
        f.write(encoded(receipt))
    validate_receipt(repo, path, policy, now=now)
    return path


def _proof_check(proof, games, cutoff, now):
    if (
        not proof.get("url", "").startswith(ESPN + "?")
        or not cutoff <= utc(proof["retrieved_at"]) <= now
    ):
        raise ValueError("Invalid finality provenance/timestamp")
    if len(proof.get("response_sha256", "")) != 64:
        raise ValueError("Missing finality response digest")
    expected = {g.game_id: g for g in games.itertuples()}
    seen = set()
    for p in proof["games"]:
        if p["game_id"] not in expected or p["game_id"] in seen:
            raise ValueError("Unexpected/duplicate finality game")
        g = expected[p["game_id"]]
        seen.add(g.game_id)
        if p.get("confirmed_final") is not True or any(
            p[k] != getattr(g, k)
            for k in ["home_team", "away_team", "home_score", "away_score", "week"]
        ):
            raise ValueError("Finality evidence differs from nflverse")
        if (
            utc(p["kickoff_at"]) != utc(g.kickoff_at)
            or utc(p["completed_at"]) >= now
            or utc(p["completed_at"]) != utc(g.completed_at)
        ):
            raise ValueError("Invalid finality availability")
    if seen != set(expected):
        raise ValueError("Finality coverage incomplete")


def validate_receipt(repo, path, policy, *, now=None):
    repo = Path(repo).resolve()
    now = utc(now or datetime.now(UTC))
    path = Path(path)
    # Global floor before reading a receipt that may contain protected outcomes.
    time_gate(
        policy,
        policy["operational_scope"]["season"],
        policy["operational_scope"]["first_week"],
        now=now,
    )
    r = json.loads(path.read_text())
    if (
        r.get("schema") != SCHEMA
        or r["target_week"] != r["through_week"] + 1
        or r["policy_sha256"] != sha(repo / "weekly_learning" / "policy.json")
    ):
        raise ValueError("Operational admission identity/policy mismatch")
    meta, _ = capture_check(repo, r["capture_path"], r["capture_manifest_sha256"])
    cutoff = time_gate(policy, r["season"], r["through_week"], capture=meta, now=now)
    if (
        utc(r["settlement_cutoff"]) != cutoff
        or not cutoff <= utc(r["created_at"]) <= now
        or r["models"] != meta["models"]
    ):
        raise ValueError("Operational admission timing/model mismatch")
    source = (repo / r["source_path"]).resolve()
    source.relative_to(repo / "weekly_learning_state" / "sources")
    from scripts.forecast_features import schedule_times

    from .sources import verify_snapshot

    if sha(source / "sources.json") != r["sources_sha256"]:
        raise ValueError("Admitted source identity changed")
    verify_snapshot(source)
    games = schedule_times(
        pd.read_parquet(
            source / "schedule.parquet",
            filters=[
                ("season", "==", r["season"]),
                ("week", "==", r["through_week"]),
                ("game_type", "==", "REG"),
            ],
        )
    )
    if (
        games.empty
        or games.completed_at.isna().any()
        or not pd.to_datetime(games.completed_at, utc=True).lt(now).all()
    ):
        raise ValueError("Admitted week no longer has complete finality")
    for name in ["player_stats", "team_stats", "schedule", "snaps"]:
        if (
            utc(json.loads((source / "sources.json").read_text())[name]["retrieved_at"])
            < cutoff
        ):
            raise ValueError("Source predates settlement cutoff")
    records = json.loads((source / "sources.json").read_text())
    for key in ["player_stats", "team_stats", "snaps"]:
        if utc(records[key]["retrieved_at"]) < utc(r["proof"]["retrieved_at"]):
            raise ValueError("Statistics predate confirmed finality")
    _proof_check(r["proof"], games, cutoff, now)
    allowed = {g["game_id"]: g for g in r["proof"]["games"]}
    for previous in r["previous_admissions"]:
        p = (repo / previous["path"]).resolve()
        p.relative_to(repo / "weekly_learning_state" / "sources")
        if sha(p) != previous["sha256"]:
            raise ValueError("Previous admission changed")
        old = json.loads(p.read_text())
        if old["season"] != r["season"] or old["through_week"] >= r["through_week"]:
            raise ValueError("Admission chain is not chronological")
        validate_receipt(repo, p, policy, now=now)
        allowed.update({g["game_id"]: g for g in old["allowed_games"]})
    if (
        len(r["allowed_games"]) != len(allowed)
        or {g["game_id"]: g for g in r["allowed_games"]} != allowed
    ):
        raise ValueError("Cumulative admission coverage differs")
    return r
