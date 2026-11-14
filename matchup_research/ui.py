"""Read-only mobile cards for frozen descriptive evidence. No forecasts changed."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from sgo_research.contracts import utc

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "research_inputs/sunday_preview/20261114/fixture_states.json"


def load(path, release):
    path = Path(path)
    raw = path.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != path.with_suffix(".sha256").read_text().strip()
    ):
        raise ValueError("Research snapshot integrity failure")
    state = json.loads(raw)
    if (
        state["schema"] != 1
        or state["release_id"] != release["release_id"]
        or state.get("prediction_adjustments_enabled") is not False
    ):
        raise ValueError("Research/source release mismatch")
    if utc(state["generated_at"]) > datetime.now(UTC):
        raise ValueError("Future research snapshot")
    return state


def pct(value):
    return "unavailable" if value is None else f"{value:.1%}"


def render(release, path=DEFAULT):
    st.subheader("Game-Script Intelligence — descriptive research")
    st.info(
        "Existing Stage 1A forecasts and probabilities are unchanged. Directional notes are conditional football hypotheses, not quantified betting edges."
    )
    try:
        state = load(path, release)
    except (OSError, ValueError, KeyError, TypeError):
        st.warning("No compatible, integrity-verified matchup snapshot is available.")
        return
    fixtures = state["fixtures"]
    if not fixtures:
        st.info("No fixtures in this frozen research window.")
        return
    labels = {
        f[
            "game_id"
        ]: f"{f['away']} at {f['home']} · {utc(f['kickoff_at']).strftime('%a %H:%M')} UK"
        for f in fixtures
    }
    gid = st.selectbox(
        "Fixture", list(labels), format_func=labels.get, key="script_fixture"
    )
    fixture = next(f for f in fixtures if f["game_id"] == gid)
    st.caption(
        f"Generated {state['generated_at']} · T−60 cutoff {fixture['decision_at']} · history observed by {fixture['effective_history_cutoff']}"
    )
    if datetime.now(UTC) > utc(fixture["decision_at"]):
        st.warning(
            "Decision window closed. This is a frozen pregame description, not refreshed betting advice."
        )
    st.caption(state["evidence_class"])
    for a in fixture["assessments"]:
        st.markdown(f"### {a['offense']} offense vs {a['opponent_defense']} defense")
        v = a["offensive_volume"]
        if v["games"]:
            st.write(
                f"Last {v['games']} completed games: {v['plays_per_game']:.1f} plays/game, {v['dropbacks_per_game']:.1f} dropbacks/game; dropback fraction {pct(v['dropback_fraction'])}."
            )
            st.caption(
                f"Neutral clock-gap pace proxy: {v['neutral_clock_gap_seconds'] if v['neutral_clock_gap_seconds'] is not None else 'unavailable'} seconds, {v['neutral_clock_gap_n']} intervals. Recent points for/against: {v['points_for_per_game']:.1f}/{v['points_against_per_game']:.1f}; these are not forecasts or an upcoming total."
            )
        contact = a["opponent_contact_proxy"]
        chart = a["opponent_charting"]
        st.write(
            f"Opponent recorded hit-or-sack contact on {pct(contact['hit_or_sack_rate'])} of {contact['contact_label_n']} labelled dropbacks."
        )
        st.write(
            f"Charted blitzes faced by opponent QBs: {chart['charted_blitzes']} across {chart['charted_passer_games']} passer-games; cross-source frequency proxy {pct(chart['cross_source_blitz_frequency_proxy'])}."
        )
        st.caption(chart["caution"])
        if not a["quarterbacks"]:
            st.warning(
                "No uniquely projected QB with usable baseline identity. Do not infer a starter from this page."
            )
        for q in a["quarterbacks"]:
            with st.container(border=True):
                st.markdown(f"**{q['player']} — individual QB response watch**")
                r = q["statistics"]
                i = q["interpretation"]
                st.write(
                    f"Observed scrambles: {r['scramble_n']}/{r.get('scramble_label_n', r['dropbacks'])} labelled dropbacks ({pct(r['scramble_rate'])}), {q['historical_games']} games. {i['classification']}."
                )
                st.write(
                    f"Median published weekly pressure exposure: {pct(r['median_weekly_charted_pressure_exposure'])} ({r['charted_pressure_games']} charted games). Median weekly NGS average time to throw: {r['median_weekly_average_time_to_throw'] if r['median_weekly_average_time_to_throw'] is not None else 'unavailable'} seconds ({r['NGS_weeks']} weeks)."
                )
                st.markdown("**Directional hypothesis:** " + i["direction"])
                st.write(i["assumption"])
                with st.expander("Player-specific interaction evidence and caveats"):
                    for note in i.get("interaction_notes", []):
                        st.write(note)
                st.caption(i["reason"])
                st.write(
                    "Unchanged baseline: "
                    + ", ".join(
                        f"{k}: {v:.2f} ({q['baseline_statuses'][k]})"
                        for k, v in q["baseline_projections"].items()
                    )
                )
                st.caption(i["protection_caution"])
                st.caption(q["role_caution"])
        st.markdown("**Player-specific short-target candidates from observed usage**")
        ranked = sorted(
            a["receivers"],
            key=lambda r: (r["at_or_behind_LOS_targets"], r["observed_targets"]),
            reverse=True,
        )
        for r in ranked[:3]:
            with st.container(border=True):
                st.markdown(f"**{r['player']} ({r['position']})**")
                st.write(
                    f"{r['observed_targets']:g} covered box targets over {r['observed_games']} observed games; {pct(r['covered_box_target_fraction'])} of covered team targets. PBP targets at/behind LOS: {r['at_or_behind_LOS_targets']}/{r['known_target_air_yards_n']} with known depth."
                )
                st.caption(r["direction"])
                st.write(
                    "Unchanged baseline: "
                    + ", ".join(
                        f"{k}: {v:.2f}" for k, v in r["baseline_projections"].items()
                    )
                )
        if len(ranked) > 3:
            with st.expander("Other observed player usage and baseline projections"):
                for r in ranked[3:]:
                    st.write(
                        f"{r['player']} ({r['position']}): {r['observed_targets']:g} covered targets; {r['at_or_behind_LOS_targets']}/{r['known_target_air_yards_n']} known-depth targets at/behind LOS."
                    )
                    st.caption(
                        "Unchanged baseline: "
                        + ", ".join(
                            f"{k}: {v:.2f}"
                            for k, v in r["baseline_projections"].items()
                        )
                    )
        st.caption(a["target_coverage_caution"])
        with st.expander("Game-script scenarios and missing information"):
            for s in a["game_script_scenarios"]:
                st.write(f"{s['scenario']}: {s['direction']} {s['status']}")
            for missing in a["missing"]:
                st.write("Unavailable: " + missing)
    with st.expander("Sources and interpretation limits"):
        for s in [state["source"]] + state.get("auxiliary_sources", []):
            st.write(s["url"])
            st.caption(
                "Retrieved "
                + s["retrieved_at"]
                + "; original historical publication timing not verified."
            )
        st.write(
            "No coverage scheme, confirmed injury redistribution, exact screen/checkdown rate or pressure-conditioned QB response is inferred from these proxies. Fixed descriptive rules are not fitted or validated forecast adjustments. All nine production markets remain safeguards, with no model changes."
        )
