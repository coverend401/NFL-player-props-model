import streamlit as st
import pandas as pd
import joblib
from scipy.stats import norm

st.title("NFL Player Props Model")

MARKETS = {
    "Passing Yards": "passing_yards",
    "Passing Attempts": "passing_attempts",
    "Completions": "completions",
    "Rushing Yards": "rushing_yards",
    "Rushing Attempts": "rushing_attempts",
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
X = latest[feature_cols].values.reshape(1, -1)
prediction = model.predict(X)[0]

st.metric(f"Model projection - {market_label}", f"{prediction:.1f}")

line = st.number_input("Bookmaker line", value=float(round(prediction, 1)), step=0.5)
prob_over = 1 - norm.cdf(line, prediction, resid_std)
prob_under = 1 - prob_over

col1, col2 = st.columns(2)
col1.metric("Model probability Over", f"{prob_over*100:.1f}%")
col2.metric("Model probability Under", f"{prob_under*100:.1f}%")

st.caption(f"Based on data through Season {int(latest['season'])}, Week {int(latest['week'])} "
           f"({int(latest['games_played_prior'])} prior games on record).")