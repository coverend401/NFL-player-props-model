"""Audited quote ingestion and predeclared chronological singles accounting.

No quotes are supplied with this repository. Evidence hashes establish integrity,
not truth: provider identity/licence/archive authenticity require owner review.
Synthetic regression fixtures are never evidence of realised betting performance.
"""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from stage1b.betting import economics

QUOTE_FIELDS = [
    "quote_id",
    "bookmaker",
    "game_id",
    "player_id",
    "market",
    "side",
    "line",
    "odds",
    "quoted_at",
    "available_at",
    "decision_at",
    "kickoff_at",
    "rule_id",
    "evidence_id",
]
RULES = {
    "offensive_snap_action_v1": "Action iff verified offensive snaps > 0; any contrary official settlement blocks scoring."
}


def verify_quotes(quotes, evidence_manifest, evidence_root):
    missing = set(QUOTE_FIELDS) - set(quotes)
    if missing:
        raise ValueError("Missing quote columns: " + str(sorted(missing)))
    q = quotes.copy()
    for field in [
        "quote_id",
        "bookmaker",
        "game_id",
        "player_id",
        "market",
        "evidence_id",
    ]:
        if q[field].isna().any() or q[field].astype(str).str.strip().eq("").any():
            raise ValueError("Missing quote identity: " + field)
    if q.quote_id.duplicated().any():
        raise ValueError("Duplicate quote ID")
    if not q.side.isin(["Over", "Under"]).all() or not q.rule_id.isin(RULES).all():
        raise ValueError("Unsupported side or bookmaker settlement rule")
    for c in ["quoted_at", "available_at", "decision_at", "kickoff_at"]:
        if any(pd.isna(x) or pd.Timestamp(x).tzinfo is None for x in q[c]):
            raise ValueError("Quote timestamps require explicit timezone offsets")
        q[c] = pd.to_datetime(q[c], utc=True, errors="raise")
    if q[["quoted_at", "available_at", "decision_at", "kickoff_at"]].isna().any().any():
        raise ValueError("Missing quote timing")
    if not (
        (q.quoted_at <= q.available_at)
        & (q.available_at <= q.decision_at)
        & (q.decision_at < q.kickoff_at)
    ).all():
        raise ValueError("Post-decision or post-kickoff quote")
    if not np.equal(q.line * 2, np.floor(q.line * 2)).all():
        raise ValueError("Quarter/split settlement lines are not supported")
    if not np.isfinite(q[["line", "odds"]].to_numpy(float)).all() or q.odds.le(1).any():
        raise ValueError("Invalid line or decimal price")
    root = Path(evidence_root).resolve()
    verified = []
    for row in q.to_dict("records"):
        e = evidence_manifest.get(str(row["evidence_id"]))
        if (
            not e
            or e.get("classification") != "authentic_provider_archive"
            or not e.get("reviewed_by")
            or not e.get("licence_confirmed")
        ):
            raise ValueError(
                "Provenance not independently reviewed; no genuine return claim permitted"
            )
        path = (root / e["path"]).resolve()
        if root not in path.parents or path.is_symlink():
            raise ValueError("Evidence path escapes archive")
        if hashlib.sha256(path.read_bytes()).hexdigest() != e["sha256"]:
            raise ValueError("Evidence hash mismatch")
        url = e.get("source_url", "")
        host = urlparse(url).hostname
        if (
            urlparse(url).scheme != "https"
            or host != e.get("provider_host")
            or urlparse(url).query
            or urlparse(url).username
        ):
            raise ValueError("Invalid reviewed provider source")
        rule = e.get("settlement_rule")
        if not rule or rule.get("rule_id") != row["rule_id"]:
            raise ValueError("Archived settlement rule evidence required")
        rule_path = (root / rule["path"]).resolve()
        if (
            root not in rule_path.parents
            or rule_path.is_symlink()
            or hashlib.sha256(rule_path.read_bytes()).hexdigest() != rule["sha256"]
        ):
            raise ValueError("Settlement rule evidence missing or modified")
        rule_time = pd.Timestamp(rule["available_at"])
        if (
            pd.isna(rule_time)
            or rule_time.tzinfo is None
            or rule_time > row["decision_at"]
        ):
            raise ValueError("Retrospective settlement rules cannot be assumed")
        rule_url = urlparse(rule.get("source_url", ""))
        if (
            rule_url.scheme != "https"
            or not rule_url.hostname
            or rule_url.query
            or rule_url.username
        ):
            raise ValueError("Invalid reviewed settlement rule source")
        payload = json.loads(path.read_text())
        # Reviewed normalized extraction MUST bind every economic/identity field
        # to the archived source. Preserve the original provider response too.
        original = (root / e["original_path"]).resolve()
        if (
            root not in original.parents
            or original.is_symlink()
            or hashlib.sha256(original.read_bytes()).hexdigest() != e["original_sha256"]
        ):
            raise ValueError("Original provider response missing or modified")
        evidence = next(
            (x for x in payload["quotes"] if x["quote_id"] == row["quote_id"]), None
        )
        if evidence is None:
            raise ValueError("Quote not present in reviewed archive")
        for field in [
            "bookmaker",
            "game_id",
            "player_id",
            "market",
            "side",
            "line",
            "odds",
            "rule_id",
        ]:
            if (
                float(evidence[field]) != float(row[field])
                if field in ["line", "odds"]
                else str(evidence[field]) != str(row[field])
            ):
                raise ValueError("Quote differs from reviewed evidence: " + field)
        for field in ["quoted_at", "available_at", "kickoff_at"]:
            if pd.Timestamp(evidence[field]) != row[field]:
                raise ValueError("Quote timestamp differs from evidence")
        verified.append(e.get("provider_host"))
    q["provider_host"] = verified
    # Fixed policy: most recent available snapshot, not best retrospective price.
    return q.sort_values(["available_at", "quote_id"]).drop_duplicates(
        ["game_id", "player_id", "market", "side", "line", "decision_at"], keep="last"
    )


