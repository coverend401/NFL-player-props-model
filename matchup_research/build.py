"""Freeze predecision descriptive fixture states; no fitting or sealed outcomes."""

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from release_utils import resolve_release, sha256
from sgo_research.contracts import name_key, team_key, utc

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = [
    "game_id",
    "play_id",
    "season",
    "week",
    "season_type",
    "posteam",
    "defteam",
    "play_type",
    "qb_dropback",
    "qb_scramble",
    "qb_hit",
    "sack",
    "air_yards",
    "passer_player_id",
    "receiver_player_id",
    "rusher_player_id",
]
MISSING = [
    "Validated full-team blitz/pressure denominators",
    "Man/zone and coverage-shell tendencies",
    "Pressure-specific QB scramble/throw/sack splits",
    "Time to throw and true screen/checkdown labels",
    "Individual offensive-line protection grades and injury availability",
    "Verified routes, snaps and current inactive/role changes",
    "Timestamped UK spread/total and weather information",
]


def safe_rate(numerator, denominator):
    return (
        float(numerator / denominator)
        if denominator > 0 and pd.notna(numerator)
        else None
    )


def contact_rates(plays):
    d = plays[plays.qb_dropback.eq(1)]
    known = d.qb_hit.notna() & d.sack.notna()
    hits = d.loc[known, "qb_hit"].eq(1) | d.loc[known, "sack"].eq(1)
    air = d.air_yards.dropna()
    scramble = d.qb_scramble.dropna()
    return {
        "dropbacks": len(d),
        "contact_label_n": int(known.sum()),
        "hit_or_sack_rate": safe_rate(hits.sum(), known.sum()),
        "sack_rate": safe_rate(d.sack.eq(1).sum(), d.sack.notna().sum()),
        "scramble_n": int(scramble.eq(1).sum()),
        "scramble_label_n": len(scramble),
        "scramble_rate": safe_rate(scramble.eq(1).sum(), len(scramble)),
        "air_yards_n": len(air),
        "mean_air_yards": float(air.mean()) if len(air) else None,
        "at_or_behind_LOS_rate": safe_rate(air.le(0).sum(), len(air)),
    }


def qb_response(qb):
    """Fixed descriptive rules, NOT estimated pressure effects or fitted cutoffs."""
    n = qb.get("scramble_label_n", qb["dropbacks"])
    r = qb["scramble_rate"]
    if n < 40 or r is None:
        return {
            "classification": "insufficient observed dropbacks",
            "direction": "unknown",
            "reason": "No supported player-specific pressure response can be inferred.",
            "assumption": "Additional QB dropbacks and actual pressure splits are required.",
        }
    if r >= 0.08:
        return {
            "classification": "higher observed scramble involvement",
            "direction": "conditional upward watch: QB rushing attempts/yards",
            "reason": "This player has scrambled on at least 8% of observed dropbacks; this is an explicit descriptive screening rule, not a learned effect.",
            "assumption": "If the defense produces pressure and opens escape lanes, broken plays could create rushing opportunities. Contain discipline could instead suppress them; blitz frequency is not verified.",
        }
    if r <= 0.03:
        return {
            "classification": "lower observed scramble involvement",
            "direction": "conditional short-target watch; no automatic QB rushing uplift",
            "reason": "This player has scrambled on at most 3% of observed dropbacks; this does not measure mobility or actual decisions under pressure.",
            "assumption": "If pressure arrives, short throws, sacks or throwaways may be more relevant than scrambling. RB/TE/WR beneficiaries require routes and actual hot-read evidence, which are missing.",
        }
    return {
        "classification": "mixed observed scramble involvement",
        "direction": "ambiguous; no directional QB adjustment",
        "reason": "Observed scramble frequency is between the fixed 3% and 8% screens.",
        "assumption": "Pressure response, protection, coverage and game state could change the outcome in either direction.",
    }


def recent_games(team_games, team, cutoff, n=4):
    eligible = team_games[
        team_games.team.eq(team)
        & (pd.to_datetime(team_games.completed_at, utc=True) <= pd.Timestamp(cutoff))
    ]
    return eligible.sort_values("kickoff_at").tail(n)


