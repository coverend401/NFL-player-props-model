"""Recommendations-first research screens; certified forecasts remain read-only."""

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.build_slate import MARKETS as LABELS

from . import enhanced_engine as engine


@st.cache_data(show_spinner=False)
def loaded(fingerprint):
    return engine.load()


def current(release):
    p = engine.DIRECTORY / "manifest.json"
    if not p.exists():
        return None
    meta = json.loads(p.read_text())
    if release["release_id"] != meta["parent_release"]:
        return None
    frame, _, _, fixtures, manifest = loaded(
        (p.stat().st_mtime_ns, p.stat().st_size, engine.sha(Path(engine.__file__)))
    )
    frame = engine.eligible_rows(frame, datetime.now(UTC))
    from .selection_integrity import available_rows

    frame = available_rows(frame)
    top, two = engine.select(frame)
    return frame, top, two, fixtures, manifest


@st.cache_data(show_spinner=False)
def point_metrics():
    return pd.read_csv(engine.EXPERIMENT / "point_metrics.csv")


def card(row):
    r = row.to_dict() if hasattr(row, "to_dict") else row
    confidence = (
        "Better-supported research"
        if r["support_tier"] == 2
        else "Point forecast supported; pricing uncertain"
        if r["point_admitted"]
        else "Baseline retained; probability research supported"
        if r["probability_supported"]
        else "Baseline retained; enhancement unproven"
    )
    header = escape(f"{r['player']} — {r['team']} vs {r['opponent']}")
    label = escape(LABELS[r["market"]])
    why = escape(r["why_pick"])
    metrics = point_metrics()
    method = r["point_family"] if r["point_admitted"] else "baseline"
    comparison = metrics[
        metrics.market.eq(r["market"]) & metrics.season.eq(2026)
    ].set_index("method")
    measured = comparison.loc[method]
    risk_text = r["principal_risk"] + " Injury and game-day inactive status unverified."
    if r["point_admitted"] and abs(measured.bias) >= 0.05 * measured.mae:
        unit = (
            "yards"
            if "yards" in r["market"]
            else "catches"
            if r["market"] == "receptions"
            else "carries"
            if "rushing_attempts" in r["market"]
            else "completions"
        )
        risk_text += f" In the 2026 replay, this approach averaged {abs(measured.bias):.1f} {unit} {'below' if measured.bias < 0 else 'above'} actual results."
    risk = escape(risk_text)
    st.markdown(
        f"""<article class="desk-card enhanced-research-card">
<div class="eyebrow">MODEL-ONLY — NO VERIFIED BOOKMAKER VALUE</div>
<h3>{header}</h3><strong>{label}: {r["enhanced_projection"]:.1f}</strong>
<p>Original {r["baseline"]:.1f} · Change {r["projection_change"]:+.1f}</p>
<p><b>Confidence:</b> {escape(confidence)}. Historical error {r["diagnostic_mae"]:.1f}; research 90% range {r["q05"]:.0f}–{r["q95"]:.0f}.</p>
<p><b>Why this pick?</b> {why}</p>
<p><b>Principal risk:</b> {risk}</p></article>""",
        unsafe_allow_html=True,
    )
    with st.expander(f"Detailed model analysis · {r['player']} · {label}"):
        st.write(
            f"Point-error trade-off: RMSE {comparison.loc['baseline', 'rmse']:.2f} → {measured.rmse:.2f}; average forecast minus actual {measured.bias:+.2f}. Lower MAE does not guarantee lower RMSE or unbiased totals."
        )
        st.caption(
            "Enhanced tree projections describe a typical outcome (median-like), not the ceiling or the predictive distribution mean. Pricing uses the whole research distribution where supported."
        )
        st.caption(
            f"2026 inspected diagnostic sample: {int(r['diagnostic_n'])}; MAE gain {r['diagnostic_mae_gain']:+.1%}. No independent final-test or profitability claim."
        )
        st.write(
            f"Season average {r['season_mean']:.1f}; recent three/five {r['last3']:.1f}/{r['last5']:.1f}. Recent offensive snaps {r['recent_snap_share']:.1%}."
        )
        st.caption(
            f"Historical probability-band gap {r['calibration_gap']:.1%}; this is not a player win rate or confidence score. Probabilities: {r['probability_mode']}."
        )
        st.caption(
            f"Forecast recomputed {r['selection_built_at']}; statistics cutoff {r['feature_cutoff']}; roster evidence available {r['eligibility_available_at']}. The certified projection remains unchanged."
        )
        sensitivity = pd.read_csv(engine.DIRECTORY / "sensitivity.csv")
        detail = sensitivity[
            sensitivity.game_id.eq(r["game_id"])
            & sensitivity.player_id.eq(r["player_id"])
            & sensitivity.market.eq(r["market"])
        ]
        if not detail.empty:
            st.dataframe(
                detail[["input_group", "change_vs_training_median_reference"]].round(3),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                "These are model sensitivities to historical reference values, not causal explanations or additional adjustments. No failed game-script multiplier is applied."
            )