def settle_single(row):
    stake = float(row["stake"])
    if stake < 0 or not np.isfinite(stake):
        raise ValueError("Invalid stake")
    decision = pd.Timestamp(row["decision_at"])
    available = pd.Timestamp(row["outcome_available_at"])
    if (
        pd.isna(available)
        or pd.isna(decision)
        or available.tzinfo is None
        or decision.tzinfo is None
    ):
        raise ValueError("Settlement timing must be observed and timezone-aware")
    if available <= decision:
        raise ValueError("Outcome was already known at decision time")
    action = row["action_status"]
    if action == "unknown":
        return "unresolved", np.nan
    if action == "void":
        if row.get("official_void_verified", False) != True:
            raise ValueError("No participation alone is not proof of a bookmaker void")
        return "void", 0.0
    if action == "action" and (
        row.get("participation_verified", False) != True
        or row.get("positive_offensive_participation", False) != True
    ):
        raise ValueError("Action requires verified participation under this rule")
    if action != "action" or not np.isfinite(row["outcome"]):
        raise ValueError("Invalid observed settlement")
    if row["outcome"] == row["line"]:
        return "push", 0.0
    won = (
        (row["outcome"] > row["line"])
        if row["side"] == "Over"
        else (row["outcome"] < row["line"])
    )
    return ("win", stake * (row["odds"] - 1)) if won else ("loss", -stake)


