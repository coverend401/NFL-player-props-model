"""Minimal manual/bulk proposition entry in the existing selection workspaces."""

import io
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from research_access import secret

from .engine import REQUIRED, dependency, evaluate, rankings, ticket
from .settlement import freeze, performance
from .store import GitHubJournal


def backend():
    return GitHubJournal(
        secret("NFL_SELECTION_GITHUB_REPOSITORY"),
        secret("NFL_SELECTION_GITHUB_TOKEN"),
        week=st.session_state.get("line_week"),
    )


def render(frame, fixtures, release, mode, *, admitted_current=None):
    scope = release.get("fixture_slate", {})
    week = f"{scope['season']}-{scope['week']:02d}" if scope else None
    if st.session_state.get("line_week") != week:
        for key in ["line_journal", "line_draft", "line_initial_read_attempted"]:
            st.session_state.pop(key, None)
        st.session_state["line_week"] = week
    st.markdown(
        "#### Quoted propositions — "
        + ("Top Picks" if mode == "top" else "Top 2 per Game")
    )
    st.caption(
        "Actual quotes are separate from forecasts. Ranking prioritises supported hit probability, then forecast uncertainty and workload stability; estimated EV is shown separately. WATCH means research only, not an approved bet."
    )
    from research_platform import enhanced_engine as engine

    live = engine.eligible_rows(frame, datetime.now(UTC))
    durable = bool(
        not release.get("preview_only", False)
        and secret("NFL_SELECTION_GITHUB_REPOSITORY")
        and secret("NFL_SELECTION_GITHUB_TOKEN")
    )
    if release.get("preview_only"):
        st.info(
            "Unselected candidate preview: comparisons are allowed, but private reads and freezing are disabled until owner-approved activation."
        )
    elif not durable:
        st.info(
            "Durable private selection storage is not configured. Quotes may be compared, but no selections are recorded or recommended until immutable storage succeeds. The existing quota repository is never used."
        )
    if st.button(
        "Load private frozen selections", key="line_load_" + mode, disabled=not durable
    ):
        try:
            state, _ = backend().read()
            st.session_state["line_journal"] = state
        except (ValueError, OSError, KeyError, TypeError):
            st.error(
                "Private selection journal unavailable or failed integrity checks. No fallback to ephemeral selection recording."
            )
    if (
        durable
        and "line_journal" not in st.session_state
        and not st.session_state.get("line_initial_read_attempted")
    ):
        st.session_state["line_initial_read_attempted"] = True
        try:
            state, _ = backend().read()
            st.session_state["line_journal"] = state
        except (ValueError, OSError, KeyError, TypeError):
            st.warning(
                "Initial private journal read failed; use Load to retry explicitly. No selections inferred."
            )
    draft = st.session_state.get("line_draft", [])
    state = st.session_state.get("line_journal", {"schema": 1, "events": []})
    frozen = [
        r
        for e in state["events"]
        if e["kind"] == "freeze" and e["payload"]["release_id"] == release["release_id"]
        for r in e["payload"]["records"]
    ]
    allowed = set(zip(live.game_id, live.player_id, live.market, strict=True))
    # New material availability evidence restricts serving, never rewrites frozen decisions.
    visible = [
        r for r in frozen if (r["game_id"], r["player_id"], r["market"]) in allowed
    ]
    top, groups = rankings(visible)
    if mode == "top":
        selected = top
        if not selected:
            st.info(
                "No fresh, frozen and sufficiently supported quoted selections. Forecast-only research follows below; it is not bookmaker value."
            )
        show(selected)
    else:
        for game in fixtures.itertuples():
            st.markdown(
                f"**{game.away_team} at {game.home_team} — quoted propositions**"
            )
            picks = groups.get(game.game_id, [])
            show(picks)
            if len(picks) < 2:
                st.caption(
                    "Fewer than two eligible frozen quotes: missing prices, expired/cutoff-closed quotes, insufficient probability/workload evidence, or documented forecast exclusion. Model-only coverage remains separately visible below."
                )
            if len(picks) == 2:
                st.warning(dependency(*picks))
    with st.expander("Enter or bulk import actual bookmaker quotes; freeze selections"):
        st.caption(
            "Manual quotes only. No bookmaker API calls. CSV columns: "
            + ", ".join(sorted(REQUIRED))
        )
        if live.empty:
            st.info(
                "No admitted upcoming forecasts remain before T−60. Existing historical forecasts cannot be turned into new pregame selections."
            )
        else:
            with st.form("line_quote_" + mode):
                identity = st.selectbox(
                    "Forecast identity",
                    list(live.index),
                    format_func=lambda i: (
                        f"{live.loc[i, 'player']} · {live.loc[i, 'market']} · {live.loc[i, 'game_id']}"
                    ),
                )
                side = st.selectbox("Actual quoted side", ["over", "under"])
                line_type = st.selectbox(
                    "Line definition", ["unspecified", "primary", "alternate"]
                )
                line = st.number_input("Actual line", value=None, step=0.5)
                odds = st.number_input(
                    "Actual decimal odds", value=None, min_value=1.01
                )
                book = st.text_input("Bookmaker")
                source = st.text_input(
                    "Quote source reference (no credentials or private account links)"
                )
                at = st.text_input("Quote observed at (timezone required, ISO 8601)")
                confirmed = st.checkbox(
                    "I observed this available quote and confirmed full-stake push refund with offensive participation required. I authorise private retention of this manual research record."
                )
                submitted = st.form_submit_button("Compare actual quote")
            if submitted:
                try:
                    if not confirmed:
                        raise ValueError("Quote and settlement confirmation required")
                    r = live.loc[identity]
                    raw = {
                        "game_id": r.game_id,
                        "player_id": r.player_id,
                        "market": r.market,
                        "side": side,
                        "line_type": line_type,
                        "line": line,
                        "decimal_odds": odds,
                        "bookmaker": book,
                        "source": source,
                        "quoted_at": at,
                        "settlement_rule": "offensive_participation_full_refund_push",
                    }
                    draft = [*draft, evaluate(raw, live)]
                    st.session_state["line_draft"] = draft
                except (ValueError, TypeError, KeyError, OSError):
                    st.error(
                        "Quote rejected: check actual price, identity, source, timestamp, supported settlement and T−60 eligibility."
                    )
            upload = st.file_uploader(
                "Bulk manual-quote CSV (maximum 100 rows / 64 KiB)",
                type=["csv"],
                key="line_upload_" + mode,
            )
            confirmed_bulk = st.checkbox(
                "All imported quotes were observed and may be privately retained under the stated settlement rules.",
                key="bulk_confirm_" + mode,
            )
            if st.button("Validate bulk quotes", key="bulk_" + mode):
                try:
                    if upload is None or upload.size > 65536 or not confirmed_bulk:
                        raise ValueError("Confirmed bounded CSV required")
                    imported = pd.read_csv(io.BytesIO(upload.getvalue()))
                    if not 1 <= len(imported) <= 100:
                        raise ValueError("Unsupported CSV schema/count")
                    from .imports import compare

                    parsed = compare(imported, live)
                    draft = [*draft, *parsed]
                    st.session_state["line_draft"] = draft
                except (ValueError, TypeError, KeyError, OSError):
                    st.error(
                        "Bulk import rejected atomically; no rows recorded. Check schema, timestamp, identities and supported quote domain."
                    )
        if draft:
            show(draft)
            st.caption(
                "Unfrozen comparisons: not recorded selections. Original probabilities and prices will be frozen without later rewriting."
            )
            if st.button(
                "Freeze quoted research decisions",
                key="line_freeze_" + mode,
                disabled=not durable,
            ):
                try:
                    # Recheck all current integrity/availability evidence at the actual write time.
                    from research_platform.enhanced_engine import DIRECTORY, sha
                    from research_platform.enhanced_ui import current
                    from research_platform.selection_integrity import block_reason

                    if admitted_current is None:
                        if block_reason(release):
                            raise ValueError(
                                "Current forecast integrity review required"
                            )
                        current_live = current(release)[0]
                    else:
                        current_live = admitted_current()
                    refreshed = [evaluate(r, current_live) for r in draft]
                    # An unchanged quote must retain its originally displayed numbers.
                    for old, new in zip(draft, refreshed, strict=True):
                        for key in [
                            "quote_id",
                            "hit_probability",
                            "expected_profit_per_unit",
                            "forecast_sha256",
                        ]:
                            if old.get(key) != new.get(key):
                                raise ValueError(
                                    "Quote probability/forecast changed; compare again"
                                )
                    journal = backend()
                    before, version = journal.read()
                    after = freeze(
                        before,
                        draft,
                        calibration_history=journal.prior_state(),
                        release_id=release["release_id"],
                        forecast_manifest_sha256=sha(
                            __import__("pathlib").Path(__file__).resolve().parents[1]
                            / release["selection_manifest_path"]
                            if admitted_current is not None
                            else DIRECTORY / "manifest.json"
                        ),
                    )
                    journal.write(before, after, version)
                    st.session_state["line_journal"] = after
                    st.session_state["line_draft"] = []
                    st.success(
                        "Frozen decisions persisted and verified in the private journal. Reload the workspace to display them."
                    )
                except (ValueError, OSError, KeyError, TypeError):
                    st.error(
                        "Freeze failed closed: storage conflict, missing private permissions, stale quote or forecast admission failure. No selection success is claimed; reload before retrying."
                    )
    with st.expander("Quoted-selection weekly performance"):
        st.json(performance(state))
        st.caption(
            "Missing outcomes remain pending. Only authorised completed operational results can settle; paper ROI is hypothetical, actual ROI is never inferred. No ranking is automatically promoted."
        )
    with st.expander(
        "Quoted ticket assessment — existing parlay tools remain available"
    ):
        choices = {
            r["quote_id"]: r
            for r in frozen
            if any(
                r["quote_id"] == x["quote_id"]
                for x in top + [leg for pair in groups.values() for leg in pair]
            )
        }
        ids = st.multiselect(
            "Frozen current quoted legs",
            list(choices),
            format_func=lambda i: (
                f"{choices[i]['player']} {choices[i]['side']} {choices[i]['line']} {choices[i]['market']}"
            ),
            key="line_ticket_" + mode,
        )
        quoted_ticket = st.number_input(
            "Actual available combined ticket decimal price (optional)",
            min_value=1.01,
            value=None,
            key="line_ticket_price_" + mode,
        )
        if ids:
            st.json(ticket([choices[i] for i in ids], quoted_ticket))


