"""iPhone-first integrated research desk for the existing authenticated app."""

import html
from datetime import UTC, datetime

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from scipy.stats import norm

from matchup_research.ui import DEFAULT
from matchup_research.ui import load as load_matchups
from matchup_research.ui import render as render_games
from sgo_research.contracts import STAT_MARKETS, utc
from sgo_research.market_ui import render as render_collection

from .engine import evaluate, player_evidence, retain_snapshots
from .performance import load as load_performance

CSS = """<style>
.stApp{background:#080f1d;color:#e8edf7;font-family:Inter,system-ui,-apple-system,sans-serif}
[data-testid="stHeader"]{background:#080f1dee}
[data-testid="stMainBlockContainer"]{max-width:1050px;padding-top:1.1rem;padding-bottom:3rem}
h1,h2,h3,p,label,[data-testid="stMarkdownContainer"]{color:inherit}
[data-testid="stVerticalBlockBorderWrapper"]{background:#111b2d;border-color:#26344c!important;border-radius:18px}
[data-baseweb="select"]>div,input{background-color:#17243b!important;color:#f0f4fa!important}
[data-testid="stWidgetLabel"] p{color:#aab8ce;font-size:.9rem}
[data-testid="stAlert"]>div{background:#17243b;color:#d7e2f2}
[data-testid="stAlert"] p{color:#d7e2f2}
[data-baseweb="select"] div,[role="listbox"]{background-color:#17243b;color:#f0f4fa}
button{min-height:44px!important;border-radius:12px!important}
[data-testid="stExpander"]{border-color:#26344c;border-radius:14px}
[data-testid="stExpander"] summary{color:#cbd5e1}
[data-testid="stCaptionContainer"]{color:#a5b4cc}
.desk-hero{padding:17px 20px;background:linear-gradient(120deg,#152946,#101928);border:1px solid #29405f;border-radius:22px;margin-bottom:18px}
.desk-eyebrow{font-size:11px;color:#87a8cf;letter-spacing:2px;font-weight:750}
.desk-title{font-size:clamp(25px,6vw,36px);line-height:1.1;font-weight:800;margin:7px 0}
.desk-sub{color:#b6c6db;font-size:14px;line-height:1.6}
.desk-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:14px 0}
.desk-stat{background:#101c30;border:1px solid #283852;border-radius:13px;padding:10px 9px;min-width:0}
.desk-stat b{display:block;font-size:24px;color:#eef4fc}.desk-stat span{font-size:11px;color:#a5b4cc}
.desk-card{background:#111c2f;border:1px solid #2a3b56;border-left:4px solid #64748b;border-radius:17px;padding:18px;margin:15px 0 8px;overflow-wrap:anywhere}
.desk-card.watch{border-left-color:#e5ad42}.desk-card.pass{border-left-color:#aa6574}
.desk-card h3{font-size:22px;margin:8px 0 6px}.desk-card .small{font-size:12px;color:#afbed2;line-height:1.5}
.desk-pill{display:inline-block;border-radius:6px;padding:4px 8px;font-size:10px;font-weight:800;letter-spacing:1px;background:#26344a;color:#d3deee}
.desk-pill.watch{background:#44351b;color:#f6d18c}.desk-pill.pass{background:#38232e;color:#efaebd}
.desk-line{font-size:17px;color:#edf3fb;margin:8px 0}.desk-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:14px 0}
.desk-grid b{display:block;font-size:19px;line-height:1.5}.desk-grid span{font-size:11px;color:#a5b4cc}
.desk-bar{height:6px;background:#293750;border-radius:4px;margin:6px 0 12px;overflow:hidden}.desk-bar i{display:block;height:100%;background:#d6a54c}
.desk-note{font-size:13px;line-height:1.65;color:#c1cee0}.desk-risk{font-size:12px;line-height:1.6;color:#e0b4bd}
@media(max-width:480px){[data-testid="stMainBlockContainer"]{padding-left:14px;padding-right:14px}.desk-card{padding:15px}.desk-hero{padding:16px 17px}.desk-grid b{font-size:17px}}
</style>"""


def esc(value):
    return html.escape(str(value), quote=True)


def pct(value):
    return "Unavailable" if value is None else f"{value:.1%}"


def game_label(gid, release):
    bits = gid.split("_")
    when = release["game_kickoffs"].get(gid)
    return (
        f"{bits[-2]} at {bits[-1]} · {utc(when).strftime('%a %H:%M')} UK"
        if when
        else gid
    )


