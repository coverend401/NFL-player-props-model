import streamlit as st
import pandas as pd

st.title("NFL Player Props Model")

@st.cache_data
def load_data():
    return pd.read_parquet("data/weekly_player_data.parquet")

df = load_data()

st.write(f"Loaded {len(df)} rows covering multiple seasons.")
st.dataframe(df.head(20))