"""Targeted r8 coverage diagnostics and event-ID collection; existing research app."""

import os
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import streamlit as st

from matchup_research.ui import render as game_view
from research_access import secret
from sgo_research.config import quota_store
from sgo_research.contracts import Unavailable, utc
from sgo_research.event_client import EventClient
from sgo_research.ui import research_key

from .cards81 import market_card, model_card
from .coverage8 import (
    collect8,
    explain_error,
    plan8,
    price_merge,
    private_records,
    state8,
    two8,
    write_audit,
)
from .engine import evaluate
from .football_evidence import attach_context
from .slate import cached_snapshots, model_candidates, parlay_research
from .slate_notice import stale_sunday_notice
from .ui import (
    CSS,
    game_label,
    operations_view,
    performance_view,
    player_view,
    state_for,
)


def cache_path():
    return os.environ.get("SGO_RESEARCH_STORE") or str(
        Path(tempfile.gettempdir()) / "nfl-research-odds-cache.sqlite"
    )


def data8(slate, release):
    now = datetime.now(UTC)
    incoming = cached_snapshots(now)
    latest = st.session_state.get("market_snapshot")
    if latest:
        incoming.append(latest)
    snapshots = price_merge(
        [*st.session_state.get("intelligence_snapshots", []), *incoming], now
    )
    st.session_state["intelligence_snapshots"] = snapshots
    if latest and latest not in snapshots:
        st.session_state.pop("market_snapshot", None)
    rows, _ = evaluate(snapshots, slate, release, now)
    rows = [
        r
        for r in rows
        if now < utc(release["game_kickoffs"][r["game_id"]]) - timedelta(minutes=60)
    ]
    rows = attach_context(rows, release)
    models = attach_context(model_candidates(slate, release, now), release)
    history = private_records(cache_path(), "r8_audit", now)
    audit = next(
        (a["audit"] for a in history if a.get("release_id") == release["release_id"]),
        {},
    )
    audit = {**audit, **st.session_state.get("r8_audit", {})}
    # Keep r7 failure evidence if the same authenticated session survived deployment.
    for s in st.session_state.get("r7_batch_status", []):
        if s.get("status") == "blocked":
            for gid in s["games"]:
                audit.setdefault(
                    gid,
                    {
                        "stage": "response_rejected"
                        if s.get("code") == "UNSAFE"
                        else "collection_blocked",
                        "category": "E",
                        "code": s.get("code"),
                        "detail": s.get("message", "r7 collection stopped."),
                    },
                )
        elif s.get("status") == "not_requested_bounded_partial":
            for gid in s["games"]:
                audit.setdefault(
                    gid,
                    {
                        "stage": "not_attempted_after_block",
                        "category": "A",
                        "detail": "r7 did not request this fixture after its earlier response failure/bound.",
                    },
                )
    plan = plan8(slate, release, now, ["fanduel", "draftkings", "betmgm"])
    return (
        rows,
        models,
        snapshots,
        audit,
        plan,
        state8(rows, models, snapshots, audit, plan, release, now),
    )


def summary(states):
    counts = {
        "Eligible": len(states),
        "Bookmaker": sum(s["bookmaker"] for s in states.values()),
        "Model only": sum(s["model_only"] for s in states.values()),
        "No forecast": sum(
            not s["bookmaker"] and not s["models"] for s in states.values()
        ),
    }
    st.caption(" · ".join(f"{k}: {v}" for k, v in counts.items()))


def model8(row, release, state):
    model_card(row, release, state)