def state_for(release):
    try:
        return load_matchups(DEFAULT, release)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def current_decisions(slate, release):
    now = datetime.now(UTC)
    snapshots = st.session_state.get("intelligence_snapshots", [])
    latest = st.session_state.get("market_snapshot")
    if latest:
        snapshots = retain_snapshots(snapshots, latest, now)
    else:
        # Prune even when there is no latest capture.
        snapshots = [
            s
            for s in snapshots
            if 0 <= (now - utc(s["retrieved_at"])).total_seconds() <= 900
        ]
    st.session_state["intelligence_snapshots"] = snapshots
    if latest and (now - utc(latest["retrieved_at"])).total_seconds() > 900:
        st.session_state.pop("market_snapshot", None)
    return evaluate(snapshots, slate, release, now)


def card(row, release, state, detail=True):
    evidence = player_evidence(state, row["player_id"], row["game_id"])
    prob = pct(row["model_probability"])
    ev = "Unavailable" if row["ev_pct"] is None else f"{row['ev_pct']:+.1f}%"
    cls = row["classification"].lower()
    st.markdown(
        f"""<article class="desk-card {cls}">
<div class="small">{esc(game_label(row["game_id"], release))} · {esc(row["team"])}</div>
<h3>{esc(row["player"])}</h3><span class="desk-pill {cls}">{esc(row["classification"])}</span> <span class="desk-pill">EXPERIMENTAL</span>
<div class="desk-line">{esc(row["side"])} {row["line"]:g} · {esc(row["market"])}</div>
<div class="small">{esc(row["bookmaker"].upper())} · {row["decimal_odds"]:.3f} decimal · {esc(row["fractional_odds"])} fractional · US benchmark</div>
<div class="desk-grid"><div><b>{row["projection"]:.1f}</b><span>STAGE 1A FORECAST</span></div><div><b>{prob}</b><span>MODEL ESTIMATE</span></div><div><b>{ev}</b><span>ESTIMATED EV / £1</span></div></div>
<div class="small">{row["book_count"]} contributing book(s) · {"single-book benchmark" if row["book_count"] == 1 else "market median"} {row["median_line"]:g} · model gap {row["market_difference"]:+.1f}</div>
<p class="desk-note">{esc(row["reasons"][0])}</p>
<p class="desk-note">Observed context: {esc(evidence["facts"][-1] if evidence["facts"] else "Player-specific recent context unavailable; do not assume zero usage.")}</p>
<div class="desk-risk">Primary risks: unvalidated probability calibration; current inactive/role status and UK availability unverified.</div>
<div class="small">Oldest paired price {row["age_seconds"] / 60:.1f} min old · T−60 enforced · {esc(row["matching_confidence"].replace("_", " "))}</div></article>""",
        unsafe_allow_html=True,
    )
    if not detail:
        return
    with st.expander(
        f"Evidence, pricing & risks · {row['player']} / {row['bookmaker']} / {row['side']}"
    ):
        st.markdown("**Exact-line pricing**")
        st.write(
            f"Raw implied {row['implied_probability']:.1%} · price-normalised no-vig {row['no_vig_probability']:.1%} · paired overround {row['overround_pct']:.2f}%"
        )
        if row["model_probability"] is not None:
            st.write(
                f"Model minus no-vig probability: {100 * row['probability_gap']:+.2f} percentage points. Fair decimal estimate: {row['fair_decimal']:.3f}."
                if row["fair_decimal"] is not None
                else "Fair odds unavailable."
            )
            st.caption(
                "No-vig removes the paired quoted margin proportionally; it is not a forecast of the true probability. Prices are compared only at the same book and exact line."
            )
            st.write(
                f"EV per £1 = ({row['model_probability']:.5f} × {row['decimal_odds']:.5f}) − 1 = {row['ev_pct'] / 100:+.4f}. No stake is recommended."
            )
            st.caption(
                f"Projection-shift stress test ±1 residual scale: estimated EV {row['stress_ev_min']:+.1f}% to {row['stress_ev_max']:+.1f}%. This is an illustrative sensitivity range, not a confidence interval or validated forecast distribution."
            )
        else:
            st.caption(
                "Push-aware settlement probability is unsupported at this line; EV selection is blocked."
            )
        st.markdown("**Measured player / game context**")
        for fact in evidence["facts"]:
            st.write(fact)
        if not evidence["facts"]:
            st.write(
                "No player-specific recent evidence available; missing does not mean zero usage."
            )
        st.markdown("**Unquantified football hypotheses**")
        for note in evidence["hypotheses"]:
            st.write(note)
        st.caption(
            "Context is not a causal explanation of the market gap and does not change projection, probability or ranking."
        )
        st.markdown("**Why this is not a BET recommendation**")
        for reason in row["reasons"][1:] + evidence["missing"]:
            st.write("• " + reason)
        st.caption(
            f"Book updated {row['oldest_update']} · retrieved {row['retrieved_at']} · forecast {row['forecast_at']} · kickoff {row['kickoff_at']}"
        )
        st.caption(
            f"Exact definition: {row['source_odd_id']} · primary scope verified: {row['primary_scope_verified']} · raw primary flag: {row['raw_main_line_flag']}"
        )
        st.caption(
            f"Release {row['release_id']} · policy {row['policy_id']}. No bet settlement, live bankroll or outcome access."
        )


