"""Current certified weekly inputs and existing research selections; no data collection."""

import json
from datetime import UTC, datetime

import streamlit as st

from weekly_learning.store import ROOT

from .enhanced_engine import eligible_rows, select
from .enhanced_ui import calculator, card, fixture_status
from .weekly_serving import RELEASE


def render(frame, fixtures, release):
    now = datetime.now(UTC)
    if release.get("preview_only"):
        st.warning(
            "CANDIDATE PREVIEW ONLY — not selected or activated. No quoted selections can be frozen here."
        )

    def current_admitted():
        if release.get("preview_only"):
            raise ValueError("Unselected preview cannot freeze selections")
        from .weekly_serving import selected

        active = selected()
        if active is None or active[2]["release_id"] != release["release_id"]:
            raise ValueError("Release is no longer selected")
        from weekly_learning.availability import filter_frame

        return filter_frame(eligible_rows(active[0], datetime.now(UTC)))[0]

    st.markdown(f"## Week {release['fixture_slate']['week']} · NFL research selections")
    st.caption(
        "Serving profile: "
        + release["serving_runtime_profile"]
        + " · Release: "
        + release["release_id"]
    )
    st.warning(
        "Research probabilities are conditional on offensive participation. Injury/inactive status is unverified; no player is labelled injury-cleared. Roof-only games cannot be priced or selected."
    )
    st.caption(
        f"{len(frame)} complete frozen-model inputs · {frame.game_id.nunique()} complete fixtures · {len(fixtures) - frame.game_id.nunique()} roof-only fixtures · No bookmaker prices are assumed."
    )
    section = st.selectbox(
        "Workspace",
        [
            "Top Picks",
            "Top 2 by Game",
            "Accumulator Candidate Pool",
            "Player Intelligence",
            "Game Intelligence",
            "Market Intelligence",
            "Model Performance",
            "Weekly Learning",
            "Data & Safety",
        ],
    )
    live = eligible_rows(frame, now)
    from weekly_learning.availability import filter_frame

    try:
        ranked_frame, availability = filter_frame(frame, now=now)
        live = filter_frame(live, now=now)[0]
    except ValueError:
        ranked_frame = frame.iloc[:0]
        live = live.iloc[:0]
        availability = {"status": "integrity failure; pricing withheld", "withheld": []}
    st.caption(
        "Availability: "
        + availability["status"]
        + f" · withheld players: {len(availability['withheld'])}. Unlisted players are not injury-cleared."
    )
    if section in ["Top Picks", "Top 2 by Game"]:
        from selection_learning.ui import render as quoted

        quoted(
            ranked_frame,
            fixtures,
            release,
            "top" if section == "Top Picks" else "games",
            admitted_current=current_admitted,
        )
        st.markdown("### Model-only research · not quoted betting selections")
        top, two = select(ranked_frame)
        if section == "Top Picks":
            for row in top.to_dict("records"):
                st.caption(fixture_status(row["kickoff_at"], now))
                card(row)
        else:
            for game in fixtures.itertuples():
                st.markdown(f"### {game.away_team} at {game.home_team}")
                st.caption(fixture_status(game.kickoff_at, now))
                picks = two[two.game_id.eq(game.game_id)]
                if picks.empty:
                    st.info(game.coverage_status)
                for row in picks.to_dict("records"):
                    card(row)
        if (
            section == "Top 2 by Game"
            and release["fixture_slate"]["week"] == 12
            and release["release_id"] != RELEASE.name
        ):
            with st.expander(
                "Earlier Week 12 fixtures — historical pre-kickoff research only",
                expanded=True,
            ):
                from .weekly_serving import admit as archive_admit

                archive, old_games, _ = archive_admit()
                _, old_two = select(archive)
                for game in old_games[
                    ~old_games.game_id.isin(fixtures.game_id)
                ].itertuples():
                    st.markdown(f"### {game.away_team} at {game.home_team}")
                    st.caption(
                        "HISTORICAL ONLY — original 24 November frozen research; no new quotes, freezing or betting eligibility."
                    )
                    picks = old_two[old_two.game_id.eq(game.game_id)]
                    if picks.empty:
                        st.info(game.coverage_status)
                    for row in picks.to_dict("records"):
                        card(row)
    elif section == "Accumulator Candidate Pool":
        from selection_learning.engine import eligible_quotes, ticket

        journal = st.session_state.get("line_journal", {"events": []})
        records = [
            r
            for e in journal["events"]
            if e["kind"] == "freeze"
            and e["payload"]["release_id"] == release["release_id"]
            for r in e["payload"]["records"]
        ]
        allowed = set(zip(live.game_id, live.player_id, live.market, strict=True))
        pool = {
            r["quote_id"]: r
            for r in eligible_quotes(records)
            if (r["game_id"], r["player_id"], r["market"]) in allowed
        }
        st.info(
            "Choose any subset of eligible frozen quoted legs, including explicitly identified alternate lines. No ticket is forced. Cross-player joint probabilities and EV are withheld; exact same-stat threshold intersections are identified separately."
        )
        ids = st.multiselect(
            "Candidate legs",
            list(pool),
            format_func=lambda k: (
                f"{pool[k]['player']} · {pool[k]['game_id']} · {pool[k]['side']} {pool[k]['line']} {pool[k]['market']}"
            ),
        )
        offered = st.number_input(
            "Genuine offered combined decimal price (optional)",
            min_value=1.01,
            value=None,
        )
        source = st.text_input("Combined-price source (optional)")
        quoted_at = st.text_input("Combined-price observed at (ISO UTC, optional)")
        confirmed = st.checkbox(
            "I verified this exact combined ticket and price with the bookmaker"
        )
        if ids:
            legs = [pool[i] for i in ids]
            proof = None
            if offered and source and quoted_at and confirmed:
                proof = {
                    "decimal_odds": offered,
                    "source": source,
                    "quoted_at": quoted_at,
                    "bookmaker": legs[0]["bookmaker"],
                    "confirmed_available": True,
                }
            try:
                st.json(ticket(legs, offered, ticket_quote=proof))
            except (ValueError, KeyError, TypeError):
                st.warning(
                    "The combined-price evidence is incomplete, stale or incompatible with these legs; no ticket EV is available."
                )
        if not pool:
            st.caption(
                "No eligible frozen genuine quotes recorded. Enter actual quotes in Top Picks first."
            )
    elif section == "Player Intelligence":
        if not live.empty:
            calculator(live, "weekly_player")
        else:
            st.info("No current pre-cutoff forecasts eligible for pricing.")
        st.dataframe(
            frame[
                [
                    "player",
                    "team",
                    "opponent",
                    "market",
                    "baseline",
                    "enhanced_projection",
                    "q05",
                    "q95",
                ]
            ],
            hide_index=True,
        )
    elif section == "Market Intelligence":
        st.caption(
            "Manual/bulk genuine quotes only. No provider collection is activated."
        )
        from selection_learning.ui import render as quoted

        quoted(
            ranked_frame,
            fixtures,
            release,
            "top",
            admitted_current=current_admitted,
        )
    elif section == "Model Performance":
        from .enhanced_ui import point_metrics

        st.dataframe(point_metrics(), hide_index=True)
        st.info(
            "Previously inspected retrospective evidence; no new methods promoted, no historical bookmaker profitability established."
        )
    elif section == "Game Intelligence":
        st.json(
            json.loads(
                (ROOT / release["selection_manifest_path"])
                .with_name("game_script.json")
                .read_text()
            )
        )
    elif section == "Weekly Learning":
        from weekly_learning.ui import render as weekly_learning

        weekly_learning()
    else:
        st.json(
            {
                "release": release["release_id"],
                "prediction_at": release["prediction_at"],
                "feature_cutoff": release["feature_data_cutoff"],
                "forecasts_unchanged": True,
                "probabilities": "existing frozen research policy; no new methods promoted",
                "roof_only": [
                    r.game_id
                    for r in fixtures.itertuples()
                    if r.game_id not in set(frame.game_id)
                ],
            }
        )