def collection8(slate, release, only=None):
    with st.expander(
        "Collect missing slate prices — bounded, rate-paced", expanded=False
    ):
        books = st.multiselect(
            "r8 bookmakers",
            ["fanduel", "draftkings", "betmgm"],
            default=["fanduel", "draftkings", "betmgm"],
        )
        if not research_key():
            st.info(
                "No research API key configured. Independent model research remains available; no provider request is made."
            )
        if not books:
            st.info("Select at least one bookmaker.")
            return
        plan = plan8(slate, release, datetime.now(UTC), books)
        if only:
            plan["games"] = [g for g in plan["games"] if g == only]
            plan["max_reserved_objects"] = 32 + len(plan["games"])
            plan["max_provider_http_calls"] = 2 * (2 + len(plan["games"]))
        st.write(
            f"{len(plan['games'])} eligible fixtures. Conservative maximum: {plan['max_reserved_objects']} reserved objects, {plan['max_provider_http_calls']} provider HTTP calls. Actual use falls with cached catalogue/prices and two-event batches."
        )
        st.caption(
            "Separate small event discovery from event-specific player prices. Six provider calls/minute remains enforced. One explicit foreground action may pause between requests, up to six minutes total; it never polls, retries failed requests or clears a halt. Existing account checks and atomic reservations remain before each uncached fetch."
        )
        if st.button(
            "Discover & collect missing eligible fixtures",
            disabled=not plan["games"] or not research_key(),
        ):
            progress = st.empty()
            client = None
            try:
                client = EventClient(
                    research_key(),
                    quota_store(),
                    terms_ack=str(secret("SGO_PRIVATE_CACHE_TERMS_ACK")) == "1",
                    object_cap=int(secret("SGO_OBJECT_CAP") or "2000"),
                    clock=lambda: datetime.now(UTC),
                    progress=progress.caption,
                )
                current = data8(slate, release)
                result = collect8(
                    plan,
                    slate,
                    release,
                    client,
                    current[2],
                    private_records(cache_path(), "r8_catalog", datetime.now(UTC)),
                    progress.caption,
                )
                st.session_state["r8_audit"] = {
                    **st.session_state.get("r8_audit", {}),
                    **result["audit"],
                }
                st.session_state["intelligence_snapshots"] = price_merge(
                    [*current[2], *result["snapshots"]], datetime.now(UTC)
                )
                if result["snapshots"]:
                    st.session_state["market_snapshot"] = result["snapshots"][-1]
                write_audit(
                    client,
                    {**result, "audit": dict(st.session_state["r8_audit"])},
                    release["release_id"],
                )
                st.rerun()
            except (
                Unavailable,
                OSError,
                ValueError,
                TypeError,
                KeyError,
                sqlite3.Error,
            ) as error:
                code, message = explain_error(error, client)
                st.warning(
                    f"Collection stopped [{code}]: {message}. No quota reset or automatic recovery."
                )
        st.caption(
            "A legacy r7 UNSAFE halt remains until reviewed recovery is explicitly authorised. This release contains no halt-clear or counter-reset control."
        )


def details(states, audit, release, plan):
    with st.expander("Per-fixture coverage evidence & diagnostics", expanded=False):
        for gid, s in states.items():
            st.write(f"{game_label(gid, release)} — {s['label']}")
            st.caption(f"{s['detail']} · pipeline category {s['category']}")
            if audit.get(gid):
                st.json(audit[gid], expanded=False)
        for gid, reason in plan["excluded"].items():
            st.caption(f"{gid}: {reason}")
        st.caption(
            "Catalogue timestamps identify provider events, not fresh prices or verified injury status. Price age/identity/O-U pairing/primary-line/T−60 guards are unchanged. No provider-coverage claim is inferred from a blocked or unattempted request."
        )


def certified_top8(slate, release):
    from .slate import unique_watch

    rows, models, _, audit, plan, states = data8(slate, release)
    state = state_for(release)
    st.markdown("### Top Picks")
    summary(states)
    watch = unique_watch(rows)
    priced = watch or sorted(
        [r for r in rows if r.get("ev_pct") is not None],
        key=lambda r: r["ev_pct"],
        reverse=True,
    )
    if priced:
        if not watch:
            st.info(
                "No positive estimated value: these comparisons are PASS research, not betting recommendations."
            )
        shown = set()
        for row in priced:
            identity = (row["game_id"], row["player_id"], row["market"], row["side"])
            if identity in shown:
                continue
            shown.add(identity)
            market_card(row, release, state)
            if len(shown) == 8:
                break
    else:
        st.info(
            "No current bookmaker-backed WATCH. Independent model research follows; no line, odds or EV is invented."
        )
    supported = {r["game_id"] for r in rows if r.get("ev_pct") is not None}
    unpriced = {g for g, s in states.items() if s["models"] and g not in supported}
    if unpriced:
        st.markdown("#### Model-only starting points across unpriced fixtures")
        choices = two8([], models, release)
        for gid in sorted(unpriced, key=lambda g: release["game_kickoffs"][g]):
            for row in choices.get(gid, [])[:1]:
                model8(row, release, state)
    collection8(slate, release)
    details(states, audit, release, plan)


def certified_games8(slate, release):
    rows, models, _, audit, plan, states = data8(slate, release)
    picks = two8(rows, models, release)
    state = state_for(release)
    st.markdown("### Top 2 by Game")
    summary(states)
    st.caption(
        "Highest eligible research comparisons per distinct player; PASS is not a positive-value recommendation. Where prices are absent/unsupported, model-only candidates carry no bookmaker-value claim."
    )
    for gid in plan["games"]:
        st.markdown("#### " + game_label(gid, release))
        st.caption(states[gid]["label"])
        if not picks[gid]:
            st.info("Insufficient complete data; no forced second pick.")
        for r in picks[gid]:
            if r["classification"] == "MODEL ONLY":
                model8(r, release, state)
            else:
                market_card(r, release, state)
    collection8(slate, release)
    details(states, audit, release, plan)


def top8(slate, release):
    from .enhanced_ui import render as enhanced

    if enhanced(release, "top"):
        if st.checkbox(
            "Show unchanged certified rankings and legacy bookmaker tools",
            key="enhanced_certified_top",
        ):
            certified_top8(slate, release)
    else:
        certified_top8(slate, release)


