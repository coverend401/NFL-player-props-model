import streamlit as st
import pandas as pd
import joblib
from scipy.stats import norm
from odds_utils import parse_odds, implied_probability, expected_value, signal_category

st.title("NFL Player Props Model")

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

@st.cache_data
def load_features():
    return pd.read_parquet("data/player_features.parquet")

@st.cache_resource
def load_model(file_label):
    return joblib.load(f"data/model_{file_label}.joblib")

features = load_features()

tab1, tab2 = st.tabs(["Today's Slate", "Single Prop Lookup"])

with tab1:
    st.subheader("This week's projections")
    try:
        slate = pd.read_parquet("data/slate.parquet")
        week_num = slate["week"].iloc[0] if len(slate) else "?"
        st.caption(f"Week {week_num} - {len(slate)} player-market projections")

        market_filter = st.multiselect("Filter by market", sorted(slate["market"].unique()))
        filtered = slate[slate["market"].isin(market_filter)] if market_filter else slate

        st.dataframe(
            filtered.sort_values(["market", "projection"], ascending=[True, False])
            [["market", "player", "team", "opponent", "projection", "season_avg", "games_played_prior"]],
            use_container_width=True,
            hide_index=True,
        )
        st.caption("No bookmaker odds baked in yet - check any interesting projection against "
                   "a real sportsbook price in the Single Prop Lookup tab to see edge and EV.")
    except FileNotFoundError:
        st.warning("Slate not generated yet - run the workflow to build it.")

with tab2:
    st.subheader("Try a prediction")
    market_label = st.selectbox("Market", list(MARKETS.keys()))
    file_label = MARKETS[market_label]

    try:
        bundle = load_model(file_label)
    except FileNotFoundError:
        st.warning(f"No trained model file found yet for {market_label}.")
        st.stop()

    model = bundle["model"]
    resid_std = bundle["resid_std"]
    feature_cols = bundle["features"]
    positions = bundle["positions"]

    eligible = features[features["position"].isin(positions)]
    players = sorted(eligible["player_display_name"].dropna().unique())
    player = st.selectbox("Player", players)

    player_rows = eligible[eligible["player_display_name"] == player].dropna(subset=feature_cols)
    if player_rows.empty:
        st.warning("Not enough game history for this player yet.")
        st.stop()

    latest = player_rows.sort_values(["season", "week"]).iloc[-1]
    X = latest[feature_cols].to_frame().T
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
    else:
        st.caption("Enter the odds for the side you're checking to see edge and expected value.")