"""Recommendations-first UI. Existing URL, password, adapters and pricing only."""

from datetime import UTC, datetime

import streamlit as st

from matchup_research.ui import render as render_games
from research_access import secret
from sgo_research.diagnostics import safe_diagnostic
from sgo_research.market_ui import render as render_fixture
from sgo_research.ui import research_key

from .engine import evaluate, player_evidence
from .slate import (
    LazyCollector,
    cached_snapshots,
    collection_plan,
    coverage,
    execute_plan,
    merge_snapshots,
    model_candidates,
    parlay_research,
    top_two,
    unique_watch,
)
from .ui import (
    CSS,
    esc,
    game_label,
    operations_view,
    performance_view,
    player_view,
    state_for,
)


def load_data(slate, release):
    now = datetime.now(UTC)
    incoming = cached_snapshots(now)
    latest = st.session_state.get("market_snapshot")
    if latest:
        incoming.append(latest)
    captures, expired = merge_snapshots(
        st.session_state.get("intelligence_snapshots", []), incoming, now
    )
    st.session_state["intelligence_snapshots"] = captures
    st.session_state["r7_expired"] = expired
    if latest and latest not in captures:
        st.session_state.pop("market_snapshot", None)
    rows, issues = evaluate(captures, slate, release, now)
    return rows, model_candidates(slate, release, now), captures, issues


def opponent_note(state, player_id, gid):
    if state:
        fixture = next((f for f in state["fixtures"] if f["game_id"] == gid), None)
        if fixture:
            for a in fixture["assessments"]:
                if any(
                    p.get("player_id") == player_id
                    for p in a.get("quarterbacks", []) + a.get("receivers", [])
                ):
                    contact = a["opponent_contact_proxy"]
                    rate = contact.get("hit_or_sack_rate")
                    if rate is not None:
                        return f"Opponent {a['opponent_defense']}: observed hit/sack contact {rate:.1%} over {contact['contact_label_n']} labelled dropbacks. Historical proxy, not a quantified player adjustment."
    return "Opponent effects are unquantified; no reliable player-specific matchup uplift is assumed."


def model_card(row, release, state):
    evidence = player_evidence(state, row["player_id"], row["game_id"])
    fact = (
        evidence["facts"][-1]
        if evidence["facts"]
        else "Player-specific recent usage unavailable; no zero usage is inferred."
    )
    st.markdown(
        f"""<article class="desk-card"><div class="small">{esc(game_label(row["game_id"], release))}</div><h3>{esc(row["player"])}</h3><span class="desk-pill">MODEL ONLY</span><div class="desk-line">{esc(row["market"])} · forecast {row["projection"]:.1f}</div><p class="desk-note">Projection rank {int(row["production_rank"])} of {int(row["market_population"])} in this market. High projected output is not betting value.</p><div class="small">No bookmaker line, direction, odds, probability or EV is inferred.</div><p class="desk-note">{esc(fact)}</p><p class="desk-note">{esc(opponent_note(state, row["player_id"], row["game_id"]))}</p><div class="desk-risk">Role/inactive status and matchup effects are unverified. Independent model research only.</div></article>""",
        unsafe_allow_html=True,
    )
    with st.expander(f"Model evidence · {row['player']} / {row['market']}"):
        for text in evidence["facts"]:
            st.write("Observed: " + text)
        for text in evidence["hypotheses"]:
            st.write("Hypothesis: " + text)
        for text in evidence["missing"]:
            st.caption(text)
        st.caption(
            f"Forecast {row['prediction_at']} · no numeric matchup adjustment or bookmaker comparison."
        )