def games8(slate, release):
    from .enhanced_ui import render as enhanced

    if enhanced(release, "games"):
        if st.checkbox(
            "Show unchanged certified rankings and legacy bookmaker tools",
            key="enhanced_certified_games",
        ):
            certified_games8(slate, release)
    else:
        certified_games8(slate, release)


def parlays8(slate, release):
    rows, models, _, _, _, _ = data8(slate, release)
    picks = two8(rows, models, release)
    choices = {}
    for group in picks.values():
        for row in group:
            choices[
                "|".join(
                    str(row.get(k))
                    for k in [
                        "game_id",
                        "player_id",
                        "market",
                        "side",
                        "bookmaker",
                        "line",
                        "decimal_odds",
                    ]
                )
            ] = row
    st.markdown("### Parlay Research")
    st.caption(
        "This legacy parlay list uses unchanged certified forecasts; enhanced primary-screen selections are not validated joint-probability models."
    )
    st.info(
        "No validated joint probability or genuinely quoted combined price. No parlay EV or bet placement."
    )
    chosen = st.multiselect(
        "Research legs",
        list(choices),
        format_func=lambda k: (
            f"{choices[k]['player']} · {choices[k]['market']} · {choices[k]['classification']} · {choices[k]['game_id']}"
        ),
    )
    same = st.checkbox("Include same-game research (correlation unmodelled)", False)
    result = parlay_research([choices[k] for k in chosen], datetime.now(UTC), same)
    if result["leg_price_product"] is not None:
        st.metric(
            "Arithmetic leg-price product — NOT a quoted parlay",
            f"{result['leg_price_product']:.3f}",
        )
    st.write(
        "Actual combined quote, joint probability and parlay EV: unavailable. Model-only/PASS/expired legs cannot be priced."
    )
    for w in result["warnings"]:
        st.warning(w)


def render(slate, release):
    from weekly_learning.selection import for_app

    slate, release = for_app(slate, release)
    st.markdown(CSS, unsafe_allow_html=True)
    from .selection_integrity import availability_review, available_rows, block_reason

    blocked = block_reason(release)
    if blocked:
        st.error("INTEGRITY REVIEW — FAIL: " + blocked)
        st.info(
            "Top Picks, Top 2 by Game, player comparisons and bookmaker pricing are disabled. "
            "Existing forecast files are preserved; no selection is betting-ready. "
            "An active roster entry does not confirm game-day injury or inactive status."
        )
    else:
        for issue in availability_review()["material_issues"]:
            st.warning(f"Withheld player {issue['player_id']}: {issue['reason']}")
        slate = available_rows(slate)
        st.warning(
            "Roster/fixture review passed. Injury and game-day inactive information is unverified; "
            "these are research candidates, not injury-cleared selections. Check availability before use. "
            "Documented material availability issues are excluded individually."
        )
    st.caption(
        "NFL Research · Enhanced Sunday selections · certified Stage 1A preserved"
    )
    if release.get("weekly_selection_warning"):
        st.warning(release["weekly_selection_warning"])
    notice = stale_sunday_notice(slate, release, datetime.now(UTC))
    if notice:
        st.warning(notice)
    section = st.selectbox(
        "Workspace",
        [
            "Top Picks",
            "Top 2 by Game",
            "Parlay Research",
            "Player Intelligence",
            "Game Intelligence",
            "Market Intelligence",
            "Model Performance",
            "Weekly Learning",
            "Data & Safety",
        ],
    )
    if blocked and section not in {"Model Performance", "Weekly Learning"}:
        return
    if section == "Top Picks":
        top8(slate, release)
    elif section == "Top 2 by Game":
        games8(slate, release)
    elif section == "Parlay Research":
        parlays8(slate, release)
    elif section == "Player Intelligence":
        from .enhanced_ui import render as enhanced_player

        if not enhanced_player(release, "player"):
            data8(slate, release)
            player_view(slate, release)
    elif section == "Game Intelligence":
        from season_intelligence.ui import render as render_season_intelligence

        render_season_intelligence(release)
        from script_adjustment.ui import render as render_numerical

        render_numerical(release)
        from weekly_learning.operations import render_game_research

        render_game_research(release)
        from .sunday_script_ui import render as render_script

        render_script(release)
        game_view(release)
    elif section == "Market Intelligence":
        data8(slate, release)
        gid = st.selectbox(
            "Event-specific fixture",
            list(release["game_kickoffs"]),
            format_func=lambda g: game_label(g, release),
        )
        collection8(slate, release, only=gid)
        rows, _, _, audit, plan, states = data8(slate, release)
        for row in rows:
            if row["game_id"] == gid:
                market_card(row, release, state_for(release))
        details(states, audit, release, plan)
    elif section == "Model Performance":
        performance_view()
    elif section == "Weekly Learning":
        from weekly_learning.ui import render as learning_view

        learning_view()
    else:
        operations_view(release)
