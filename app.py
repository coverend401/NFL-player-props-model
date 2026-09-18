import streamlit as st
import pandas as pd
import nfl_data_py as nfl

st.title("NFL Player Props Model")

st.write("Pulling 2024 weekly player stats... this may take a moment on first load.")

@st.cache_data
def load_data():
    return nfl.import_weekly_data([2024])

df = load_data()

st.write(f"Loaded {len(df)} rows of player-week data.")
st.dataframe(df.head(20))