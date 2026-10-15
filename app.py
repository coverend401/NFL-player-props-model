import json
from datetime import datetime, timezone

import joblib
import pandas as pd
import streamlit as st
from scipy.stats import norm

import betting_engine as be
import performance as perf
from ledger import Ledger, SQLiteBackend, SupabaseBackend
from odds_utils import parse_odds, implied_probability, expected_value, signal_category
from pricing import price_prop

st.set_page_config(page_title="NFL Player Props Model", layout="centered")
st.title("NFL Player Props Model")

# ---------------------------------------------------------------- access gate
def _secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


_pw = _secret("APP_PASSWORD")
if _pw:
    if st.session_state.get("authed") != True:
        entered = st.text_input("Password", type="password")
        if entered and entered == _pw:
            st.session_state["authed"] = True
            st.rerun()
        elif entered:
            st.error("Wrong password.")
        st.stop()

# ---------------------------------------------------------------- shared setup
MARKETS = {
    "Passing Yards": "passing_yards",
    "Passing Attempts": "passing_attempts",
    "Completions": "completions",
    "Rushing Yards": "rushing_yards",
    "Rushing Attempts": "rushing_attempts",
    "QB Rushing Yards": "qb_rushing_yards",
    "QB Rushing Attempts": "qb_rushing_attempts",
    "Receiving Yards": "receiving_yards",
    "Receptions": "receptions",
}
INJURY_OPTIONS = ["unknown", "healthy", "questionable", "doubtful", "out"]


@st.cache_data
def load_features():
    return pd.read_parquet("data/player_features.parquet")


@st.cache_data
def load_slate():
    try:
        return pd.read_parquet("data/slate.parquet")
    except FileNotFoundError:
        return None


@st.cache_resource
def load_model(file_label):
    try:
        return joblib.load(f"data/model_{file_label}.joblib")
    except FileNotFoundError:
        return None


@st.cache_data
def latest_lookup(_features):
    latest = _features.sort_values(["season", "week"]).groupby("player_display_name").tail(1)
    return {r["player_display_name"]: r for _, r in latest.iterrows()}


@st.cache_resource
def get_ledger():
    url, key = _secret("SUPABASE_URL"), _secret("SUPABASE_KEY")
    if url and key:
        try:
            return Ledger(SupabaseBackend(url, key)), None
        except Exception as e:  # fall back, but say so loudly
            return Ledger(SQLiteBackend("ledger_local.db")), f"Supabase connection failed ({e}). Using TEMPORARY local storage."
    return Ledger(SQLiteBackend("ledger_local.db")), "Supabase not configured - bets are stored in a TEMPORARY file that is wiped when the app restarts."


features = load_features()
slate = load_slate()
LATEST = latest_lookup(features)
ledger, ledger_warning = get_ledger()


def load_settings():
    saved = ledger.get_setting("settings", {}) or {}
    return {**be.DEFAULT_SETTINGS, **saved}


settings = load_settings()
live_pl = ledger.realised_live_pl()
bankroll = be.current_bankroll(settings, live_pl)
ledger_df = ledger.dataframe()
calib_table = be.calibration_table(ledger_df)
_clv = pd.to_numeric(ledger_df["clv_pct"], errors="coerce").mean() if len(ledger_df) else 0.0
avg_clv = 0.0 if pd.isna(_clv) else float(_clv)

if ledger_warning:
    st.warning(ledger_warning)
if settings["paper_mode"]:
    st.info("PAPER MODE is on - bets you log are tracked but do not touch your bankroll. "
            "This model has not yet been tested against real bookmaker prices, so this is the recommended setting.")


def price(market, player, side, line, odds_raw, odds_other_raw=None, injury="unknown"):
    return price_prop(market=market, file_label=MARKETS[market], player=player, side=side, line=line,
                      odds_raw=odds_raw, odds_other_raw=odds_other_raw, injury_status=injury, slate=slate,
                      latest_lookup=LATEST, load_model=load_model, calib_table=calib_table, avg_clv=avg_clv,
                      settings=settings, bankroll=bankroll)


def gbp(x):
    return f"£{x:,.2f}"


tabs = st.tabs(["Top Picks", "Today's Slate", "Single Prop Lookup", "Price Board",
                "Parlay Hunter", "My Bets", "Settings"])

# ================================================================ TOP PICKS (unchanged)
with tabs[0]:
    st.subheader("Model's highest-conviction Over picks")
    st.caption("Two per game, ranked by how far the model's view diverges from the player's "
               "RECENT form (last 3 games) - not career average, so this should track much closer "
               "to real bookmaker lines. Shows Over picks only. This reflects model confidence, "
               "not confirmed betting value - check any pick against a real sportsbook price in "
               "Single Prop Lookup before betting it.")
    try:
        top_picks = pd.read_parquet("data/top_picks.parquet")
        for _, r in top_picks.iterrows():
            st.markdown(f"**{r['player']}** ({r['team']} vs {r['opponent']}) — "
                        f"Over {r['recent_form']} {r['market']} "
                        f"→ model projects {r['projection']}")
            st.caption(f"Model confidence: {r['model_probability']*100:.0f}% | "
                       f"{r['games_played_prior']} games on record")
            st.divider()
        st.warning("If picking two legs from the SAME game for a parlay: same-game outcomes are "
                   "correlated (a QB's big day tends to come with his top receiver's big day too). "
                   "Multiplying these two probabilities together overstates your true combined odds - "
                   "treat same-game parlays with extra caution.")
    except FileNotFoundError:
        st.warning("Top picks not generated yet - run the workflow to build them.")