def filters(rows, *, deduplicate=True):
    with st.expander("Filter your research", expanded=False):
        games = st.multiselect("Fixtures", sorted({r["game_id"] for r in rows}))
        markets = st.multiselect("Prop markets", sorted({r["market"] for r in rows}))
        teams = st.multiselect("Teams", sorted({r["team"] for r in rows}))
        classes = st.multiselect("Classification", ["WATCH", "PASS"], default=["WATCH"])
        books = st.multiselect("Bookmakers", sorted({r["bookmaker"] for r in rows}))
        query = st.text_input("Player name").casefold()
        limit = st.select_slider("Cards per page", options=[5, 10, 20, 40], value=10)
    selected = [
        r
        for r in rows
        if (not games or r["game_id"] in games)
        and (not markets or r["market"] in markets)
        and (not teams or r["team"] in teams)
        and r["classification"] in classes
        and (not books or r["bookmaker"] in books)
        and query in r["player"].casefold()
    ]
    # Avoid filling the landing screen with multiple quotes of the same selection.
    unique = {}
    for r in selected:
        key = (r["game_id"], r["player_id"], r["market"], r["side"])
        if key not in unique:
            unique[key] = r
    return (list(unique.values()) if deduplicate else selected), limit, len(selected)


def top_picks(slate, release):
    st.markdown("### Top Picks")
    st.caption("US benchmarks · not confirmed Northern Ireland betting availability")
    st.caption(
        f"View generated {datetime.now(UTC).strftime('%H:%M:%S')} UK. No background polling; refresh the view before acting on an idle screen."
    )
    with st.expander(
        "Load / refresh genuine bookmaker prices",
        expanded=not bool(st.session_state.get("market_snapshot")),
    ):
        # Keep the working r5 two-argument interface: Cloud can retain an older
        # imported collection module across a warm source update.
        render_collection(slate, release)
    rows, issues = current_decisions(slate, release)
    watch = sum(r["classification"] == "WATCH" for r in rows)
    st.markdown(
        f"""<div class="desk-stats"><div class="desk-stat"><b>0</b><span>VALIDATED BETS</span></div><div class="desk-stat"><b>{watch}</b><span>WATCH QUOTES</span></div><div class="desk-stat"><b>{len(slate)}</b><span>BASELINE FORECASTS</span></div></div>""",
        unsafe_allow_html=True,
    )
    with st.expander("How recommendations work"):
        st.write(
            "WATCH = positive legacy estimated EV with unresolved calibration/availability risks. PASS = non-positive estimate or unsupported settlement. BET is disabled until independent evidence and a preregistered safety threshold exist. No arbitrary confidence score. Rankings do not establish profitability. Multiple props on one player/game can be correlated; they are not an independently diversified portfolio."
        )
    if not rows:
        st.info(
            "No fresh, matched pre-cutoff prices in this session. Retrieve once above; independent forecasts remain available in Player Intelligence. No odds are fetched automatically or fabricated."
        )
        st.caption(
            f"{len(issues)} unsupported source records excluded. Touchdown markets are unavailable: no validated production touchdown model."
        )
        return
    present = {r["market"].removeprefix("QB ") for r in rows}
    with st.expander("Coverage & unavailable markets"):
        st.write(
            f"{len({r['game_id'] for r in rows})} fixture(s) with eligible comparisons in this session. Not a full-slate coverage guarantee."
        )
        st.write(
            "Canonical markets without eligible comparisons: "
            + (
                ", ".join(m for m in STAT_MARKETS.values() if m not in present)
                or "none"
            )
        )
        st.caption(
            "A missing comparison may mean absent/one-sided odds, identity mismatch, a scenario-only forecast, stale data or a closed decision window. It is not a zero or an inferred price. Touchdown probability models are unavailable."
        )
    selected, limit, count = filters(rows)
    st.caption(
        f"{len(selected)} unique selections · {count} quotes · highest estimated EV per selection shown"
    )
    if not selected:
        st.info(
            "No selections match these filters. Zero opportunities is a valid result."
        )
    state = state_for(release)
    page_count = max(1, (len(selected) + limit - 1) // limit)
    page = min(max(1, st.session_state.get("intelligence_page", 1)), page_count)
    if st.session_state.get("intelligence_page", page) != page:
        st.session_state["intelligence_page"] = page
    for row in selected[(page - 1) * limit : page * limit]:
        card(row, release, state)
    if page_count > 1:
        st.selectbox(
            "Results page", list(range(1, page_count + 1)), key="intelligence_page"
        )


def player_view(slate, release):
    st.markdown("### Player Intelligence")
    names = slate[["player_id", "player"]].drop_duplicates().sort_values("player")
    pid = st.selectbox(
        "Player",
        names.player_id.tolist(),
        format_func=lambda p: names[names.player_id.eq(p)].iloc[0].player,
    )
    own = slate[slate.player_id.eq(pid)]
    gid = st.selectbox(
        "Player fixture",
        own.game_id.unique(),
        format_func=lambda g: game_label(g, release),
    )
    own = own[own.game_id.eq(gid)]
    st.markdown(f"#### {own.iloc[0].player} · {own.iloc[0].team}")
    market = st.selectbox("Forecast market", own.market.unique())
    row = own[own.market.eq(market)].iloc[0]
    st.metric("Independent Stage 1A projection", f"{row.projection:.1f}")
    st.caption(
        f"Status: {row.projection_status} · residual scale {row.resid_std:.2f} · forecast {row.prediction_at}"
    )
    if row.projection_status != "complete":
        st.warning(
            "Scenario-only forecast. Not eligible for market recommendations; unknown conditions are not assumed confirmed."
        )
    st.markdown("**Legacy distribution reference · experimental**")
    if row.resid_std > 0:
        x = np.linspace(
            max(0, row.projection - 3 * row.resid_std),
            max(1, row.projection + 3 * row.resid_std),
            100,
        )
        curve = pd.DataFrame(
            {"Outcome": x, "Density": norm.pdf(x, row.projection, row.resid_std)}
        )
        chart = (
            alt.Chart(curve)
            .mark_area(opacity=0.45, color="#859ed3")
            .encode(x="Outcome:Q", y="Density:Q")
            .properties(height=150, background="#111c2f")
            .configure_axis(labelColor="#b7c5da", titleColor="#b7c5da")
            .configure_view(stroke=None)
        )
        st.altair_chart(chart, width="stretch")
    st.caption(
        "Unchanged normal reference, displayed only for non-negative outcomes without renormalising. Discrete, skewed and zero-heavy outcomes can violate this assumption. This is not a calibrated prediction interval."
    )
    evidence = player_evidence(state_for(release), pid, gid)
    st.markdown("**Recent observed role & matchup**")
    for value in evidence["facts"]:
        st.write(value)
    for value in evidence["hypotheses"]:
        st.caption("Hypothesis: " + value)
    with st.expander("Missing information / uncertainty"):
        for value in evidence["missing"]:
            st.write(value)
        st.write(
            "Season-long trend, per-game snap/route chart, confirmed current injury/inactive status, personnel changes and timestamped weather are not supplied by this frozen preview. No missing history is filled with zeros."
        )
    rows, _ = current_decisions(slate, release)
    relevant = [
        r
        for r in rows
        if r["player_id"] == pid and r["market"] == market and r["game_id"] == gid
    ]
    st.markdown("**Current genuine bookmaker comparisons**")
    if not relevant:
        st.info(
            "No fresh eligible prices for this player/market. Refresh in Top Picks or Market Intelligence."
        )
    for r in relevant[:6]:
        card(r, release, state_for(release), detail=False)


def performance_view():
    st.markdown("### Model Performance")
    st.warning(
        "Frozen chronological development evidence, not a fresh independent final test. Research methods remain inactive in live Stage 1A pricing. Unit tests demonstrate engineering behavior, not profitability."
    )
    try:
        data = load_performance()
    except (OSError, ValueError, KeyError, TypeError):
        st.error(
            "Frozen performance artifact failed integrity/governance checks. Results are not displayed."
        )
        return
    a = data["accuracy.csv"]
    p = data["probability_metrics.csv"]
    rel = data["reliability.csv"]
    market = st.selectbox("Evaluation market", sorted(a.market.unique()))
    season = st.selectbox(
        "Evaluation season",
        ["all"] + sorted([str(x) for x in a.season.unique() if str(x) != "all"]),
    )
    view = a[a.market.eq(market) & a.season.astype(str).eq(season)]
    for _, r in view.iterrows():
        with st.container(border=True):
            st.markdown(f"**{r.version.upper()} · {int(r.n):,} player-market games**")
            st.write(
                f"MAE {r.mae:.2f} · RMSE {r.rmse:.2f} · bias {r.bias:+.2f} · naive MAE {r.naive_mae:.2f}"
            )
            st.write(
                f"90% interval coverage {r.coverage90:.1%} · width {r.width90:.2f} · interval score {r.interval_score90:.2f}"
            )
    scored = p[p.market.eq(market) & p.season.astype(str).eq(season)]
    for _, r in scored.iterrows():
        st.caption(
            f"{r.version}: Brier {r.brier:.4f} [{r.brier_low:.4f}, {r.brier_high:.4f}] week-block interval · log loss {r.log_loss:.4f} · n={int(r.n):,} player games"
        )
    legacy = data["legacy_probability.csv"]
    legacy = legacy[legacy.market.eq(market) & legacy.season.astype(str).eq(season)]
    for _, r in legacy.iterrows():
        st.caption(
            f"Archived Stage 1A normal-rule comparator: Brier {r.brier:.4f}, log loss {r.log_loss:.4f}, n={int(r.n):,}. Applied to historical chronological fold forecasts/synthetic thresholds, not today's deployed model or genuine historical odds."
        )
    st.markdown("**Development calibration by probability band**")
    points = rel[rel.market.eq(market)].copy()
    chart = (
        alt.Chart(points)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "mean_probability:Q",
                scale=alt.Scale(domain=[0, 1]),
                title="Mean model probability",
            ),
            y=alt.Y(
                "observed:Q", scale=alt.Scale(domain=[0, 1]), title="Observed frequency"
            ),
            color="version:N",
            tooltip=[
                "version",
                "n_probes",
                "n_player_games",
                "mean_probability",
                "observed",
            ],
        )
        .properties(height=230)
    )
    diagonal = (
        alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]}))
        .mark_line(color="#718096", strokeDash=[4, 4])
        .encode(x="x:Q", y="y:Q")
    )
    st.altair_chart(
        (chart + diagonal)
        .properties(background="#111c2f")
        .configure_axis(labelColor="#b7c5da", titleColor="#b7c5da")
        .configure_legend(labelColor="#b7c5da", titleColor="#b7c5da")
        .configure_view(stroke=None),
        width="stretch",
    )
    with st.expander("Reliability counts and uncertainty"):
        for _, r in points.iterrows():
            st.caption(
                f"{r.version}, band {int(r.band)}: {int(r.n_probes)} correlated probes / {int(r.n_player_games)} distinct player-games; observed week-block interval [{r.observed_block_low:.3f}, {r.observed_block_high:.3f}]."
            )
    st.caption(
        "The chart uses all development seasons even when an individual season is selected above. Multiple synthetic thresholds per player-game are correlated and are not historical bookmaker lines."
    )
    st.markdown("**What is established — and what is not**")
    st.write(
        "Chronological walk-forward infrastructure, preserved populations, naive comparisons, development error/calibration diagnostics and week-block uncertainty are implemented. Stage 1B.1 passing-yards MAE improved from 73.07 to 68.14 on previously inspected development data. This does not validate today’s Stage 1A betting probabilities."
    )
    st.write(
        "Stage 1A exact deployed release versus genuinely available historical bookmaker lines: unavailable. The research Stage 1B comparator is not a replay of today’s saved production release. Authentic historical betting sample: 0; realised ROI, hit rate and closing-line value unavailable. No invented odds or results."
    )
    st.caption(
        "Final period 2026 week 11 onward remains sealed. No final outcomes, experimental model files or raw evaluation forecasts are loaded here. C1/C2 matchup experiments were archived without demonstrated player-level improvement; qualitative context is not a numeric adjustment."
    )
    st.info(
        "Calibration certificate for BET classification: unavailable. Passing touchdowns and anytime touchdowns: unavailable. New model fitting, settlement and paid odds sources are not activated."
    )


