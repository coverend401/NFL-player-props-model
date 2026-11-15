"""Deterministic research decisions. No fitting, wagers, stakes or outcomes."""

import math
from collections import defaultdict
from datetime import timedelta

from scipy.stats import norm

from sgo_research.contracts import utc
from sgo_research.market import benchmarks

POLICY_ID = "stage1a-research-watch-only-v1"


def retain_snapshots(existing, snapshot, now):
    """Private per-session snapshots only, bounded to six windows and 15 minutes."""
    kept = []
    for s in [*existing, snapshot]:
        try:
            age = (now - utc(s["retrieved_at"])).total_seconds()
        except (KeyError, ValueError, TypeError):
            continue
        if 0 <= age <= 900:
            # Same request replaces its older response, never refreshing its timestamps.
            scope = s.get("request_scope", {})
            key = (
                scope.get("startsAfter"),
                scope.get("startsBefore"),
                scope.get("bookmakerID"),
            )
            kept = [x for x in kept if x[0] != key]
            kept.append((key, s))
    return [s for _, s in kept[-6:]]


def evaluate(snapshots, slate, release, now):
    """Each book-line is evaluated independently; medians never become quoted prices."""
    pairs = {}
    issues = []
    for snapshot in snapshots:
        rows, excluded = benchmarks(snapshot, slate, release, now)
        issues.extend(excluded)
        for r in rows:
            for book, b in r["books"].items():
                key = (r["game_id"], r["player_id"], r["market"], book)
                previous = pairs.get(key)
                if previous is None or utc(r["retrieved_at"]) > utc(
                    previous[0]["retrieved_at"]
                ):
                    pairs[key] = (r, b)
    markets = defaultdict(list)
    for key, pair in pairs.items():
        markets[key[:3]].append(pair)
    output = []
    for key, group in markets.items():
        lines = sorted(b["line"] for _, b in group)
        n = len(lines)
        median = (lines[(n - 1) // 2] + lines[n // 2]) / 2
        for benchmark, book in group:
            by_side = {q["side"]: q for q in book["quotes"]}
            over, under = by_side["Over"], by_side["Under"]
            total = 1 / over["decimal_odds"] + 1 / under["decimal_odds"]
            for side, q in by_side.items():
                p = q["model_probability"]
                half = (
                    abs(q["line"] * 2 - round(q["line"] * 2)) < 1e-9
                    and abs(q["line"] - round(q["line"])) > 1e-9
                )
                supported = half and q["ev_pct"] is not None and p is not None
                ev = q["ev_pct"] if supported else None
                reasons = []
                if not supported:
                    reasons.append(
                        "Integer/quarter-line pushes are not modelled; probability/EV selection is unavailable."
                    )
                if total < 1:
                    reasons.append(
                        "Underround paired prices need independent availability review."
                    )
                classification = (
                    "WATCH" if ev is not None and ev > 0 and total >= 1 else "PASS"
                )
                reasons.append(
                    "Stage 1A normal-tail probability has not earned independent live betting calibration."
                )
                reasons.append(
                    "US benchmark; Northern Ireland availability and settlement/inactive rules are unverified."
                )
                if ev is not None and ev <= 0:
                    reasons.insert(
                        0, "Quoted-price Stage 1A estimated EV is non-positive."
                    )
                if classification == "WATCH":
                    reasons.insert(
                        0,
                        "Positive estimated EV at this exact quote; experimental watch only, not a validated bet.",
                    )
                mu, sigma = q["projection"], q["resid_std"]
                stress = []
                if supported:
                    for shifted in [mu - sigma, mu + sigma]:
                        po = float(norm.sf(q["line"], shifted, sigma))
                        stress.append(
                            100
                            * (
                                (po if side == "Over" else 1 - po) * q["decimal_odds"]
                                - 1
                            )
                        )
                modelp = p if supported else None
                marketp = (1 / q["decimal_odds"]) / total
                output.append(
                    {
                        "policy_id": POLICY_ID,
                        "classification": classification,
                        "validation": "EXPERIMENTAL",
                        "player": benchmark["player"],
                        "player_id": benchmark["player_id"],
                        "game_id": benchmark["game_id"],
                        "market": benchmark["market"],
                        "team": q["team"],
                        "bookmaker": q["bookmaker"],
                        "side": side,
                        "line": q["line"],
                        "decimal_odds": q["decimal_odds"],
                        "fractional_odds": q["fractional_odds"],
                        "projection": mu,
                        "residual_scale": sigma,
                        "model_probability": modelp,
                        "implied_probability": 1 / q["decimal_odds"],
                        "no_vig_probability": marketp,
                        "overround_pct": 100 * (total - 1),
                        "ev_pct": ev,
                        "probability_gap": modelp - marketp if supported else None,
                        "fair_decimal": 1 / modelp
                        if supported and modelp > 0
                        else None,
                        "median_line": median,
                        "book_count": n,
                        "market_difference": mu - median,
                        "percentage_difference": 100 * (mu - median) / abs(median)
                        if median
                        else None,
                        "oldest_update": min(
                            utc(x["provider_updated_at"]) for x in by_side.values()
                        ).isoformat(),
                        "retrieved_at": q["retrieved_at"],
                        "kickoff_at": q["kickoff_at"],
                        "age_seconds": max(
                            (now - utc(x["provider_updated_at"])).total_seconds()
                            for x in by_side.values()
                        ),
                        "valid_until": min(
                            min(utc(x["provider_updated_at"]) for x in by_side.values())
                            + timedelta(minutes=15),
                            utc(q["retrieved_at"]) + timedelta(minutes=15),
                            utc(q["kickoff_at"]) - timedelta(minutes=60),
                        ).isoformat(),
                        "forecast_at": q["forecast_at"],
                        "matching_confidence": q["matching_confidence"],
                        "source_odd_id": q["odd_id"],
                        "raw_sha256": q["raw_sha256"],
                        "primary_scope_verified": q["primary_scope_verified"],
                        "raw_main_line_flag": q["main_line"],
                        "stress_ev_min": min(stress) if stress else None,
                        "stress_ev_max": max(stress) if stress else None,
                        "reasons": reasons,
                        "recommendation_stake": 0,
                        "release_id": release["release_id"],
                    }
                )
    # Ordinal triage, not a fitted confidence score: no correlated evidence sums.
    output.sort(
        key=lambda r: (
            r["classification"] == "WATCH",
            r["ev_pct"] if r["ev_pct"] is not None else -math.inf,
        ),
        reverse=True,
    )
    return output, issues


def player_evidence(state, player_id, game_id):
    """Facts and hypotheses remain separate; never a numerical adjustment."""
    if not state:
        return {
            "facts": [],
            "hypotheses": [],
            "missing": ["Compatible matchup evidence unavailable."],
        }
    fixture = next((f for f in state["fixtures"] if f["game_id"] == game_id), None)
    if not fixture:
        return {
            "facts": [],
            "hypotheses": [],
            "missing": ["No frozen fixture assessment."],
        }
    facts = []
    hypotheses = []
    missing = []
    for a in fixture["assessments"]:
        people = a.get("quarterbacks", []) + a.get("receivers", [])
        for person in people:
            if person.get("player_id") != player_id:
                continue
            v = a["offensive_volume"]
            facts.append(
                f"{a['offense']}: {v['games']} recent completed games, {v['plays_per_game']} plays/game and {v['dropbacks_per_game']} dropbacks/game."
            )
            if "statistics" in person:
                s = person["statistics"]
                facts.append(
                    f"Observed QB scrambles: {s['scramble_n']}/{s.get('scramble_label_n', s['dropbacks'])} labelled dropbacks; charted pressure games: {s['charted_pressure_games']}."
                )
                i = person["interpretation"]
                hypotheses.extend([i["direction"], i["assumption"]])
            else:
                facts.append(
                    f"{person['observed_targets']:g} covered targets in {person['observed_games']} observed games; at/behind-LOS targets {person['at_or_behind_LOS_targets']}/{person['known_target_air_yards_n']} known-depth targets."
                )
                hypotheses.append(person["direction"])
            missing.extend(a["missing"])
    if not facts:
        missing.append(
            "No player-specific usage evidence in this frozen snapshot; do not infer zero usage."
        )
    missing.extend(
        [
            "Confirmed injury/inactive status and routes unavailable.",
            "No validated numerical matchup adjustment or forecast scenario probabilities.",
        ]
    )
    return {
        "facts": facts,
        "hypotheses": hypotheses,
        "missing": list(dict.fromkeys(missing)),
        "as_of": fixture["effective_history_cutoff"],
    }