def account(bets, starting_bankroll=1000.0):
    """Reserve all open stakes; realize profits only when outcomes are available."""
    if starting_bankroll <= 0:
        raise ValueError("Invalid starting bankroll")
    b = bets.copy()
    b["result"] = pd.Series(index=b.index, dtype="str")
    b["profit"] = np.nan
    if b.quote_id.duplicated().any():
        raise ValueError("Quote reused")
    for c in ["decision_at", "outcome_available_at"]:
        b[c] = pd.to_datetime(b[c], utc=True)
    events = []
    for i, row in b.iterrows():
        result, profit = settle_single(row)
        if result == "unresolved":
            raise ValueError(
                "Unresolved action prevents a genuine realised-return report"
            )
        events.extend(
            [
                (row.decision_at, 1, i, "reserve"),
                (row.outcome_available_at, 0, i, "settle"),
            ]
        )
        b.loc[i, "result"] = result
        b.loc[i, "profit"] = profit
    cash = starting_bankroll
    reserved = 0.0
    equity = starting_bankroll
    peak = equity
    max_dd = 0.0
    for _, _, i, kind in sorted(events):
        row = b.loc[i]
        stake = float(row.stake)
        if kind == "reserve":
            if stake > cash + 1e-9:
                raise ValueError("Stake exceeds unreserved cash")
            cash -= stake
            reserved += stake
        else:
            cash += stake + float(row.profit)
            reserved -= stake
            equity = cash + reserved
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
    staked = float(b.stake.sum())
    nonvoid = float(b.loc[b.result != "void", "stake"].sum())
    return b, {
        "bets": len(b),
        "staked_including_void": staked,
        "action_stake_including_push": nonvoid,
        "profit": float(b.profit.sum()),
        "roi_on_action_stake": float(b.profit.sum() / nonvoid) if nonvoid else None,
        "ending_bankroll": cash,
        "maximum_drawdown": max_dd,
        "wins": int(b.result.eq("win").sum()),
        "losses": int(b.result.eq("loss").sum()),
        "pushes": int(b.result.eq("push").sum()),
        "voids": int(b.result.eq("void").sum()),
    }


def run_verified_backtest(
    quotes, evidence_manifest, evidence_root, forecasts, protocol
):
    """Prices must already be generated at the exact quote/forecast decision time.

    forecasts must supply p_over/p_under/p_push for the QUOTED line, not a
    probability interpolated from the hypothetical evaluation probes.
    """
    q = verify_quotes(quotes, evidence_manifest, evidence_root)
    if q.empty:
        return q, {
            "authentic_quotes": 0,
            "genuine_bets": 0,
            "profit": None,
            "roi_on_action_stake": None,
        }
    if (q.decision_at >= pd.Timestamp(protocol["final_start"])).any():
        raise ValueError("Sealed final period cannot be backtested")
    policy = protocol["betting_policy"]
    maximum_age = pd.Timedelta(minutes=policy.get("maximum_quote_age_minutes", 5))
    if (
        (q.decision_at - q.available_at > maximum_age)
        | (q.decision_at - q.quoted_at > maximum_age)
    ).any():
        raise ValueError("Stale price availability cannot be assumed")
    keys = ["game_id", "player_id", "market", "line", "decision_at"]
    f = forecasts.copy()
    f.decision_at = pd.to_datetime(f.decision_at, utc=True)
    if f.duplicated(keys).any():
        raise ValueError("Ambiguous historical forecast")
    q = q.merge(f, on=keys, how="left", validate="many_to_one", indicator=True)
    if not q._merge.eq("both").all():
        raise ValueError("No exact predecision forecast for quote")
    if not (
        pd.to_datetime(q.model_information_available_at, utc=True) < q.decision_at
    ).all():
        raise ValueError("Model information after decision")
    if not (pd.to_datetime(q.history_available_at, utc=True) < q.decision_at).all():
        raise ValueError("Future history used")
    if (
        not np.allclose(q[["p_over", "p_under", "p_push"]].sum(axis=1), 1)
        or (q[["p_over", "p_under", "p_push"]] < 0).any().any()
    ):
        raise ValueError("Invalid outcome probability partition")
    q["ev"] = [
        economics(r.p_over if r.side == "Over" else r.p_under, r.p_push, r.odds)[
            "ev_per_unit"
        ]
        for r in q.itertuples()
    ]
    q = q[q.ev >= policy["minimum_ev"]].copy()
    # One side/line per player-market-game: earliest eligible quote, deterministic
    # tie-break. No outcome, settlement or later price determines selection.
    q = q.sort_values(["decision_at", "quote_id"]).drop_duplicates(
        ["game_id", "player_id", "market"]
    )
    q["stake"] = float(policy["fixed_stake"])
    bets, summary = account(q)
    return bets, {
        "classification": "provenance-reviewed historical quotes; retrospective statistical replay limitations still apply",
        **summary,
    }