# ================================================================ TODAY'S SLATE (unchanged)
with tabs[1]:
    st.subheader("This week's projections")
    if slate is None:
        st.warning("Slate not generated yet - run the workflow to build it.")
    else:
        week_num = slate["week"].iloc[0] if len(slate) else "?"
        st.caption(f"Week {week_num} - {len(slate)} player-market projections")
        market_filter = st.multiselect("Filter by market", sorted(slate["market"].unique()))
        filtered = slate[slate["market"].isin(market_filter)] if market_filter else slate
        st.dataframe(
            filtered.sort_values(["market", "projection"], ascending=[True, False])
            [["market", "player", "team", "opponent", "projection", "career_avg", "recent_form", "games_played_prior"]],
            width="stretch", hide_index=True)
        st.caption("No bookmaker odds baked in yet - check any interesting projection against "
                   "a real sportsbook price in the Single Prop Lookup tab to see edge and EV.")

# ================================================================ SINGLE PROP LOOKUP (existing logic kept)
with tabs[2]:
    def single_lookup():
        st.subheader("Try a prediction")
        market_label = st.selectbox("Market", list(MARKETS.keys()))
        file_label = MARKETS[market_label]
        bundle = load_model(file_label)
        if bundle is None:
            st.warning(f"No trained model file found yet for {market_label}.")
            return
        model, resid_std = bundle["model"], bundle["resid_std"]
        feature_cols, positions = bundle["features"], bundle["positions"]

        eligible = features[features["position"].isin(positions)]
        players = sorted(eligible["player_display_name"].dropna().unique())
        player = st.selectbox("Player", players)
        player_rows = eligible[eligible["player_display_name"] == player].dropna(subset=feature_cols)
        if player_rows.empty:
            st.warning("Not enough game history for this player yet.")
            return

        latest = player_rows.sort_values(["season", "week"]).iloc[-1]
        X = latest[feature_cols].astype(float).to_frame().T
        prediction = model.predict(X)[0]
        games_played = int(latest["games_played_prior"])

        st.metric(f"Model projection - {market_label}", f"{prediction:.1f}")
        st.caption(f"Based on data through Season {int(latest['season'])}, Week {int(latest['week'])} "
                   f"({games_played} prior games on record).")

        st.subheader("Compare against a bookmaker price")
        line = st.number_input("Bookmaker line", value=float(round(prediction, 1)), step=0.5)
        col1, col2 = st.columns(2)
        with col1:
            side = st.radio("Which side are you pricing?", ["Over", "Under"], horizontal=True)
        with col2:
            odds_raw = st.text_input("Odds (decimal, American, or fractional)", placeholder="e.g. -110, 1.91, or 10/11")

        prob_over = 1 - norm.cdf(line, prediction, resid_std)
        prob_under = 1 - prob_over
        model_prob = prob_over if side == "Over" else prob_under
        col1, col2 = st.columns(2)
        col1.metric("Model probability Over", f"{prob_over*100:.1f}%")
        col2.metric("Model probability Under", f"{prob_under*100:.1f}%")

        if odds_raw:
            try:
                decimal_odds = parse_odds(odds_raw)
                implied_p = implied_probability(decimal_odds)
                edge = (model_prob - implied_p) * 100
                ev = expected_value(model_prob, decimal_odds)
                signal = signal_category(edge, games_played)
                st.subheader(f"Value check - {side}")
                c1, c2, c3 = st.columns(3)
                c1.metric("Implied probability", f"{implied_p*100:.1f}%")
                c2.metric("Edge", f"{edge:+.1f} pts")
                c3.metric("EV per £1 staked", f"£{ev:+.2f}")
                st.metric("Signal", signal)
            except ValueError as e:
                st.error(f"Couldn't read those odds: {e}")
                return

            # --- betting-engine view (added): uses THIS week's matchup-adjusted projection when available
            res = price(market_label, player, side, line, odds_raw)
            if "error" in res:
                st.caption(f"Engine view unavailable: {res['error']}")
            else:
                st.subheader("Engine view")
                if not res["matchup_adjusted"]:
                    st.caption("Player has no slate projection this week - engine used last game's context.")
                e1, e2, e3 = st.columns(3)
                e1.metric("EV", f"{res['ev_pct']:+.1f}%")
                e2.metric("Confidence", f"{res['confidence']:.0f}/100")
                e3.metric("Bet Score", f"{res['bet_score']:.0f}/100")
                st.metric("Classification", f"{res['class']}  |  stake {gbp(res['stake'])} ({res['stake_pct']:.2f}% of bankroll)")
                if res["dq_reasons"]:
                    st.caption("Data notes: " + "; ".join(res["dq_reasons"]))
                if st.button("Add to Price Board", key="to_board"):
                    board = st.session_state.get("board") or ledger.get_setting("price_board", []) or []
                    board.append({"market": market_label, "player": player, "side": side, "line": float(line),
                                  "odds": odds_raw, "odds_other": "", "injury": "unknown"})
                    st.session_state["board"] = board
                    ledger.set_setting("price_board", board)
                    st.success("Added - see the Price Board tab.")
        else:
            st.caption("Enter the odds for the side you're checking to see edge and expected value.")

    single_lookup()

