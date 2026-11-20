"""Presentation-only football summaries, drawn from existing recorded evidence."""

import math

import streamlit as st

from .engine import player_evidence
from .r7 import opponent_note
from .ui import esc, game_label


def number(value):
    try:
        return float(value) if math.isfinite(float(value)) else None
    except (TypeError, ValueError):
        return None


def explanation(row, state):
    assessment = None
    person = None
    for fixture in (state or {}).get("fixtures", []):
        if fixture["game_id"] != row["game_id"]:
            continue
        for a in fixture["assessments"]:
            if a.get("offense") == row.get("team"):
                assessment = a
                person = next(
                    (
                        p
                        for p in a.get("quarterbacks", []) + a.get("receivers", [])
                        if p.get("player_id") == row["player_id"]
                    ),
                    None,
                )
                break
    market = row["market"]
    receiving = market in ["Receiving Yards", "Receptions"]
    rushing = "Rushing" in market
    targets = number((person or {}).get("observed_targets"))
    games = number((person or {}).get("observed_games"))
    stats = (person or {}).get("statistics", {})
    scrambles = number(stats.get("scramble_n"))
    dropbacks = number(stats.get("scramble_label_n", stats.get("dropbacks")))
    if receiving and targets is not None and games is not None and games > 0:
        player = f"In {games:g} recorded games, {row['player']} drew {targets:g} targets; his routes and playing time today still need checking."
    elif rushing and scrambles is not None and dropbacks is not None and dropbacks > 0:
        player = f"He scrambled {scrambles:g} times on {dropbacks:g} recorded dropbacks, showing how often he has taken off when passing plays break down."
    elif (
        not receiving
        and not rushing
        and number(stats.get("dropbacks")) is not None
        and number((person or {}).get("historical_games"))
    ):
        player = f"He logged {stats['dropbacks']:g} dropbacks across {person['historical_games']:g} recorded games; today's pass protection and playing time still need checking."
    else:
        workload = (
            "carry totals"
            if rushing
            else "target totals"
            if receiving
            else "passing workload details"
        )
        player = f"Recent {workload} aren't available in this view, so {row['player']}'s expected playing time needs checking."
    opponent = (assessment or {}).get("opponent_defense", "the opposing defence")
    contact = (assessment or {}).get("opponent_contact_proxy", {})
    rate, count = (
        number(contact.get("hit_or_sack_rate")),
        number(contact.get("contact_label_n")),
    )
    if (
        not rushing
        and rate is not None
        and count is not None
        and count > 0
        and 0 <= rate <= 1
    ):
        matchup = f"{opponent} hit or sacked the quarterback on {rate:.1%} of {count:g} recorded dropbacks; coverage and today's personnel remain unclear."
    else:
        area = "run defence" if rushing else "coverage"
        matchup = f"We lack verified {area} and personnel details for {opponent}, so there's no established matchup advantage."
    projection = f"{row['projection']:.1f} {market.lower()}"
    if row.get("bookmaker") is None:
        prop = f"The forecast is {projection}; without a verified bookmaker line, this is a player to research rather than a betting-value claim."
    else:
        gap = row["projection"] - row["line"]
        comparison = (
            f"{abs(gap):.1f} {'above' if gap > 0 else 'below'}" if gap else "level with"
        )
        caution = (
            "PASS means no bet recommendation"
            if row["classification"] == "PASS"
            else "WATCH means further checks, not a ready-to-bet pick"
        )
        against = (row["side"] == "Over" and gap < 0) or (
            row["side"] == "Under" and gap > 0
        )
        prop = (
            f"The forecast is {projection}, {comparison} {row['bookmaker']}'s {row['line']:g} line; {row['side']} runs against that forecast and {caution}."
            if against
            else f"The forecast is {projection}, {comparison} {row['bookmaker']}'s {row['line']:g} line; {caution}."
        )
    return f"{player} {matchup} {prop}"