def calculator(frame, prefix):
    with st.expander("Player detail & manual bookmaker comparison", expanded=False):
        options = list(frame.index)
        identity = st.selectbox(
            "Player and prop for comparison",
            options,
            format_func=lambda i: (
                f"{frame.loc[i, 'player']} · {LABELS[frame.loc[i, 'market']]} · {frame.loc[i, 'game_id']}"
            ),
            key=prefix + "_player",
        )
        r = frame.loc[identity].to_dict()
        st.write(
            f"Research projection {r['enhanced_projection']:.2f} · original {r['baseline']:.2f}. {r['confidence_label']}."
        )
        st.write(r["why_pick"])
        line = st.number_input(
            "Actual bookmaker line you supply",
            value=None,
            step=0.5,
            key=prefix + "_line",
        )
        odds = st.number_input(
            "Actual decimal price you supply",
            min_value=1.01,
            value=None,
            key=prefix + "_odds",
        )
        side = st.selectbox("Quoted side", ["over", "under"], key=prefix + "_side")
        refund = st.checkbox(
            "I confirmed full-stake refund on an integer-line push",
            key=prefix + "_refund",
        )
        if line is None:
            st.caption(
                "No line or odds are assumed. Enter a genuine quote to compare it with the forecast."
            )
            return
        try:
            p = engine.price(
                r, float(line), float(odds) if odds is not None else None, side, refund
            )
        except (ValueError, TypeError, OverflowError) as error:
            st.info(str(error))
            return
        if p.get("unavailable"):
            st.info(p["unavailable"])
            return
        st.write(
            f"Research probability: Over {p['over']:.1%} · Under {p['under']:.1%} · Push {p['push']:.1%}."
        )
        fair = p["fair_over" if side == "over" else "fair_under"]
        if fair is not None:
            st.write(f"Refund-push fair decimal odds for {side}: {fair:.3f}.")
        if odds is not None:
            st.write(
                f"Quoted break-even conditional probability: {p['break_even_conditional']:.1%}. Estimated research EV per unit: {p['expected_profit_per_unit']:+.3f}."
            )
            st.warning(
                "Estimated EV uses your supplied quote and retrospective research probabilities. Price availability, current participation and profitability are not independently verified. No bet is placed or recorded in the bankroll."
            )


def availability_info():
    from sgo_research.ui import research_key

    if not research_key():
        st.info(
            "No research API key configured. Enhanced forecasts and manual comparison work without provider requests."
        )


def render(release, mode):
    try:
        data = current(release)
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        st.warning(
            "Enhanced selections failed admission or integrity checks; the unchanged certified research view follows."
        )
        return False
    if data is None:
        return False
    frame, top, two, fixtures, manifest = data
    st.markdown(
        "### "
        + (
            "Top Picks"
            if mode == "top"
            else "Top 2 by Game"
            if mode == "games"
            else "Player Intelligence"
        )
    )
    st.markdown(
        "**Enhanced research selections · Sunday 22 November 2026 · NFL Week 11**"
    )
    st.caption(
        "The verified schedule labels this date Week 11. Week 12 starts on 26 November; no games or sealed outcomes are relabelled."
    )
    st.caption(
        f"Eligible: {frame.game_id.nunique()} · Scheduled Sunday: {int(fixtures.gameday.astype(str).eq('2026-11-22').sum())} · Forecasts: {len(frame)} · Enhanced research Top 2: {len(two)}. Certified production rankings are unchanged."
    )
    st.info(
        "Research confidence describes historical forecast reliability, not betting value. Forecasts assume offensive participation; no inactivity probability is invented. No bookmaker prices are assumed. Roster evidence is dated 20 November; live injuries/inactives and route/coverage data remain unverified. The Week 11 outcome seal remains closed."
    )
    if frame.empty:
        st.warning(
            "No admitted selections remain before T−60. Expired forecasts are not current betting opportunities."
        )
        with st.expander("Data availability", expanded=False):
            availability_info()
        return True
    if mode == "top":
        for _, r in top.iterrows():
            card(r)
    elif mode == "games":
        sunday = fixtures[fixtures.gameday.astype(str).eq("2026-11-22")]
        for f in sunday.sort_values("kickoff_at").itertuples():
            if pd.Timestamp(f.kickoff_at) <= pd.Timestamp(
                datetime.now(UTC)
            ) + pd.Timedelta(minutes=60):
                continue
            st.markdown(f"#### {f.away_team} at {f.home_team}")
            picks = two[two.game_id.eq(f.game_id)]
            if picks.empty:
                st.info(
                    f.coverage_status + ". No unsupported second selection is forced."
                )
                continue
            for _, r in picks.iterrows():
                card(r)
            if len(picks) == 2:
                same = picks.team.nunique() == 1
                st.caption(
                    "Correlation: "
                    + (
                        "these teammates share offensive volume and may compete for touches/targets."
                        if same
                        else "these opponents share the same game pace and score; they are not independent legs."
                    )
                    + " No validated joint probability or parlay EV."
                )
    else:
        st.dataframe(
            frame[
                [
                    "player",
                    "team",
                    "opponent",
                    "market",
                    "baseline",
                    "enhanced_projection",
                    "projection_change",
                    "confidence_label",
                ]
            ].round(2),
            hide_index=True,
            width="stretch",
        )
    calculator(frame, "enhanced_" + mode)
    with st.expander("Research ordering, evidence and exclusions"):
        availability_info()
        st.json(manifest["policy"], expanded=False)
        st.caption(
            "2025 fixed method selection; previously inspected 2026 Weeks 1–10 diagnostics. Closing implied totals in the inherited champion benchmark have unverified T−60 timing. No independent final-period or betting-profit claim."
        )
        st.dataframe(
            fixtures[["game_id", "coverage_status", "research_candidates"]],
            hide_index=True,
            width="stretch",
        )
    return True
