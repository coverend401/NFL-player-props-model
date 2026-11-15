"""Password-gated standalone market benchmark cards; no production hooks."""

import logging
from datetime import UTC, datetime, timedelta

import streamlit as st

from matchup_research.ui import DEFAULT, load
from research_access import secret

from .client import Client
from .config import quota_store
from .contracts import Unavailable, utc
from .credentials import credential_status
from .diagnostics import CollectionBlocked, safe_diagnostic
from .market import US_BOOKS, benchmarks
from .ui import research_key


def render(slate, release):
    st.subheader("Market Intelligence — US research benchmarks")
    st.info(
        "US bookmaker prices may not be available to UK bettors. Disagreement is not betting value. Independent Stage 1A forecasts remain unchanged."
    )
    now = datetime.now(UTC)
    key = research_key()
    if not key:
        st.info("No research API key configured; no request made.")
        return
    week = st.selectbox("NFL week", sorted(slate.week.unique()))
    selected = slate[slate.week.eq(week)]
    eligible = {
        g: t
        for g, t in release["game_kickoffs"].items()
        if g in set(selected.game_id) and utc(t) > now + timedelta(minutes=60)
    }
    if not eligible:
        st.info("No T−60 eligible upcoming fixtures; no collection.")
        return
    gid = st.selectbox("Fixture", list(eligible))
    books = st.multiselect("US benchmark bookmakers", US_BOOKS, default=list(US_BOOKS))
    st.caption(
        "One selected fixture per request; no polling or pagination. Refresh no faster than the 10-minute cache. Stale or post-cutoff quotes never enter the median."
    )
    with st.expander("Collection diagnostics (no credentials shown)"):
        for setting in (
            "SPORTSGAMEODDS_API_KEY",
            "SGO_QUOTA_REPOSITORY",
            "SGO_GITHUB_QUOTA_TOKEN",
            "SGO_PRIVATE_CACHE_TERMS_ACK",
        ):
            st.caption(f"{setting}: {'configured' if secret(setting) else 'missing'}")
        st.caption(credential_status())
        st.caption(
            f"Current UK time: {now.strftime('%H:%M:%S')} · selected fixture T−60 cutoff: {(utc(eligible[gid]) - timedelta(minutes=60)).isoformat()}"
        )
        st.caption(
            "Configuration status does not prove token permissions. Quota access is checked on collection; no automatic diagnostic API calls."
        )
        if st.button("Check GitHub authentication (read-only; no odds)"):
            try:
                quota_store()
                st.success(
                    "Invalid-credential control rejected; supplied credential accepted; private quota state readable. Write permission is not proved by this read-only test. No odds or quota-counter writes."
                )
            except (Unavailable, ValueError, OSError, KeyError, TypeError) as error:
                code, message = safe_diagnostic(error)
                logging.getLogger(__name__).warning(
                    "Research authentication check blocked: code=%s", code
                )
                st.warning(f"Authentication check [{code}]: {message}")
    if st.button("Retrieve selected fixture's market lines"):
        stage = "configuration"
        try:
            kickoff = utc(eligible[gid])
            try:
                cap = int(secret("SGO_OBJECT_CAP") or "2000")
                if not 1 <= cap <= 2000:
                    raise ValueError
            except (ValueError, TypeError):
                raise CollectionBlocked("CONFIG_CAP") from None
            if str(secret("SGO_PRIVATE_CACHE_TERMS_ACK")) != "1":
                raise CollectionBlocked("TERMS")
            if not books:
                raise CollectionBlocked("BOOKS")
            stage = "quota repository access"
            store = quota_store()
            stage = "quota reservation / provider collection"
            snap = Client(
                key,
                store,
                terms_ack=True,
                object_cap=cap,
            ).fetch(
                (kickoff - timedelta(seconds=30)).isoformat(),
                (kickoff + timedelta(seconds=30)).isoformat(),
                books=books,
                limit=16,
            )
            st.session_state["market_snapshot"] = snap
        except (Unavailable, ValueError, OSError, KeyError, TypeError) as error:
            code, message = safe_diagnostic(error)
            # Never log exception objects, tracebacks, response bodies, headers or URLs.
            logging.getLogger(__name__).warning(
                "Research collection blocked: code=%s stage=%s", code, stage
            )
            st.warning(
                f"Collection blocked [{code}] at {stage}: {message} No production change."
            )
    # Network/CAS work can take seconds: validate captures against time AFTER collection.
    now = datetime.now(UTC)
    snap = st.session_state.get("market_snapshot")
    if not snap:
        return
    st.caption(
        f"Retrieved {snap['retrieved_at']} · Provider: SportsGameOdds · {snap['account_tier']}"
    )
    if snap.get("provider_notice"):
        st.caption(snap["provider_notice"])
    if snap.get("truncated"):
        st.caption(
            "Provider supplied a continuation cursor; additional coverage may exist. No automatic pagination."
        )
    scoped = {
        **snap,
        "events": [
            {
                **e,
                "odds": {
                    k: {
                        **o,
                        "byBookmaker": {
                            b: q
                            for b, q in o.get("byBookmaker", {}).items()
                            if b in books
                        },
                    }
                    for k, o in e.get("odds", {}).items()
                },
            }
            for e in snap["events"]
        ],
    }
    rows, issues = benchmarks(scoped, selected, release, now)
    rows = [r for r in rows if r["game_id"] == gid]
    market = st.selectbox("Market", ["All"] + sorted({r["market"] for r in rows}))
    query = st.text_input("Player contains").casefold()
    try:
        fixture = next(
            (f for f in load(DEFAULT, release)["fixtures"] if f["game_id"] == gid), None
        )
    except (OSError, ValueError, KeyError, TypeError):
        fixture = None
    visible = [
        r
        for r in rows
        if (market == "All" or r["market"] == market)
        and query in r["player"].casefold()
    ]
    st.write(
        f"{len(visible)} comparable player markets; {len(issues)} excluded source records."
    )
    if not rows:
        st.warning(
            "No fresh, matched, paired primary lines for this fixture. Coverage, identity, scenario-only forecasts or timing may prevent comparison. Missing odds are not substituted."
        )
    for r in visible:
        with st.container(border=True):
            st.markdown(f"**{r['player']} · {r['market']}**")
            st.write(
                f"Stage 1A: {r['projection']:.2f} · {r['label']}: {r['median_line']:.2f} · {r['book_count']} books"
            )
            pct = (
                "undefined (zero line)"
                if r["percentage_difference"] is None
                else f"{r['percentage_difference']:+.1f}%"
            )
            st.write(
                f"Model − market: {r['difference']:+.2f} ({pct}); absolute gap {r['absolute_difference']:.2f}"
            )
            for book, item in r["books"].items():
                st.write(f"{book}: main line {item['line']:g}")
                for q in item["quotes"]:
                    st.caption(
                        f"{q['side']} decimal {q['decimal_odds']:.3f} · {q['odd_id']} · updated {q['provider_updated_at']}"
                    )
            st.caption(
                f"Oldest quote {r['oldest_update']} · captured {r['retrieved_at']} · all included quotes ≤15 minutes old"
            )
            if r["substantial_disagreement"]:
                st.warning(
                    "Large disagreement: ≥20% descriptive review flag, not a validated edge."
                )
            with st.expander("Investigate disagreement"):
                st.write(
                    "Possible causes to check: recent role/usage changes, incomplete player history, normal-model limitations, scenario forecasts and bookmaker definitions. No cause is established solely by disagreement."
                )
                if fixture:
                    st.caption(
                        f"Frozen game-script evidence: {fixture['effective_history_cutoff']}. Open Game-Script Intelligence for this fixture; measured proxies and hypotheses remain separate."
                    )
                    for a in fixture["assessments"]:
                        v = a["offensive_volume"]
                        st.write(
                            f"{a['offense']}: recent {v['games']} games, plays/game {v.get('plays_per_game')}, dropbacks/game {v.get('dropbacks_per_game')}. Historical environment, not today's predicted volume."
                        )
                if fixture:
                    for assessment in fixture["assessments"]:
                        for person in assessment.get(
                            "quarterbacks", []
                        ) + assessment.get("receivers", []):
                            if person.get("player_id") == r["player_id"]:
                                st.write(
                                    f"Player-specific frozen evidence: {person.get('player', r['player'])}"
                                )
                                if person.get("statistics"):
                                    st.json(person["statistics"], expanded=False)
                                if person.get("interpretation"):
                                    st.write(
                                        "Conditional interpretation (not an established cause of the market gap):"
                                    )
                                    st.write(person["interpretation"])
                st.caption(
                    "No automatic projection adjustment, betting selection, ledger write or settlement."
                )