def market_card(row, release, state):
    evidence = player_evidence(state, row["player_id"], row["game_id"])
    fact = (
        evidence["facts"][-1]
        if evidence["facts"]
        else "Player-specific recent form/usage is not established."
    )
    prob = (
        "Unavailable"
        if row["model_probability"] is None
        else f"{row['model_probability']:.1%}"
    )
    ev = "Unavailable" if row["ev_pct"] is None else f"{row['ev_pct']:+.1f}%"
    st.markdown(
        f"""<article class="desk-card watch"><div class="small">{esc(game_label(row["game_id"], release))}</div><h3>{esc(row["player"])}</h3><span class="desk-pill watch">{esc(row["classification"])} · EXPERIMENTAL</span><div class="desk-line">{esc(row["side"])} {row["line"]:g} · {esc(row["market"])}</div><div class="small">{esc(row["bookmaker"].upper())} · {row["decimal_odds"]:.3f} decimal · US benchmark</div><div class="desk-grid"><div><b>{row["projection"]:.1f}</b><span>MODEL FORECAST</span></div><div><b>{prob}</b><span>LEGACY PROBABILITY</span></div><div><b>{ev}</b><span>ESTIMATED EV / £1</span></div></div><p class="desk-note">Ranks by positive quoted-price legacy estimated EV; not validated betting value.</p><p class="desk-note">{esc(fact)}</p><p class="desk-note">{esc(opponent_note(state, row["player_id"], row["game_id"]))}</p><div class="desk-risk">Calibration, inactive/role status and UK availability unverified.</div><div class="small">Updated {esc(row["oldest_update"])} · expires {esc(row["valid_until"])}</div></article>""",
        unsafe_allow_html=True,
    )
    with st.expander(
        f"Supporting evidence · {row['player']} / {row['market']} / {row['side']}"
    ):
        st.write(
            f"Exact quote: {row['bookmaker']} {row['side']} {row['line']:g} at {row['decimal_odds']:.3f}. Market median {row['median_line']:g} from {row['book_count']} books; median is not an offered price."
        )
        st.write(
            f"Raw implied {row['implied_probability']:.1%}; paired no-vig {row['no_vig_probability']:.1%}. No-vig normalises prices; it is not a true-probability certificate."
        )
        if row["ev_pct"] is not None:
            st.write(
                f"EV / £1 = p × decimal − 1 = {row['ev_pct'] / 100:+.4f}. Legacy probability method is uncalibrated for live betting."
            )
            st.caption(
                f"Projection-shift sensitivity: EV {row['stress_ev_min']:+.1f}% to {row['stress_ev_max']:+.1f}% for ±1 residual scale; not a confidence interval."
            )
        st.markdown("**Observed evidence**")
        for text in evidence["facts"]:
            st.write(text)
        st.markdown("**Matchup hypotheses — unquantified**")
        for text in evidence["hypotheses"]:
            st.write(text)
        for text in evidence["missing"] + row["reasons"]:
            st.caption(text)
        st.caption(
            f"Captured {row['retrieved_at']} · forecast {row['forecast_at']} · source {row['source_odd_id']}. No wager, stake or numerical adjustment."
        )


def controls(slate, release):
    with st.expander("Refresh prices — slate-wide collection", expanded=False):
        week = st.selectbox(
            "Collection week", sorted(slate.week.unique()), key="r7_week"
        )
        selected = slate[slate.week.eq(week)]
        books = st.multiselect(
            "Collection bookmakers",
            ["fanduel", "draftkings", "betmgm"],
            default=["fanduel", "draftkings", "betmgm"],
            key="r7_books",
        )
        if not books:
            st.info("Choose at least one bookmaker.")
            return
        plan = collection_plan(selected, release, datetime.now(UTC), books)
        st.write(
            f"{len(plan['eligible_games'])} eligible fixtures in {len(plan['windows'])} kickoff windows. Worst case this click: {plan['max_reserved_objects']} reserved objects and {plan['max_provider_http_calls']} SportsGameOdds HTTP calls. Cache hits reduce consumption."
        )
        st.caption(
            "At most three uncached windows per click: earliest deadline, then largest fixture coverage. Each window reserves 16 objects before fetching. Existing free cap/headroom and atomic quota checks can stop earlier. No retries, waiting, polling or pagination; skipped fixtures remain explicitly missing."
        )
        if st.button(
            "Collect eligible slate — bounded free requests",
            disabled=not bool(plan["windows"]) or not bool(research_key()),
            key="r7_collect",
        ):
            try:
                collector = LazyCollector(
                    research_key(),
                    lambda: datetime.now(UTC),
                    cap=int(secret("SGO_OBJECT_CAP") or "2000"),
                    terms_ack=str(secret("SGO_PRIVATE_CACHE_TERMS_ACK")) == "1",
                )
                result = execute_plan(
                    plan,
                    collector,
                    datetime.now(UTC),
                    cached_snapshots(datetime.now(UTC)),
                )
                merged, _ = merge_snapshots(
                    st.session_state.get("intelligence_snapshots", []),
                    result["snapshots"],
                    datetime.now(UTC),
                )
                st.session_state["intelligence_snapshots"] = merged
                if result["snapshots"]:
                    st.session_state["market_snapshot"] = result["snapshots"][-1]
                st.session_state["r7_batch_status"] = result["statuses"]
                st.rerun()
            except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
                code, message = safe_diagnostic(error)
                st.warning(f"Collection stopped [{code}]: {message}")
        for item in st.session_state.get("r7_batch_status", []):
            st.caption(
                f"{', '.join(item['games'])}: {item['status']}"
                + (f" [{item['code']}] {item['message']}" if item.get("code") else "")
            )
            if item.get("continuation"):
                st.caption(
                    "Provider supplied a continuation cursor; additional coverage may exist. No automatic pagination."
                )
        with st.expander(
            "Advanced — per-fixture retrieval and diagnostics", expanded=False
        ):
            # Stable two-argument interface: no repeat of the r6 warm-import defect.
            render_fixture(selected, release)