def operations_view(release):
    st.markdown("### Data, safety & £0 cost audit")
    services = [
        (
            "Streamlit Community Cloud",
            "Existing free research app only; same URL/password. No new app or upgrade.",
        ),
        (
            "SportsGameOdds",
            "Active free Amateur only; 2,500 objects / rolling 30 days; conservative lifetime cap ≤2,000 plus provider-usage/headroom checks. No paid fallback.",
        ),
        (
            "GitHub quota",
            "Existing private repository; metadata/counter only, atomic SHA writes, conflict detection and no resets. No odds, account data or keys stored there.",
        ),
        (
            "GitHub Actions",
            "Existing public-repository standard Linux CI only. No larger runners, paid capacity, schedules or billing changes.",
        ),
        (
            "Database / bankroll",
            "No new database, no Supabase connection, no production ledger access or stake placement.",
        ),
        (
            "Python / browser",
            "Existing installed open-source packages and browser tools; no new licences, compute instances, external fonts or paid testing service.",
        ),
        (
            "Codex / account billing",
            "No new paid compute resource, credit purchase or overage enabled. Existing account/subscription billing is not visible to this app; £0 total account billing cannot be independently certified.",
        ),
    ]
    for title, text in services:
        with st.container(border=True):
            st.markdown("**" + title + "**")
            st.write(text)
    st.caption(
        "Incremental paid services created: none. New subscriptions/resources/billing exposure introduced by this code: none. All account-level settings remain owner-controlled; never accept an upgrade or trial prompt."
    )
    st.markdown("**Retention & operations**")
    st.write(
        "No polling, background collection or automatic provider requests on page load. Each manual collection reserves its bounded event limit before retrieval; failed/empty responses are not refunded. Local cache has a 10-minute reuse window with 24-hour pruning on access; private UI snapshots expire after 15 minutes and are limited to six request windows. No provider archive, CSV export, settlement, closing-price collector or long-term odds storage."
    )
    st.write(
        "Prices stop qualifying after 15 minutes or T−60. Munich 13:30 UK; 18:00 slate 17:00 UK. All timing checks use timezone-aware UTC (UK is UTC on this date). A disconnected sleeping browser must refresh/reopen before acting; displayed captures never gain a new timestamp on rerun."
    )
    st.write(
        "No forecast adjustment, experimental probability activation, model retraining, sealed result access, paid account, counter reset or production modification. Working recovery checkpoint: research-r5-working-20261115 at 938485d."
    )
    st.caption(
        f"Baseline integrity verified on entry: {release['release_id']}. Nine model artifacts, forecasts and original probability method remain independent of the market."
    )


def render(slate, release):
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(
        """<header class="desk-hero"><div class="desk-eyebrow">NFL / RESEARCH DESK</div><div class="desk-title">Betting Intelligence</div><div class="desk-sub">Independent forecasts · Genuine market prices</div></header>""",
        unsafe_allow_html=True,
    )
    st.caption("Research intelligence r6.1 · experimental · US market benchmarks")
    section = st.selectbox(
        "Workspace",
        [
            "Top Picks",
            "Player Intelligence",
            "Game Intelligence",
            "Market Intelligence",
            "Model Performance",
            "Data & Safety",
        ],
    )
    if section == "Top Picks":
        top_picks(slate, release)
    elif section == "Player Intelligence":
        player_view(slate, release)
    elif section == "Game Intelligence":
        render_games(release)
    elif section == "Market Intelligence":
        render_collection(slate, release)
        rows, _ = current_decisions(slate, release)
        if rows:
            st.markdown("### Actual-line probability & price comparisons")
            selected, limit, _ = filters(rows, deduplicate=False)
            state = state_for(release)
            # Unlike landing deduplication, select player detail for every exact quote.
            for r in selected[:limit]:
                card(r, release, state)
    elif section == "Model Performance":
        performance_view()
    else:
        operations_view(release)
