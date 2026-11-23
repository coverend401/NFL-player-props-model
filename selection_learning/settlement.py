"""Selection settlement from already admitted operational cycles; never fetches results."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from weekly_learning.admission import time_gate, utc, validate_receipt
from weekly_learning.store import ROOT, Store, sha

from .engine import VERSION, digest, rankings
from .store import append, validate


def freeze(state, records, *, now=None, release_id, forecast_manifest_sha256):
    now = utc(now or datetime.now(UTC))
    validate(state)
    if not records:
        raise ValueError("No actual quoted propositions to freeze")
    if any(
        not utc(r["retrieved_at"]) <= now < utc(r["expires_at"])
        or now >= utc(r["kickoff_at"]) - pd.Timedelta(minutes=60)
        for r in records
    ):
        raise ValueError("Cannot freeze expired or post-cutoff propositions")
    old_ids = {
        r["quote_id"]
        for e in state["events"]
        if e["kind"] == "freeze"
        for r in e["payload"]["records"]
    }
    if len({r["quote_id"] for r in records}) != len(records) or any(
        r["quote_id"] in old_ids for r in records
    ):
        raise ValueError(
            "Duplicate predecision quotes cannot be frozen or counted twice"
        )
    top, games = rankings(records, now=now)
    payload = {
        "frozen_at": now.isoformat(),
        "capture_tier": "genuine_predecision_capture",
        "release_id": release_id,
        "forecast_manifest_sha256": forecast_manifest_sha256,
        "ranking_version": VERSION,
        "records": records,
        "top_picks": [r["quote_id"] for r in top],
        "top2": {g: [r["quote_id"] for r in rs] for g, rs in games.items()},
        "paper_stake": 1.0,
        "financial_scope": "hypothetical fixed one-unit paper stakes; no bankroll access",
        "game_kickoffs": {r["game_id"]: r["kickoff_at"] for r in records},
    }
    return append(state, "freeze", digest(payload), now.isoformat(), payload)


def settle_records(state, actuals, *, now, policy, receipt_id):
    """Pure scorer. Caller must verify an operational receipt before obtaining actuals."""
    validate(state)
    now = utc(now)
    if actuals.duplicated(["game_id", "player_id", "market"]).any():
        raise ValueError("Ambiguous selection outcomes")
    lookup = actuals.set_index(["game_id", "player_id", "market"])
    updated = state
    for event in state["events"]:
        if event["kind"] != "freeze":
            continue
        capture = event["payload"]
        for r in capture["records"]:
            identity = event["id"] + ":" + r["quote_id"]
            if any(
                e["kind"] == "settlement" and e["id"] == identity
                for e in updated["events"]
            ):
                continue
            season, week = map(int, r["game_id"].split("_")[:2])
            key = (r["game_id"], r["player_id"], r["market"])
            if key not in lookup.index:
                continue  # Pending, never zero or implicitly void.
            time_gate(policy, season, week, capture=capture, now=now)
            a = lookup.loc[key]
            if (
                a["status"] != "scored"
                or pd.isna(a["actual"])
                or pd.isna(a.get("completed_at"))
                or utc(a["completed_at"]) >= now
            ):
                continue
            outcome = float(a["actual"])
            if "yards" not in r["market"] and (outcome < 0 or not outcome.is_integer()):
                raise ValueError("Invalid count outcome")
            delta = outcome - r["line"]
            won = delta > 0 if r["side"] == "over" else delta < 0
            push = delta == 0
            status = "push" if push else "win" if won else "loss"
            probability = r.get("hit_probability")
            scored = {
                "freeze_id": event["id"],
                "quote_id": r["quote_id"],
                "game_id": r["game_id"],
                "player_id": r["player_id"],
                "market": r["market"],
                "outcome": outcome,
                "status": status,
                "paper_profit": 0.0 if push else r["decimal_odds"] - 1 if won else -1.0,
                "brier": None
                if probability is None or push
                else (probability - int(won)) ** 2,
                "log_loss": None
                if probability is None or push
                else -__import__("math").log(
                    max(1e-15, min(1 - 1e-15, probability if won else 1 - probability))
                ),
                "hit_probability": probability,
                "receipt_id": receipt_id,
                "scope": "hypothetical one-unit paper return at owner-recorded quote; not realised ROI",
            }
            updated = append(updated, "settlement", identity, now.isoformat(), scored)
    return updated


def performance(state, *, slate=None):
    records = [e["payload"] for e in state["events"] if e["kind"] == "settlement"]
    freezes = [e for e in state["events"] if e["kind"] == "freeze"]
    groups = {"all_quoted_propositions": set(), "top_picks": set(), "top2": set()}
    for e in freezes:
        for r in e["payload"]["records"]:
            groups["all_quoted_propositions"].add((e["id"], r["quote_id"]))
        for q in e["payload"]["top_picks"]:
            groups["top_picks"].add((e["id"], q))
        for rs in e["payload"]["top2"].values():
            groups["top2"].update((e["id"], q) for q in rs)
    if slate is not None:
        allowed = {
            (e["id"], r["quote_id"])
            for e in freezes
            for r in e["payload"]["records"]
            if "_".join(r["game_id"].split("_")[:2]) == slate
        }
        groups = {name: keys & allowed for name, keys in groups.items()}
        records = [r for r in records if "_".join(r["game_id"].split("_")[:2]) == slate]
    report = {}
    for name, keys in groups.items():
        rows = [r for r in records if (r["freeze_id"], r["quote_id"]) in keys]
        binary = [r for r in rows if r["status"] != "push"]
        profit = sum(r["paper_profit"] for r in rows)
        report[name] = {
            "frozen_n": len(keys),
            "settled_n": len(rows),
            "pending_n": len(keys) - len(rows),
            "hit_rate_excluding_push": sum(r["status"] == "win" for r in binary)
            / len(binary)
            if binary
            else None,
            "brier": sum(r["brier"] for r in binary if r["brier"] is not None)
            / sum(r["brier"] is not None for r in binary)
            if any(r["brier"] is not None for r in binary)
            else None,
            "log_loss": sum(r["log_loss"] for r in binary if r["log_loss"] is not None)
            / sum(r["log_loss"] is not None for r in binary)
            if any(r["log_loss"] is not None for r in binary)
            else None,
            "paper_profit_units": profit,
            "hypothetical_paper_roi": profit / len(rows) if rows else None,
            "actual_roi": None,
        }
    report["calibration_bands"] = []
    for low in range(0, 100, 10):
        band = [
            r
            for r in records
            if r["status"] != "push"
            and r.get("hit_probability") is not None
            and low / 100
            <= r["hit_probability"]
            < (low + 10) / 100 + (1e-12 if low == 90 else 0)
        ]
        if band:
            report["calibration_bands"].append(
                {
                    "band": f"{low}–{low + 10}%",
                    "n": len(band),
                    "mean_probability": sum(r["hit_probability"] for r in band)
                    / len(band),
                    "observed_hit_rate": sum(r["status"] == "win" for r in band)
                    / len(band),
                }
            )
    if slate is None:
        slates = sorted(
            {
                "_".join(r["game_id"].split("_")[:2])
                for e in freezes
                for r in e["payload"]["records"]
            }
        )
        report["by_slate"] = {key: performance(state, slate=key) for key in slates}
    return report


def reconcile_cycle(journal, cycle, *, now=None):
    now = utc(now or datetime.now(UTC))
    # Check the time gate before opening any result artifacts.
    policy = json.loads((ROOT / "weekly_learning/policy.json").read_text())
    state, version = journal.read()
    freezes = [e for e in state["events"] if e["kind"] == "freeze"]
    if not freezes:
        return {"status": "no_frozen_selections", "metrics": performance(state)}
    time_gate(
        policy,
        policy["operational_scope"]["season"],
        policy["operational_scope"]["first_week"],
        now=now,
    )
    cycle = Path(cycle).resolve()
    cycle.relative_to(ROOT / "weekly_learning_state/cycles")
    Store(ROOT / "weekly_learning_state").validate(cycle)
    report = json.loads((cycle / "report.json").read_text())
    if (
        report.get("mode") != "operational"
        or report.get("status") not in ["completed", "completed_with_missing"]
        or not report.get("admission_sha256")
    ):
        raise ValueError(
            "Only admitted prospective operational results can settle selections"
        )
    receipts = list(
        (ROOT / "weekly_learning_state/sources").glob("*/operational_admission.json")
    )
    matches = [
        p
        for p in receipts
        if sha(p) == report["admission_sha256"]
        and sha(p.parent / "sources.json") == report["sources_sha256"]
    ]
    if len(matches) != 1:
        raise ValueError("Operational results provenance missing or ambiguous")
    validate_receipt(ROOT, matches[0], policy, now=now)
    actuals = pd.read_parquet(cycle / "reconciled.parquet")
    updated = settle_records(
        state, actuals, now=now, policy=policy, receipt_id=report["admission_sha256"]
    )
    metrics = performance(updated)
    report_id = digest(
        {
            "cycle": cycle.name,
            "settlements": [
                e["sha256"] for e in updated["events"] if e["kind"] == "settlement"
            ],
        }
    )
    updated = append(
        updated,
        "weekly_report",
        report_id,
        now.isoformat(),
        {
            "cycle": cycle.name,
            "metrics": metrics,
            "ranking_version": VERSION,
            "promotion": "No automatic ranking adoption; chronological evidence required",
        },
    )
    journal.write(state, updated, version)
    return {"status": "reconciled", "metrics": metrics}