def coverage_panel(rows, slate, release, captures, issues):
    with st.expander(
        "Coverage, timestamps & excluded / expired prices", expanded=False
    ):
        plan = collection_plan(slate, release, datetime.now(UTC))
        report = coverage(rows, release, plan, captures)
        st.write(
            f"{report['priced']}/{report['eligible']} eligible fixtures have at least one matched, fresh paired price. This is not full-market coverage."
        )
        for gid, reason in report["missing"].items():
            st.caption(f"{game_label(gid, release)} — {reason}")
        for gid, reason in plan["excluded"].items():
            st.caption(f"{gid} — excluded: {reason}")
        for snapshot in captures:
            st.caption(
                f"Original retrieval {snapshot['retrieved_at']}; provider timestamps are preserved. Cached or restored does not mean refreshed."
            )
        st.caption(
            f"{len(issues)} unsupported source records excluded. Expired/post-cutoff prices do not enter current recommendations."
        )
        if st.session_state.get("r7_expired"):
            st.caption(
                "Expired captures removed from current view: "
                + ", ".join(st.session_state["r7_expired"])
            )
        st.caption(
            "Private local host cache may survive sessions, not redeployments. Reuse ≤10 minutes; cleanup ≤24 hours; no quote data in GitHub quota state or production Supabase."
        )


def top_picks(slate, release):
    rows, models, captures, issues = load_data(slate, release)
    state = state_for(release)
    ranked = unique_watch(rows)
    st.markdown("### Top Picks")
    st.caption(
        "0 validated BETs · experimental WATCH / model-only research · US benchmark prices"
    )
    if ranked:
        # Cards precede every collection, quota, diagnostic, coverage and filter control.
        for row in ranked[:5]:
            market_card(row, release, state)
        with st.expander("More ranked opportunities & filters", expanded=False):
            game = st.selectbox(
                "Recommendation fixture",
                ["All"] + sorted({r["game_id"] for r in ranked}),
            )
            market = st.selectbox(
                "Recommendation market", ["All"] + sorted({r["market"] for r in ranked})
            )
            query = st.text_input("Recommendation player contains").casefold()
            filtered = [
                r
                for r in ranked
                if (game == "All" or r["game_id"] == game)
                and (market == "All" or r["market"] == market)
                and query in r["player"].casefold()
            ]
            for row in (
                filtered[5:]
                if game == "All" and market == "All" and not query
                else filtered[:20]
            ):
                market_card(row, release, state)
    else:
        st.info(
            "No current WATCH quotes. Model-only candidates below have no inferred odds, direction, probability or EV."
            if not rows
            else "Available quotes do not support a WATCH candidate. PASS is a valid result; no positive edge is manufactured."
        )
        if not rows:
            people = set()
            for row in models:
                if row["player_id"] in people:
                    continue
                model_card(row, release, state)
                people.add(row["player_id"])
                if len(people) == 5:
                    break
    controls(slate, release)
    coverage_panel(rows, slate, release, captures, issues)
    with st.expander("Ranking policy & scientific limits", expanded=False):
        st.write(
            "WATCH candidates are quality-gated then ranked by unchanged Stage 1A quoted-price estimated EV. Best quote per player/market/direction shown. No confidence score, correlated-evidence sum or BET certificate. Missing/expired/scenario-only/unsupported-push cases cannot qualify. Model-only candidates rank high projected production within their own market; this is not betting value."
        )
        st.caption(
            "Snapshots and price ages are as of this view generation; reopen/rerun after leaving the phone idle. No background provider polling occurs."
        )


