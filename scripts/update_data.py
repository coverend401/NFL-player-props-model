import nfl_data_py as nfl
import pandas as pd
import os

os.makedirs("data", exist_ok=True)

years = list(range(2019, 2025))
df = nfl.import_weekly_data(years)
df.to_parquet("data/weekly_player_data.parquet", index=False)

print(f"Saved {len(df)} rows covering {years[0]}–{years[-1]}")