# ================================================================ PRICE BOARD
if "board" not in st.session_state:
    st.session_state["board"] = ledger.get_setting("price_board", []) or []


def save_board():
    ledger.set_setting("price_board", st.session_state["board"])


def priced_board():
    out = []
    for i, b in enumerate(st.session_state["board"]):
        res = price(b["market"], b["player"], b["side"], b["line"], b["odds"], b.get("odds_other") or None,
                    b.get("injury", "unknown"))
        out.append((i, b, res))
    return out


with tabs[3]:
    st.subheader("Price Board")
    st.caption("Enter the props you can actually see on Bet365 (line + price). Everything downstream - value, "
               "confidence, stakes and the Parlay Hunter - works from this board, because the model can only judge "
               "a bet once it knows the real price.")
    pool_players = (sorted(slate["player"].unique()) if slate is not None else sorted(features["player_display_name"].dropna().unique()))
    # Market sits OUTSIDE the form on purpose: widgets inside a form don't refresh until it is
    # submitted, which would leave the player list stuck on the first market's players.
    market_sel = st.selectbox("Market", list(MARKETS.keys()), key="board_market")
    if slate is not None:
        options = sorted(slate[slate["market"] == market_sel]["player"].unique())
    else:
        options = pool_players
    if not options:
        st.caption(f"No {market_sel} projections in this week's slate.")
    with st.form("add_prop", clear_on_submit=True):
        player_sel = st.selectbox("Player (this week's slate)", options, key="board_player") if options else None
        c1, c2 = st.columns(2)
        side_sel = c1.radio("Side", ["Over", "Under"], horizontal=True)
        line_sel = c2.number_input("Line", value=0.5, step=0.5)
        o1, o2 = st.columns(2)
        odds_sel = o1.text_input("Odds", placeholder="-110 / 1.91 / 10/11")
        odds_other_sel = o2.text_input("Other side odds (optional)", placeholder="for no-vig")
        inj_sel = st.selectbox("Injury status (check the team report)", INJURY_OPTIONS)
        if st.form_submit_button("Add to board") and player_sel and odds_sel:
            try:
                parse_odds(odds_sel)
                st.session_state["board"].append({"market": market_sel, "player": player_sel, "side": side_sel,
                                                  "line": float(line_sel), "odds": odds_sel,
                                                  "odds_other": odds_other_sel, "injury": inj_sel})
                save_board()
                st.rerun()
            except ValueError as e:
                st.error(f"Couldn't read those odds: {e}")

    board = priced_board()
    if not board:
        st.caption("Board is empty.")
    else:
        rows = [{"#": i, "Player": r["player"], "Market": r["market"], "Side": r["side"], "Line": r["line"],
                 "Odds": round(r["odds"], 2), "Model %": round(r["model_prob"] * 100, 1),
                 "Implied %": round(r["implied_prob"] * 100, 1), "EV %": round(r["ev_pct"], 1),
                 "Conf": round(r["confidence"]), "Score": round(r["bet_score"]), "Class": r["class"],
                 "Stake £": r["stake"]} for i, b, r in board if "error" not in r]
        if rows:
            table = pd.DataFrame(rows)
            capped = be.apply_daily_cap(table.rename(columns={"Stake £": "stake", "Score": "bet_score"}),
                                        bankroll, settings)
            st.dataframe(table, width="stretch", hide_index=True)
            if (capped["stake_after_cap"] < capped["stake"] - 0.005).any():
                st.warning(f"Daily exposure cap ({settings['max_daily_exposure_pct']}% = "
                           f"{gbp(bankroll*settings['max_daily_exposure_pct']/100)}) is trimming some stakes - "
                           f"lowest Bet Scores are cut first.")
        for i, b, r in board:
            if "error" in r:
                st.error(f"{b['player']} - {b['market']}: {r['error']}")
                if st.button("Remove", key=f"rm_err_{i}"):
                    st.session_state["board"].pop(i); save_board(); st.rerun()
                continue
            with st.expander(f"{r['player']} {r['side']} {r['line']} {r['market']} @ {b['odds']}  —  {r['class']}"):
                a1, a2, a3 = st.columns(3)
                a1.metric("Model prob", f"{r['model_prob']*100:.1f}%")
                a2.metric("Implied", f"{r['implied_prob']*100:.1f}%")
                a3.metric("No-vig", f"{r['novig_prob']*100:.1f}%" if r["novig_prob"] else "n/a")
                a1, a2, a3 = st.columns(3)
                a1.metric("Edge", f"{r['edge_pts']:+.1f} pts")
                a2.metric("EV", f"{r['ev_pct']:+.1f}%")
                a3.metric("Projection", f"{r['projection']:.1f}")
                a1, a2, a3 = st.columns(3)
                a1.metric("Confidence", f"{r['confidence']:.0f}/100")
                a2.metric("Bet Score", f"{r['bet_score']:.0f}/100")
                a3.metric("Data quality", r["data_quality"].upper())
                st.caption(f"Recommended stake {gbp(r['stake'])} = {r['stake_pct']:.2f}% of bankroll ({r['units']} units)"
                           + (" - capped at your maximum" if r["stake_capped"] else ""))
                if r["dq_reasons"]:
                    st.caption("⚠ " + "; ".join(r["dq_reasons"]))
                st.caption("Confidence breakdown: " + ", ".join(f"{k} {v:.0f}" for k, v in r["confidence_parts"].items()))
                actual = st.number_input("Actual stake £", min_value=0.0, value=float(r["stake"]), step=1.0, key=f"stk_{i}")
                book = st.text_input("Bookmaker", value="Bet365", key=f"bk_{i}")
                l1, l2 = st.columns(2)
                if l1.button("Log bet", key=f"log_{i}", disabled=actual <= 0):
                    ledger.record_single(
                        paper=settings["paper_mode"], game=r["game"], game_key=r["game_key"], team=r["team"],
                        position=r["position"], player=r["player"], market=r["market"], direction=r["side"],
                        bookmaker=book, line=r["line"], odds_decimal=r["odds"], model_prob=r["model_prob"],
                        ev_pct=r["ev_pct"], confidence=r["confidence"], bet_score=r["bet_score"],
                        recommended_stake=r["stake"], actual_stake=actual, model_version=be.MODEL_VERSION)
                    st.success("Logged with original line and odds locked.")
                if l2.button("Remove from board", key=f"rm_{i}"):
                    st.session_state["board"].pop(i); save_board(); st.rerun()