def show(records):
    for r in records:
        st.write(
            f"**{r.get('player', r['player_id'])} · {r['game_id']} · {r['market']} {r['side']} {r['line']:g} @ {r['decimal_odds']:g} · {r['bookmaker']}**"
        )
        if r.get("hit_probability") is not None:
            st.write(
                f"Research hit probability conditional on participation {r['hit_probability']:.1%} · implied {r['implied_probability']:.1%} · estimated EV {r['expected_profit_per_unit']:+.3f}/unit · {r['status']}"
            )
            st.caption(r["why_pick"] + " Risk: " + r["risk"])
            interval = r.get("outcome_interval90", [])
            if len(interval) == 2 and all(v is not None for v in interval):
                st.caption(
                    f"Research 90% outcome interval: {interval[0]:.1f}–{interval[1]:.1f}; this is not a probability confidence interval."
                )
            band = r.get("probability_band_evidence", {})
            if band.get("player_games") is not None:
                st.caption(
                    f"Probability-band evidence: {band['player_games']} player-games across {band['weeks']} weeks; calibration gap {band['band_gap']:.1%}. Previously inspected research thresholds, not independent bookmaker validation."
                )
        st.caption(
            r["reason"]
            + f" · Quote observed {r['quoted_at']} · expires {r['expires_at']}"
        )