def assess_team(
    team, opponent, gid, slate, team_games, box, pbp, cutoff, charting, ngs
):
    own = recent_games(team_games, team, cutoff)
    opp = recent_games(team_games, opponent, cutoff)
    ids = set(own.game_id)
    oppids = set(opp.game_id)
    offense = pbp[pbp.game_id.isin(ids) & pbp.posteam.eq(team)]
    defense = pbp[pbp.game_id.isin(oppids) & pbp.defteam.eq(opponent)]
    projections = slate[slate.game_id.eq(gid) & slate.team.eq(team)]
    qbs = []
    charting[charting.game_id.isin(ids) & charting.team.eq(team)]
    defchart = charting[charting.game_id.isin(oppids) & charting.opponent.eq(opponent)]
    def_blitz = defchart.times_blitzed.sum(min_count=1)
    def_db = contact_rates(defense)["dropbacks"]
    matchup_charting = {
        "charted_passer_games": len(defchart),
        "charted_blitzes": float(def_blitz) if pd.notna(def_blitz) else None,
        "all_pbp_dropbacks": def_db,
        "cross_source_blitz_frequency_proxy": safe_rate(def_blitz, def_db),
        "caution": "Blitz counts from opposing-QB weekly PFR charting divided by all PBP dropbacks; charting coverage/denominator equivalence unverified. Defensive-player pressures are not summed, avoiding duplicate defenders on a play.",
    }
    for pid, d in projections[
        projections.position.eq("QB") & projections.market.eq("Passing Yards")
    ].groupby("player_id"):
        # Individual history across teams; never infer current roster from past boxes.
        q = pbp[
            (pbp.passer_player_id.eq(pid) | pbp.rusher_player_id.eq(pid))
            & pbp.qb_dropback.eq(1)
        ]
        games = q.groupby("game_id").play_id.count().index
        latest = (
            team_games[team_games.game_id.isin(games)]
            .drop_duplicates("game_id")
            .sort_values("kickoff_at")
            .tail(4)
            .game_id
        )
        rates = contact_rates(q[q.game_id.isin(latest)])
        names = {
            name_key(x) for x in box[box.player_id.eq(pid)].player_display_name.dropna()
        }
        c = charting[
            charting.game_id.isin(latest)
            & charting.pfr_player_name.map(name_key).isin(names)
        ]
        # An individual name mapping is accepted only if each matched game has
        # exactly one charting row; no fuzzy or retrospective roster inference.
        if c.duplicated("game_id").any() or c.pfr_player_id.nunique() > 1:
            c = c.iloc[:0]
        ng = ngs[
            ngs.player_gsis_id.eq(pid)
            & ngs.week.isin(team_games[team_games.game_id.isin(latest)].week)
        ]
        rates["charting_record_n"] = len(c)
        pressure = c.times_pressured_pct.dropna()
        rates["charted_pressure_games"] = len(pressure)
        rates["median_weekly_charted_pressure_exposure"] = (
            float(pressure.median()) if len(pressure) else None
        )
        rates["charted_blitzes_faced"] = (
            float(c.times_blitzed.sum(min_count=1))
            if c.times_blitzed.notna().any()
            else None
        )
        ttt = ng.avg_time_to_throw.dropna()
        rates["NGS_weeks"] = len(ttt)
        rates["median_weekly_average_time_to_throw"] = (
            float(ttt.median()) if len(ttt) else None
        )
        interpretation = qb_response(rates)
        interpretation["opponent_context"] = matchup_charting
        interpretation["protection_caution"] = (
            "Hit/sack and charted pressure exposure reflect QB behaviour, scheme, opponents and OL together; not an isolated pass-blocking grade."
        )
        qbs.append(
            {
                "player_id": pid,
                "player": str(d.iloc[0].player),
                "historical_games": len(latest),
                "statistics": rates,
                "interpretation": interpretation,
                "baseline_projections": {
                    r.market: float(r.projection)
                    for r in projections[projections.player_id.eq(pid)].itertuples()
                },
                "baseline_statuses": {
                    r.market: str(r.projection_status)
                    for r in projections[projections.player_id.eq(pid)].itertuples()
                },
                "role_caution": "Included in approved Stage 1A slate; not independent confirmation of starter or fitness.",
            }
        )
    history = box[box.game_id.isin(ids) & box.team.eq(team)].copy()
    covered = history.targets.sum(min_count=1)
    recipients = []
    current = set(projections.player_id)
    for pid, d in history[
        history.player_id.isin(current) & history.position.isin(["RB", "WR", "TE"])
    ].groupby("player_id"):
        targets = d.targets.sum(min_count=1)
        if pd.isna(targets):
            continue
        rows = projections[projections.player_id.eq(pid)]
        target_plays = offense[offense.receiver_player_id.eq(pid)]
        depth = target_plays.air_yards.dropna()
        recipients.append(
            {
                "pbp_targets": len(target_plays),
                "known_target_air_yards_n": len(depth),
                "at_or_behind_LOS_targets": int(depth.le(0).sum()),
                "mean_target_air_yards": float(depth.mean()) if len(depth) else None,
                "player_id": pid,
                "player": str(rows.iloc[0].player),
                "position": str(rows.iloc[0].position),
                "observed_targets": float(targets),
                "observed_games": int(d.game_id.nunique()),
                "covered_box_target_fraction": safe_rate(targets, covered),
                "baseline_projections": {
                    r.market: float(r.projection) for r in rows.itertuples()
                },
                "direction": "Conditional short-target candidate only; target depth, routes, screen role and availability are not established.",
            }
        )
    recipients = sorted(recipients, key=lambda r: r["observed_targets"], reverse=True)
    outlets = sorted(
        [r for r in recipients if r["at_or_behind_LOS_targets"] > 0],
        key=lambda r: r["at_or_behind_LOS_targets"],
        reverse=True,
    )[:3]
    for q in qbs:
        outlet_text = (
            ", ".join(
                f"{r['player']} ({r['position']}: {r['at_or_behind_LOS_targets']} observed at/behind-LOS targets)"
                for r in outlets
            )
            or "No supported current-slate outlet identified"
        )
        q["interpretation"]["interaction_notes"] = [
            f"Against {opponent}, PFR records {matchup_charting['charted_blitzes']} blitzes across {matchup_charting['charted_passer_games']} opposing-passer records. This is exposure evidence, not proof of tomorrow's calls.",
            f"{q['player']} has {q['statistics']['scramble_n']} observed scrambles on {q['statistics']['dropbacks']} dropbacks. Do not apply the same rushing adjustment to every QB or equate this with a pressure-conditioned scramble rate.",
            "If an earlier release is forced, observed shallow-usage candidates are "
            + outlet_text
            + ". Target depth is not proof of a screen, checkdown or hot-read assignment.",
            "Protection and containment, man/zone coverage and personnel availability remain unknown. They can reverse either a rushing or short-passing hypothesis.",
        ]
    pace_n = own.pace_n.sum()
    pace_sum = own.pace_sum.sum()
    volume = {
        "games": len(own),
        "plays_per_game": float(own.plays.mean()) if len(own) else None,
        "dropbacks_per_game": float(own.dropbacks.mean()) if len(own) else None,
        "dropback_fraction": safe_rate(own.dropbacks.sum(), own.plays.sum()),
        "neutral_clock_gap_seconds": safe_rate(pace_sum, pace_n),
        "neutral_clock_gap_n": int(pace_n),
        "points_for_per_game": float(own.points_for.mean()) if len(own) else None,
        "points_against_per_game": float(own.points_against.mean())
        if len(own)
        else None,
    }
    return {
        "offense": team,
        "opponent_defense": opponent,
        "history_game_ids": sorted(ids),
        "defense_history_game_ids": sorted(oppids),
        "offensive_volume": volume,
        "offense_contact_proxy": contact_rates(offense),
        "opponent_contact_proxy": contact_rates(defense),
        "opponent_charting": matchup_charting,
        "quarterbacks": qbs,
        "receivers": recipients,
        "target_coverage_caution": "Fractions use covered box-score targets, not guaranteed full team targets; WR/TE/RB history incompleteness remains unresolved. No exhaustive teammate allocation is claimed.",
        "game_script_scenarios": [
            {
                "scenario": "Trailing / hurry-up",
                "direction": "Passing attempts and target opportunities may rise; efficiency can fall.",
                "status": "Qualitative conditional scenario; no scenario probability or spread-derived forecast.",
            },
            {
                "scenario": "Leading / clock control",
                "direction": "Carries may rise while pass volume falls; workload allocation remains player-specific and unverified.",
                "status": "Qualitative conditional scenario; not a prediction that this team will lead.",
            },
        ],
        "missing": MISSING,
    }