# ================================================================ PARLAY HUNTER
with tabs[4]:
    st.subheader("2-Leg Parlay Hunter")
    st.caption("Singles are the core strategy. A 2-leg parlay is a small, high-variance satellite position - "
               "never a way to win back losses, and stakes should never go up after a losing parlay.")
    priced = [r for _, _, r in priced_board() if "error" not in r]
    if len(priced) < 2:
        st.info("Add at least two priced props to the Price Board first - the hunter can only combine props "
                "whose real bookmaker price it knows.")
    else:
        legs_df = pd.DataFrame(priced)
        overrides = st.session_state.setdefault("parlay_overrides", {})
        result = be.hunt_two_leg_parlays(legs_df, settings, bankroll, overrides)
        d = result["diagnostics"]
        st.caption(f"{len(priced)} props on board. Legs qualifying - Safest: {d['safest_pool']}, "
                   f"Best Value: {d['value_pool']}, Big Payout: {d['big_pool']}.")

        def show(title, key, blurb):
            st.markdown(f"### {title}")
            st.caption(blurb)
            c = result[key]
            if not c:
                st.info("No pair meets this profile's rules on the current board. That is a valid answer - "
                        "see why each prop was rejected below.")
                return
            l1, l2 = c["leg1"], c["leg2"]
            st.markdown(f"**Leg 1:** {l1['player']} {l1['side']} {l1['line']} {l1['market']} @ {l1['odds']:.2f}  \n"
                        f"**Leg 2:** {l2['player']} {l2['side']} {l2['line']} {l2['market']} @ {l2['odds']:.2f}")
            default_odds = l1["odds"] * l2["odds"]
            bo = st.number_input("Bookmaker's actual parlay price (decimal)", min_value=1.01,
                                 value=float(round(overrides.get(c["pair_key"], default_odds), 2)), step=0.05,
                                 key=f"po_{key}")
            if abs(bo - default_odds) > 0.005:
                overrides[c["pair_key"]] = bo
            m = be.parlay_metrics(c["metrics"]["combined_prob"], bo)
            stake = be.recommend_stake(m["combined_prob"], bo, c["min_conf"], bankroll, settings, "parlay2")
            x1, x2, x3 = st.columns(3)
            x1.metric("Combined probability", f"{m['combined_prob']*100:.1f}%")
            x2.metric("Model fair odds", f"{m['fair_odds']:.2f}")
            x3.metric("Bookmaker odds", f"{bo:.2f}")
            x1, x2, x3 = st.columns(3)
            x1.metric("Bookmaker implied", f"{m['implied_prob']*100:.1f}%")
            x2.metric("Probability edge", f"{m['prob_edge_pts']:+.1f} pts")
            x3.metric("Parlay EV", f"{m['ev_pct']:+.1f}%")
            x1, x2, x3 = st.columns(3)
            x1.metric("Parlay Score", f"{c['parlay_score']:.0f}/100")
            x2.metric("Correlation", be.CORR_ICON[c["correlation"]])
            x3.metric("Stake", f"{gbp(stake['stake'])} ({stake['pct_bankroll']:.2f}%)")
            st.caption(f"If it lands: return {gbp(stake['stake']*bo)}, profit {gbp(stake['stake']*(bo-1))}. "
                       f"Leg probabilities {l1['model_prob']*100:.0f}% / {l2['model_prob']*100:.0f}%, "
                       f"leg EV {l1['ev_pct']:+.1f}% / {l2['ev_pct']:+.1f}%, "
                       f"confidence {l1['confidence']:.0f} / {l2['confidence']:.0f}.")
            if c["flag"]:
                st.error(c["flag"])
            if stake["stake"] <= 0:
                st.caption("Stake rounds to £0 at these settings.")
            else:
                actual = st.number_input("Actual stake £", min_value=0.0, value=float(stake["stake"]), step=0.5, key=f"as_{key}")
                if st.button("Log this parlay", key=f"lp_{key}", disabled=actual <= 0):
                    ledger.record_parlay(
                        paper=settings["paper_mode"], legs=[l1, l2], bet_type="parlay2", bookmaker="Bet365",
                        parlay_odds_decimal=bo, combined_model_prob=m["combined_prob"], ev_pct=m["ev_pct"],
                        confidence=c["min_conf"], parlay_score=c["parlay_score"], recommended_stake=stake["stake"],
                        actual_stake=actual, model_version=be.MODEL_VERSION)
                    st.success("Parlay logged separately from singles, original prices locked.")
            st.divider()

        show("Safest Double", "safest", "Maximises the chance BOTH legs win, with strict leg thresholds, low correlation only.")
        show("Best Value Double", "best_value", "Best overall balance of probability, EV, confidence, correlation and price.")
        show("Big Payout Double", "big_payout", "Higher return, lower probability - but both legs must still be +EV and credible.")

        with st.expander("Why each prop on the board did / didn't qualify"):
            prof = [("Standard", settings["leg_min_prob"], settings["leg_min_ev"], settings["leg_min_conf"]),
                    ("Safest", settings["safest_min_prob"], settings["safest_min_ev"], settings["safest_min_conf"])]
            for r in priced:
                bits = []
                for name, p_, e_, c_ in prof:
                    why = be.leg_failures(r, p_, e_, c_)
                    bits.append(f"{name}: " + ("qualifies" if not why else "; ".join(why)))
                st.markdown(f"**{r['player']}** {r['side']} {r['line']} {r['market']}")
                for b_ in bits:
                    st.caption(b_)

