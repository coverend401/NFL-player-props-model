import nflreadpy as nfl
import pandas as pd
import os
from datetime import datetime

os.makedirs("data", exist_ok=True)

current_year = datetime.now().year
years = list(range(2019, current_year + 1))
df = nfl.load_player_stats(seasons=years).to_pandas()
df = df.rename(columns={"passing_interceptions": "interceptions"})
df.to_parquet("data/weekly_player_data.parquet", index=False)

print(f"Saved {len(df)} rows covering {years[0]}-{years[-1]}")