def build(
    pbp_path, source_path, output, *, now=None, charting_path=None, ngs_path=None
):
    now = now or datetime.now(UTC)
    data, release = resolve_release(ROOT)
    source = json.loads(Path(source_path).read_text())
    if sha256(pbp_path) != source["sha256"] or utc(source["retrieved_at"]) > now:
        raise ValueError("Unverified/future source snapshot")
    context = ROOT / "research_inputs/stage1c/public-20261113-v3"
    m = json.loads((context / "manifest.json").read_text())
    if sha256(context / "team_games.parquet") != m["files"]["team_games.parquet"]:
        raise ValueError("Frozen context integrity mismatch")
    if any(utc(s["retrieved_at"]) > now for s in m["source_records"]):
        raise ValueError("Future context capture")
    team = pq.read_table(
        context / "team_games.parquet",
        filters=[("season", "=", 2026), ("week", "<", 11)],
    ).to_pandas()
    team = team[pd.to_datetime(team.completed_at, utc=True) <= pd.Timestamp(now)]
    ids = sorted(set(team.game_id))
    filters = [
        ("season", "=", 2026),
        ("week", "<", 11),
        ("season_type", "=", "REG"),
        ("game_id", "in", ids),
    ]
    plays = pq.read_table(pbp_path, columns=COLUMNS, filters=filters).to_pandas()
    if plays.duplicated(["game_id", "play_id"]).any():
        raise ValueError("Duplicate play identity")
    plays = plays[plays.play_type.isin(["pass", "run"])]
    box = pq.read_table(
        data / "weekly_player_data.parquet",
        columns=[
            "game_id",
            "player_id",
            "player_display_name",
            "team",
            "position",
            "targets",
        ],
        filters=[("season", "=", 2026), ("week", "<", 11), ("game_id", "in", ids)],
    ).to_pandas()
    if box.duplicated(["game_id", "player_id"]).any():
        raise ValueError("Duplicate box identity")
    extra_sources = []
    for path in [charting_path, ngs_path]:
        if path is None:
            raise ValueError("Explicit captured charting/NGS source paths required")
        meta = json.loads(Path(path).with_suffix(".source.json").read_text())
        if sha256(path) != meta["sha256"] or utc(meta["retrieved_at"]) > now:
            raise ValueError("Future/unverified auxiliary snapshot")
        extra_sources.append(meta)
    charting = pq.read_table(
        charting_path,
        columns=[
            "game_id",
            "season",
            "week",
            "team",
            "opponent",
            "pfr_player_name",
            "pfr_player_id",
            "times_blitzed",
            "times_pressured",
            "times_pressured_pct",
        ],
        filters=[
            ("season", "=", 2026),
            ("week", "<", 11),
            ("game_type", "=", "REG"),
            ("game_id", "in", ids),
        ],
    ).to_pandas()
    if charting.duplicated(["game_id", "pfr_player_id"]).any():
        raise ValueError("Duplicate charting identity")
    if not charting.times_pressured_pct.dropna().between(0, 1).all():
        raise ValueError("Unknown charting pressure units")
    ngs = pq.read_table(
        ngs_path,
        columns=["season", "week", "team_abbr", "player_gsis_id", "avg_time_to_throw"],
        filters=[
            ("season", "=", 2026),
            ("week", ">", 0),
            ("week", "<", 11),
            ("season_type", "=", "REG"),
        ],
    ).to_pandas()
    charting["team"] = charting.team.map(team_key)
    charting["opponent"] = charting.opponent.map(team_key)
    ngs["team_abbr"] = ngs.team_abbr.map(team_key)
    complete_pairs = set(zip(team.team, team.week))
    ngs = ngs[[pair in complete_pairs for pair in zip(ngs.team_abbr, ngs.week)]]
    if ngs.duplicated(["player_gsis_id", "week"]).any():
        raise ValueError("Duplicate NGS weekly identity")
    slate = pd.read_parquet(data / "slate.parquet")
    fixtures = []
    for gid, time in release["game_kickoffs"].items():
        kickoff = utc(time)
        decision = kickoff - timedelta(minutes=60)
        if (
            not datetime(2026, 11, 15, tzinfo=UTC)
            <= kickoff
            < datetime(2026, 11, 16, 6, tzinfo=UTC)
            or decision <= now
        ):
            continue
        parts = gid.split("_")
        away, home = parts[-2:]
        fixtures.append(
            {
                "game_id": gid,
                "away": away,
                "home": home,
                "kickoff_at": kickoff.isoformat(),
                "decision_at": decision.isoformat(),
                "effective_history_cutoff": now.isoformat(),
                "assessments": [
                    assess_team(
                        t,
                        o,
                        gid,
                        slate,
                        team,
                        box,
                        plays,
                        min(now, decision),
                        charting,
                        ngs,
                    )
                    for t, o in [(away, home), (home, away)]
                ],
            }
        )
    payload = {
        "schema": 1,
        "generated_at": now.isoformat(),
        "release_id": release["release_id"],
        "purpose": "Descriptive research only; no forecast/probability/EV adjustment",
        "source": source,
        "auxiliary_sources": extra_sources,
        "team_source_manifest_sha256": sha256(context / "manifest.json"),
        "evidence_class": "Observed before upcoming decision; original historical publication timing unverified; corrected nflverse statistics",
        "sealed_outcomes_accessed": False,
        "prediction_adjustments_enabled": False,
        "fixed_screening_rules": {
            "minimum_qb_dropbacks": 40,
            "lower_scramble_rate": 0.03,
            "higher_scramble_rate": 0.08,
            "recent_games": 4,
            "fitted": False,
        },
        "fixtures": sorted(fixtures, key=lambda f: f["kickoff_at"]),
    }
    encoded = json.dumps(payload, indent=2, allow_nan=False).encode()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    output.with_suffix(".sha256").write_text(hashlib.sha256(encoded).hexdigest() + "\n")
    return payload


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pbp", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--charting", type=Path, required=True)
    p.add_argument("--ngs", type=Path, required=True)
    a = p.parse_args()
    result = build(a.pbp, a.source, a.output, charting_path=a.charting, ngs_path=a.ngs)
    print("Pregame fixtures:", len(result["fixtures"]))
    print("No models fitted or adjusted. No sealed outcome rows materialised.")