# ================================================================ MY BETS
RESULT_LABELS = {"win": "Won", "loss": "Lost", "push": "Push", "void": "Void"}
TYPE_FILTERS = {"Singles": "single", "2-Leg Parlays": "parlay2", "SGPs": "sgp", "Larger Parlays": "parlayN"}


def bet_text(b):
    if b["bet_type"] == "single":
        return f"{b['player']} {b['direction']} {b['line']} {b['market']}"
    legs = b["legs_json"] or []
    return " + ".join(f"{l['player']} {l['side']} {l['line']}" for l in legs) or str(b["player"])


with tabs[5]:
    st.subheader("My Bets")
    view_paper = st.radio("Show", ["Live bets", "Paper bets"], horizontal=True) == "Paper bets"
    df = ledger_df
    st.metric("Bankroll", gbp(bankroll), help="Starting bankroll + settled LIVE profit/loss (paper bets excluded).")

    bad = ledger.verify_integrity()
    if bad:
        st.error(f"{len(bad)} bet(s) have original details that no longer match their lock hash. Investigate.")

    view = df[df["paper"].astype(bool) == view_paper] if len(df) else df
    open_ = view[view["status"] == "open"] if len(view) else view
    sub_open, sub_hist, sub_perf = st.tabs([f"Open ({len(open_)})", "History", "Performance"])

    # ---------------------------------------------------------------- OPEN
    with sub_open:
        if open_.empty:
            st.caption("No open bets.")
        for _, b in open_.iterrows():
            label = (f"{b['player']} {b['direction']} {b['line']} {b['market']} @ {b['odds_decimal']:.2f}"
                     if b["bet_type"] == "single" else f"{b['bet_type']}: {b['player']}")
            with st.expander(f"{label}  |  stake {gbp(float(b['actual_stake'] or 0))}"):
                st.caption(f"Logged {str(b['created_at'])[:16]} | model {b['model_version']} | EV {float(b['ev_pct']):+.1f}% | "
                           f"confidence {float(b['confidence']):.0f}")
                if b["bet_type"] == "single":
                    cl1, cl2 = st.columns(2)
                    cline = cl1.number_input("Closing line", value=float(b["line"]), step=0.5, key=f"cl_{b['bet_id']}")
                    codds = cl2.text_input("Closing odds", key=f"co_{b['bet_id']}", placeholder="1.85")
                    if st.button("Save closing line", key=f"scl_{b['bet_id']}") and codds:
                        try:
                            ledger.set_closing_single(b["bet_id"], cline, parse_odds(codds)); st.rerun()
                        except ValueError as e:
                            st.error(str(e))
                    res = st.selectbox("Result", ["win", "loss", "push", "void"], key=f"res_{b['bet_id']}")
                    if st.button("Settle", key=f"set_{b['bet_id']}"):
                        ledger.settle_single(b["bet_id"], res); st.rerun()
                else:
                    legs = b["legs_json"] or []
                    results = []
                    for j, l in enumerate(legs):
                        st.markdown(f"Leg {j+1}: {l['player']} {l['side']} {l['line']} {l['market']} @ {l['odds']:.2f}")
                        results.append(st.selectbox(f"Leg {j+1} result", ["win", "loss", "push", "void"], key=f"lr_{b['bet_id']}_{j}"))
                        k1, k2 = st.columns(2)
                        cod = k2.text_input("Closing odds", key=f"lco_{b['bet_id']}_{j}", placeholder="1.70")
                        if cod and st.button("Save closing", key=f"lsc_{b['bet_id']}_{j}"):
                            try:
                                ledger.set_closing_leg(b["bet_id"], j, float(l["line"]), parse_odds(cod)); st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                    if st.button("Settle parlay", key=f"sp_{b['bet_id']}"):
                        ledger.settle_parlay(b["bet_id"], results); st.rerun()

        st.markdown("#### Exposure (open bets)")
        exp = be.exposure_summary(open_)
        for w in exp["warnings"]:
            st.warning(w)
        for name, t in exp["tables"].items():
            with st.expander(f"By {name}"):
                st.dataframe(t, hide_index=True, width="stretch")

    # ---------------------------------------------------------------- HISTORY
    with sub_hist:
        if view.empty:
            st.caption("No bets logged yet.")
        else:
            h = view.copy()
            h["when"] = pd.to_datetime(h["settled_at"].fillna(h["created_at"]), errors="coerce", utc=True)

            c1, c2 = st.columns(2)
            status_f = c1.selectbox("Status", ["Settled", "Open", "All"], key="hist_status")
            result_f = c2.selectbox("Result", ["All", "Won", "Lost", "Push", "Void"], key="hist_result")
            c3, c4 = st.columns(2)
            type_f = c3.selectbox("Bet type", ["All"] + list(TYPE_FILTERS), key="hist_type")
            period_f = c4.selectbox("Period", ["All time", "Last 7 days", "Last 30 days", "Last 90 days"], key="hist_period")
            search_f = st.text_input("Search player, market or game", key="hist_search")

            if status_f == "Settled":
                h = h[h["status"] == "settled"]
            elif status_f == "Open":
                h = h[h["status"] == "open"]
            if result_f != "All":
                inv = {v: k for k, v in RESULT_LABELS.items()}
                h = h[h["result"] == inv[result_f]]
            if type_f != "All":
                h = h[h["bet_type"] == TYPE_FILTERS[type_f]]
            if period_f != "All time":
                days = int(period_f.split()[1])
                h = h[h["when"] >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)]
            if search_f.strip():
                q = search_f.strip().lower()
                hay = (h["player"].fillna("") + " " + h["market"].fillna("") + " " + h["game"].fillna("")).str.lower()
                h = h[hay.str.contains(q, regex=False)]
            h = h.sort_values("when", ascending=False)

            settled = h[h["status"] == "settled"]
            stk = pd.to_numeric(settled["actual_stake"], errors="coerce").fillna(0)
            prf = pd.to_numeric(settled["profit"], errors="coerce").fillna(0)
            w_, l_, p_ = (int((settled["result"] == x).sum()) for x in ("win", "loss", "push"))
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Bets", len(h))
            m2.metric("W-L-P", f"{w_}-{l_}-{p_}")
            m3.metric("Profit", gbp(float(prf.sum())))
            m4.metric("ROI", f"{(prf.sum() / stk.sum() * 100 if stk.sum() else 0):+.1f}%")

            if h.empty:
                st.info("No bets match those filters.")
            else:
                local = h["when"].dt.tz_convert("Europe/London")
                table = pd.DataFrame({
                    "Date": local.dt.strftime("%d %b %H:%M"),
                    "Type": h["bet_type"].map({v: k for k, v in TYPE_FILTERS.items()}).fillna(h["bet_type"]),
                    "Bet": [bet_text(b) for _, b in h.iterrows()],
                    "Odds": pd.to_numeric(h["odds_decimal"].fillna(h["parlay_odds_decimal"]), errors="coerce").round(2),
                    "Stake £": pd.to_numeric(h["actual_stake"], errors="coerce").round(2),
                    "Result": h["result"].map(RESULT_LABELS).fillna("Open"),
                    "Profit £": pd.to_numeric(h["profit"], errors="coerce").round(2),
                    "EV %": pd.to_numeric(h["ev_pct"], errors="coerce").round(1),
                    "Model %": (pd.to_numeric(h["model_prob"], errors="coerce") * 100).round(1),
                    "CLV %": pd.to_numeric(h["clv_pct"], errors="coerce").round(1),
                    "Model": h["model_version"],
                }).reset_index(drop=True)
                st.dataframe(table, hide_index=True, width="stretch")
                st.download_button("Download these as CSV", table.to_csv(index=False), "my_bets.csv", "text/csv")

                st.markdown("#### Inspect a bet")
                rows = list(h.iterrows())
                idx = st.selectbox("Pick one", range(len(rows)), key="hist_pick",
                                   format_func=lambda i: f"{table.loc[i, 'Date']} | {table.loc[i, 'Bet'][:48]} | {table.loc[i, 'Result']}")
                b = rows[idx][1]
                bid = b["bet_id"]
                st.markdown(f"**Original bet (locked)** - logged {str(b['created_at'])[:16]} UTC, model {b['model_version']}")
                a1, a2, a3 = st.columns(3)
                a1.metric("Bookmaker", b["bookmaker"] or "-")
                a2.metric("Odds", f"{float(b['odds_decimal'] if b['bet_type'] == 'single' else b['parlay_odds_decimal']):.2f}")
                a3.metric("Stake", gbp(float(b["actual_stake"] or 0)))
                a1, a2, a3 = st.columns(3)
                a1.metric("Model prob", f"{float(b['model_prob'])*100:.1f}%")
                a2.metric("EV at bet", f"{float(b['ev_pct']):+.1f}%")
                a3.metric("Confidence", f"{float(b['confidence']):.0f}")
                st.caption(f"Recommended stake was {gbp(float(b['recommended_stake'] or 0))}"
                           + (f" | Line {b['line']}" if b["bet_type"] == "single" else ""))
                if b["bet_type"] == "single":
                    if pd.notna(b["closing_odds_decimal"]):
                        st.caption(f"Closing line {b['closing_line']} @ {float(b['closing_odds_decimal']):.2f} | "
                                   f"CLV {float(b['clv_pct']):+.1f}% | line moved in our favour: {b['line_moved_favourably']}")
                    else:
                        st.caption("No closing line recorded.")
                else:
                    for j, l in enumerate(b["legs_json"] or []):
                        st.caption(f"Leg {j+1}: {l['player']} {l['side']} {l['line']} {l['market']} @ {l['odds']:.2f} - "
                                   f"{RESULT_LABELS.get(l.get('result'), 'open')}"
                                   + (f" | closed @ {l['closing_odds_decimal']:.2f}" if l.get("closing_odds_decimal") else ""))
                if b["status"] == "settled":
                    st.markdown(f"**Result: {RESULT_LABELS.get(b['result'], b['result'])}** - "
                                f"returned {gbp(float(b['return_amount'] or 0))}, profit {gbp(float(b['profit'] or 0))}")
                    with st.expander("Settled it wrong? Correct the result"):
                        st.caption("Profit is recalculated from the original, locked odds and stake.")
                        opts = ["win", "loss", "push", "void"]
                        if b["bet_type"] == "single":
                            new = st.selectbox("Correct result", opts, index=opts.index(b["result"]), key=f"hfix_{bid}")
                            if st.button("Apply correction", key=f"hfixb_{bid}"):
                                ledger.settle_single(bid, new); st.rerun()
                        else:
                            legs = b["legs_json"] or []
                            news = [st.selectbox(f"Leg {j+1}", opts, index=opts.index(l.get("result") or "win"),
                                                 key=f"hfix_{bid}_{j}") for j, l in enumerate(legs)]
                            if st.button("Apply correction", key=f"hfixb_{bid}"):
                                ledger.settle_parlay(bid, news); st.rerun()
                note = st.text_area("Notes", value=b["notes"] or "", key=f"hnote_{bid}")
                if st.button("Save note", key=f"hnoteb_{bid}"):
                    ledger.add_note(bid, note); st.rerun()

    # ---------------------------------------------------------------- PERFORMANCE
    with sub_perf:
        bt = perf.by_type(df, view_paper)
        if not bt:
            st.caption("No settled bets yet.")
        for name, s in bt.items():
            st.markdown(f"**{name}**")
            a1, a2, a3 = st.columns(3)
            a1.metric("Bets", s["bets"]); a2.metric("Win rate", f"{s['win_rate']:.0f}%"); a3.metric("ROI", f"{s['roi_pct']:+.1f}%")
            a1, a2, a3 = st.columns(3)
            a1.metric("Profit", gbp(s["profit"])); a2.metric("Staked", gbp(s["staked"]))
            a3.metric("Avg CLV", f"{s['avg_clv']:+.1f}%" if s["avg_clv"] is not None else "n/a")
            st.caption(f"Avg odds {s['avg_odds']:.2f} | avg EV {s['avg_ev']:+.1f}% | avg model prob {s['avg_model_prob']:.0f}% | "
                       f"avg confidence {s['avg_confidence']:.0f} | max losing streak {s['max_losing_streak']} | "
                       f"max drawdown {gbp(s['max_drawdown'])}"
                       + (f" | avg bet score {s['avg_bet_score']:.0f}" if s["avg_bet_score"] else "")
                       + (f" | avg parlay score {s['avg_parlay_score']:.0f}" if s["avg_parlay_score"] else ""))
        curve = perf.profit_curve(df, view_paper)
        if not curve.empty:
            st.line_chart(curve.set_index("settled_at"))
        for label, by in [("By market", "market"), ("By EV band", "ev_band"), ("By probability band", "prob_band"),
                          ("By position", "position"), ("By model version", "model_version")]:
            t = perf.breakdown(df, view_paper, by)
            if not t.empty:
                with st.expander(label):
                    st.dataframe(t, hide_index=True, width="stretch")
        with st.expander("Calibration: did the model's probabilities come true?"):
            ct = be.calibration_table(df, live_only=not view_paper) if len(df) else pd.DataFrame()
            if ct.empty:
                st.caption("Needs settled singles. Until a bucket has 30+ results it is ignored (neutral).")
            else:
                ct = ct.assign(bucket=ct["bucket"].astype(str), predicted=(ct["predicted"] * 100).round(1),
                               actual=(ct["actual"] * 100).round(1))
                st.dataframe(ct, hide_index=True, width="stretch")
        clv_rows = view[pd.to_numeric(view["clv_pct"], errors="coerce").notna()] if len(view) else view
        if len(clv_rows):
            moved = clv_rows["line_moved_favourably"].dropna()
            st.caption(f"CLV recorded on {len(clv_rows)} bets. Line moved in the model's direction on "
                       f"{(moved.astype(bool).mean()*100 if len(moved) else 0):.0f}% of those with a line move.")