def by_game(slate, release):
    rows, models, captures, issues = load_data(slate, release)
    state = state_for(release)
    picks = top_two(rows, models, release)
    st.markdown("### Top 2 by Game")
    st.caption(
        "At most one selection per player, up to two per fixture; fewer is valid. Model-only entries have no bookmaker bet or Over/Under recommendation."
    )
    for gid in sorted(
        release["game_kickoffs"], key=lambda g: release["game_kickoffs"][g]
    ):
        st.markdown("#### " + game_label(gid, release))
        if not picks[gid]:
            st.caption(
                "No eligible WATCH or unpriced complete model candidates. Closed windows, PASS prices or incomplete forecasts are not forced into picks."
            )
        for row in picks[gid]:
            if row["classification"] == "MODEL ONLY":
                model_card(row, release, state)
            else:
                market_card(row, release, state)
    controls(slate, release)
    coverage_panel(rows, slate, release, captures, issues)


def parlays(slate, release):
    rows, models, _, _ = load_data(slate, release)
    picks = top_two(rows, models, release)
    choices = {}
    for legs in picks.values():
        for r in legs:
            key = "|".join(
                str(r.get(k))
                for k in ["game_id", "player_id", "market", "side", "bookmaker"]
            )
            choices[key] = r
    st.markdown("### Parlay Research")
    st.info(
        "No genuine bookmaker combined quote or validated dependence model is available. Joint probability and parlay EV are unavailable; this tool does not place bets."
    )
    selected = st.multiselect(
        "Choose legs from Top 2 by Game",
        list(choices),
        format_func=lambda k: (
            f"{choices[k]['player']} · {choices[k]['market']} · {choices[k]['game_id']} · {choices[k]['classification']}"
        ),
    )
    same = st.checkbox(
        "Include same-game research (unmodelled correlation)", value=False
    )
    legs = [choices[k] for k in selected]
    result = parlay_research(legs, datetime.now(UTC), allow_same_game=same)
    for row in legs:
        price = (
            "unpriced model research"
            if row.get("decimal_odds") is None
            else f"{row['bookmaker']} {row['side']} {row['line']:g} at {row['decimal_odds']:.3f}"
        )
        st.write(f"{row['player']} · {row['market']}: {price}")
    if result["leg_price_product"] is not None:
        st.metric(
            "Arithmetic product of leg prices — NOT an offered parlay quote",
            f"{result['leg_price_product']:.3f}",
        )
    st.write(
        "Actual combined quoted odds: unavailable. Joint model probability: unavailable. Parlay EV: unavailable. Recommended stake: £0."
    )
    for warning in result["warnings"]:
        st.warning(warning)


def render(slate, release):
    st.markdown(CSS, unsafe_allow_html=True)
    st.caption("NFL Research · r7 · independent Stage 1A forecasts")
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
            "Data & Safety",
        ],
    )
    if section == "Top Picks":
        top_picks(slate, release)
    elif section == "Top 2 by Game":
        by_game(slate, release)
    elif section == "Parlay Research":
        parlays(slate, release)
    elif section == "Player Intelligence":
        load_data(slate, release)
        player_view(slate, release)
    elif section == "Game Intelligence":
        render_games(release)
    elif section == "Market Intelligence":
        load_data(slate, release)
        render_fixture(slate, release)
    elif section == "Model Performance":
        performance_view()
    else:
        operations_view(release)
