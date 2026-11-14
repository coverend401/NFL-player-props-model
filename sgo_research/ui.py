"""Optional research view; no ledger imports, background jobs or quote downloads."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import streamlit as st

from .analysis import comparisons
from .client import Client
from .contracts import FREE_BOOKS, STAT_MARKETS, Unavailable, utc
from .store import Store


def research_key():
    key = os.environ.get("SPORTSGAMEODDS_API_KEY")
    if not key:
        try:
            key = st.secrets.get("sportsgameodds", {}).get("api_key")
        except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
            return None
    return key


def render(slate, release):
    st.subheader("Odds & Value — research only")
    st.caption(
        "Stage 1A probabilities at actual bookmaker lines. No wagers, ledger changes or settlement. UK bookmaker variants and live coverage require verification."
    )
    key = research_key()
    if not key:
        st.info(
            "No research API key configured. Existing forecasts remain available. Add SPORTSGAMEODDS_API_KEY as an environment secret; never paste it into chat."
        )
        return
    now = datetime.now(UTC)
    if slate.empty:
        st.info(
            "No approved projections available for comparison. Models will not be retrained here."
        )
        return
    week = st.selectbox("NFL week", sorted(slate.week.unique()), key="sgo_week")
    selected = slate[slate.week.eq(week)]
    books = st.multiselect(
        "Bookmakers (UK variants unverified)",
        FREE_BOOKS,
        default=["williamhill", "unibet"],
        key="sgo_books",
    )
    path = os.environ.get("SGO_RESEARCH_STORE")
    persistent = os.environ.get("SGO_PERSISTENT_VOLUME_APPROVED") == "1"
    terms = os.environ.get("SGO_PRIVATE_CACHE_TERMS_ACK") == "1"
    if not path or not persistent or not terms:
        st.warning(
            "Collection disabled: an approved persistent private quota store and data-use/cache acknowledgement are required. Ephemeral Streamlit storage cannot guarantee a durable free-tier limit."
        )
        return
    try:
        store = Store(Path(path), persistent=True)
        times = [
            utc(t)
            for gid, t in release.get("game_kickoffs", {}).items()
            if gid in set(selected.game_id) and utc(t) > now + timedelta(minutes=60)
        ]
        if not times:
            st.info("No future T−60 eligible fixtures in this approved slate.")
            return
        # Stable request window permits reuse across reruns, not rolling cache misses.
        start, end = (
            min(times) - timedelta(seconds=30),
            max(times) + timedelta(seconds=30),
        )
        if st.button(
            "Retrieve upcoming odds (manual, free budget enforced)", key="sgo_fetch"
        ):
            st.session_state["sgo_snapshot"] = Client(
                key, store, terms_ack=terms
            ).fetch(start.isoformat(), end.isoformat(), books=books)
        snapshot = st.session_state.get("sgo_snapshot")
        if not snapshot:
            st.info("No odds retrieved. No API call occurs until you press Retrieve.")
            return
        rows, issues = comparisons(snapshot, selected, release, now)
    except (Unavailable, OSError, ValueError, TypeError, KeyError):
        st.warning(
            "Research odds unavailable or unsafe to compare. No forecasts or settings have changed. Check private setup and provider availability."
        )
        return
    st.caption(
        f"Last retrieved: {snapshot['retrieved_at']} · {snapshot['account_tier']} · 10-minute cache · hard local ceiling 2,000 objects per provider interval (plus safety headroom)."
    )
    if snapshot.get("provider_notice"):
        st.caption(snapshot["provider_notice"])
    if snapshot.get("truncated"):
        st.warning(
            "Response truncated: coverage is incomplete. No automatic pagination."
        )
    markets = st.multiselect(
        "Markets",
        list(STAT_MARKETS.values()),
        default=list(STAT_MARKETS.values()),
        key="sgo_markets",
    )
    game = st.selectbox(
        "Game",
        ["All"] + sorted({r.get("game_id", r["event_id"]) for r in rows}),
        key="sgo_game",
    )
    player = st.text_input("Player contains", key="sgo_player").casefold()
    minimum = st.number_input("Minimum estimated EV (%)", value=0.0, key="sgo_ev")
    diagnostics = st.checkbox(
        "Include incomplete, unmatched and stale comparisons",
        value=True,
        key="sgo_diagnostics",
    )
    visible = [
        r
        for r in rows
        if r["bookmaker"] in books
        and (
            r["model_market"] in markets
            or r["model_market"].removeprefix("QB ") in markets
        )
        and (game == "All" or r.get("game_id", r["event_id"]) == game)
        and player in (r.get("player") or r.get("player_name") or "").casefold()
        and (diagnostics or r["eligible"])
        and (r["ev_pct"] is None or r["ev_pct"] >= minimum)
    ]
    visible.sort(
        key=lambda r: r["ev_pct"] if r["ev_pct"] is not None else -1e9, reverse=True
    )
    st.write(
        f"{len(visible)} comparisons; {sum(r['eligible'] for r in rows)} eligible research comparisons. No UK variants have been verified by this interface."
    )
    for r in visible[:30]:
        with st.container(border=True):
            st.markdown(
                f"**{r.get('player') or r.get('player_name') or 'Unmatched player'} — {r['model_market']}**"
            )
            st.write(
                f"{r['bookmaker']} · {r['side']} {r['line']:g} · decimal {r['decimal_odds']:.3f} · fractional {r['fractional_odds']}"
            )
            if r["model_probability"] is not None:
                st.write(
                    f"Projection {r['projection']:.2f} · model probability {r['model_probability']:.1%} · bookmaker implied {r['implied_probability']:.1%}"
                )
            st.write(
                "EV: excluded (push unsupported)"
                if r["ev_pct"] is None
                else f"Estimated EV: {r['ev_pct']:.2f}% (unvalidated Stage 1A pricing)"
            )
            st.caption(
                f"{r['comparison_status']} · match: {r['matching_confidence']} · provider {r['provider_updated_at']}"
            )
    if len(visible) > 30:
        st.caption("Showing the first 30; narrow filters to see others.")
    present = {r["canonical_stat"] for r in rows}
    st.caption(
        "Missing canonical markets in this response: "
        + (", ".join(k for k in STAT_MARKETS if k not in present) or "none")
    )
    st.caption(
        f"{len(issues)} unsupported/incomplete quote records excluded. Paper archival and outcome settlement remain disabled."
    )