# ================================================================ SETTINGS
with tabs[6]:
    st.subheader("Bankroll & risk settings")
    st.caption(f"Model version {be.MODEL_VERSION} | storage: {ledger.b.name}")
    with st.form("settings_form"):
        st.markdown("**Bankroll**")
        sb = st.number_input("Starting bankroll £", min_value=0.0, value=float(settings["starting_bankroll"]), step=50.0)
        ov = st.number_input("Current bankroll override £ (0 = starting + live profit/loss)", min_value=0.0,
                             value=float(settings["current_bankroll_override"]), step=50.0)
        up = st.number_input("Unit size (% of bankroll)", min_value=0.1, value=float(settings["unit_pct"]), step=0.1)
        st.markdown("**Limits**")
        ms = st.number_input("Max single bet (% of bankroll)", min_value=0.1, value=float(settings["max_single_pct"]), step=0.1)
        mp = st.number_input("Max parlay stake (% of bankroll)", min_value=0.05, value=float(settings["max_parlay_pct"]), step=0.05)
        md = st.number_input("Max daily exposure (% of bankroll)", min_value=0.5, value=float(settings["max_daily_exposure_pct"]), step=0.5)
        kf = st.slider("Kelly fraction", 0.05, 0.5, float(settings["kelly_fraction"]), 0.05)
        paper = st.checkbox("Paper trading mode", value=bool(settings["paper_mode"]))
        st.markdown("**Parlay Hunter leg thresholds**")
        c1, c2, c3 = st.columns(3)
        lp = c1.number_input("Std min prob", 0.3, 0.95, float(settings["leg_min_prob"]), 0.01)
        le = c2.number_input("Std min EV %", 0.0, 50.0, float(settings["leg_min_ev"]), 0.5)
        lc = c3.number_input("Std min conf", 0, 100, int(settings["leg_min_conf"]), 1)
        sp, se, sc = st.columns(3)
        s_p = sp.number_input("Safest min prob", 0.3, 0.95, float(settings["safest_min_prob"]), 0.01)
        s_e = se.number_input("Safest min EV %", 0.0, 50.0, float(settings["safest_min_ev"]), 0.5)
        s_c = sc.number_input("Safest min conf", 0, 100, int(settings["safest_min_conf"]), 1)
        bp, be_, bc = st.columns(3)
        b_p = bp.number_input("Big min prob", 0.3, 0.95, float(settings["big_min_prob"]), 0.01)
        b_e = be_.number_input("Big min EV %", 0.0, 50.0, float(settings["big_min_ev"]), 0.5)
        b_c = bc.number_input("Big min conf", 0, 100, int(settings["big_min_conf"]), 1)
        bo1, bo2 = st.columns(2)
        b_odds = bo1.number_input("Big payout min price", 1.5, 20.0, float(settings["big_min_odds"]), 0.1)
        b_cp = bo2.number_input("Big payout min combined prob", 0.05, 0.9, float(settings["big_min_combined_prob"]), 0.01)
        sg = st.checkbox("Allow same-game pairs (flagged: correlation not modelled; never used for Safest)",
                         value=bool(settings["allow_same_game"]))
        if st.form_submit_button("Save settings"):
            new = {"starting_bankroll": sb, "current_bankroll_override": ov, "unit_pct": up, "max_single_pct": ms,
                   "max_parlay_pct": mp, "max_daily_exposure_pct": md, "kelly_fraction": kf, "paper_mode": paper,
                   "leg_min_prob": lp, "leg_min_ev": le, "leg_min_conf": lc, "safest_min_prob": s_p,
                   "safest_min_ev": s_e, "safest_min_conf": s_c, "big_min_prob": b_p, "big_min_ev": b_e,
                   "big_min_conf": b_c, "big_min_odds": b_odds, "big_min_combined_prob": b_cp, "allow_same_game": sg}
            ledger.set_setting("settings", new)
            st.success("Saved.")
            st.rerun()
    st.caption(f"Current bankroll in use: {gbp(bankroll)} (live P/L to date {gbp(live_pl)}). "
               f"1 unit = {gbp(bankroll*settings['unit_pct']/100)}.")