def technical(row, release, state):
    evidence = player_evidence(state, row["player_id"], row["game_id"])
    with st.expander(
        f"Detailed model analysis · {row['player']} / {row.get('market')} / {row.get('side') or 'model only'}"
    ):
        st.markdown("**Recorded evidence**")
        for text in evidence["facts"]:
            st.write(text)
        st.write(opponent_note(state, row["player_id"], row["game_id"]))
        st.markdown("**Football interpretations — not forecast adjustments**")
        for text in evidence["hypotheses"]:
            st.write(text)
        for text in evidence["missing"] + row.get("reasons", []):
            st.caption(text)
        if row.get("bookmaker") is None:
            st.write(
                f"Projection rank {int(row['production_rank'])} of {int(row['market_population'])} in this market; production rank is not betting value."
            )
            st.caption(
                f"Residual scale {row.get('resid_std', float('nan')):.2f}; not a calibrated prediction interval. Forecast {row['prediction_at']}."
            )
        else:
            st.write(
                f"Exact quote: {row['bookmaker']} {row['side']} {row['line']:g} at {row['decimal_odds']:.3f}. Median line {row['median_line']:g} from {row['book_count']} books; not an offered price."
            )
            st.write(
                f"Implied probability {row['implied_probability']:.1%}; paired no-vig {row['no_vig_probability']:.1%}. The existing Stage 1A probability method and calibration limitations are unchanged."
            )
            if row["ev_pct"] is not None:
                st.write(
                    f"EV / £1 = p × decimal − 1 = {row['ev_pct'] / 100:+.4f}; projection-shift sensitivity {row['stress_ev_min']:+.1f}% to {row['stress_ev_max']:+.1f}% for ±1 residual scale, not a confidence interval."
                )
            st.caption(
                f"Captured {row['retrieved_at']} · forecast {row['forecast_at']} · source {row['source_odd_id']}."
            )
        st.caption(
            f"Research release {release['release_id']}. Injury/inactive confirmation, routes and validated game-script adjustments are unavailable here."
        )


def model_card(row, release, state):
    st.markdown(
        f"""<article class="desk-card"><div class="small">{esc(game_label(row["game_id"], release))}</div><h3>{esc(row["player"])}</h3><span class="desk-pill">MODEL ONLY</span><div class="desk-line">{esc(row["market"])} · forecast {row["projection"]:.1f}</div><p class="desk-note"><b>Why this pick?</b><br>{esc(explanation(row, state))}</p><div class="desk-risk">MODEL-ONLY — NO VERIFIED BOOKMAKER VALUE. No line, odds or EV is supplied.</div></article>""",
        unsafe_allow_html=True,
    )
    technical(row, release, state)


def market_card(row, release, state):
    prob = (
        "Unavailable"
        if row["model_probability"] is None
        else f"{row['model_probability']:.1%}"
    )
    ev = "Unavailable" if row["ev_pct"] is None else f"{row['ev_pct']:+.1f}%"
    kind = "watch" if row["classification"] == "WATCH" else "pass"
    st.markdown(
        f"""<article class="desk-card {kind}"><div class="small">{esc(game_label(row["game_id"], release))}</div><h3>{esc(row["player"])}</h3><span class="desk-pill {kind}">{esc(row["classification"])} · EXPERIMENTAL</span><div class="desk-line">{esc(row["side"])} {row["line"]:g} · {esc(row["market"])}</div><div class="small">{esc(row["bookmaker"].upper())} · {row["decimal_odds"]:.3f} decimal · US benchmark</div><div class="desk-grid"><div><b>{row["projection"]:.1f}</b><span>MODEL FORECAST</span></div><div><b>{prob}</b><span>MODEL CHANCE</span></div><div><b>{ev}</b><span>ESTIMATED EV / £1</span></div></div><p class="desk-note"><b>Why this pick?</b><br>{esc(explanation(row, state))}</p><div class="desk-risk">Playing time, fitness, price availability and UK betting access still need checking. Research only.</div><div class="small">Updated {esc(row["oldest_update"])} · expires {esc(row["valid_until"])}</div></article>""",
        unsafe_allow_html=True,
    )
    technical(row, release, state)
