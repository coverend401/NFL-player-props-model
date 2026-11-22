"""Independent selection admission; never changes certified release validation."""

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "research_audits/sunday-20261122/integrity.json"
REQUIRED_FILES = (
    {
        "research_selection_releases/enhanced-sunday-20261121-v1/" + name
        for name in [
            "forecasts.parquet",
            "top_picks.csv",
            "top2.csv",
            "fixtures.csv",
            "manifest.json",
        ]
    }
    | {
        "research_inference_releases/research-week11-frozen-20261120-r2/" + name
        for name in ["eligibility.json", "roster_evidence.csv", "schedule.parquet"]
    }
    | {
        "experiments/season_intelligence/sunday-20261121-v1/sunday_feature_states.parquet"
    }
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normal_name(value):
    value = (
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    value = re.sub(r"\b(jr|sr|ii|iii|iv)\.?$", "", value.strip())
    return re.sub(r"[^a-z]", "", value)


def block_reason(release, report_path=REPORT, now=None):
    """Missing, failed, expired or unbound evidence cannot admit selections."""
    try:
        report = json.loads(Path(report_path).read_text())
        if report["release_id"] != release["release_id"]:
            return "This research release has no matching player–fixture audit."
        if report["status"] != "PASS":
            return "Player–team–fixture verification is incomplete. Selections and pricing are withheld."
        required = (
            "authoritative_schedule_verified",
            "current_player_transactions_verified",
            "availability_review_complete",
            "opponent_features_verified",
        )
        if not all(report.get(key) is True for key in required):
            return "Required schedule, roster, availability or opponent evidence is missing."
        if report["internal_error_rows"] != 0 or report["fixture_feed_disagreements"]:
            return "Unresolved player or fixture association errors remain."
        if datetime.fromisoformat(report["valid_until"]) <= (now or datetime.now(UTC)):
            return "Player–fixture verification has expired."
        files = report["files"]
        if not REQUIRED_FILES.issubset(files):
            return "The integrity audit does not bind all forecast and identity files."
        for relative, expected in files.items():
            path = (ROOT / relative).resolve()
            if not path.is_relative_to(ROOT) or digest(path) != expected:
                return "Forecast or evidence files changed after the integrity audit."
        return None
    except (OSError, ValueError, KeyError, TypeError):
        return "A complete, valid player–fixture audit is unavailable."


def check_association(row, schedule, roster):
    """Reject invalid or ambiguous associations, not merely unknown name strings."""
    games = schedule[schedule.game_id.eq(row["game_id"])]
    if len(games) != 1:
        return "schedule_missing_or_ambiguous"
    game = games.iloc[0]
    teams = {game.home_team, game.away_team}
    if (
        row["team"] not in teams
        or row["opponent"] not in teams
        or row["team"] == row["opponent"]
    ):
        return "invalid_team_opponent_join"
    expected_id = (
        f"{int(game.season)}_{int(game.week):02d}_{game.away_team}_{game.home_team}"
    )
    if row["game_id"] != expected_id:
        return "invalid_fixture_identity"
    players = roster[roster.gsis_id.eq(row["player_id"])]
    teams = set(players.team.dropna())
    if teams != {row["team"]}:
        return "roster_missing_or_conflicting_team"
    if set(players.status.dropna()) != {"ACT"}:
        return "active_roster_not_confirmed"
    if "player" in row:
        if "full_name" not in players:
            return "roster_name_evidence_missing"
        names = set(players.full_name.map(normal_name))
        for first in ["first_name", "football_name"]:
            if first in players and "last_name" in players:
                names.update(
                    (players[first] + " " + players.last_name).map(normal_name)
                )
        if normal_name(row["player"]) not in names:
            return "player_name_identifier_mismatch"
    return None
