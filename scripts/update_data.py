"""Fetch recorded player statistics through the current NFL (not calendar) season."""

from pathlib import Path
import nflreadpy as nfl
from nflreadpy.utils_date import get_current_season


def update_data(output_dir="data"):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # January/February still belong to the preceding NFL season. Asking for
    # next season's nonexistent stats would abort a normal January release.
    season = get_current_season()
    years = list(range(2019, season + 1))
    frame = nfl.load_player_stats(seasons=years).to_pandas()
    frame = frame.rename(columns={"passing_interceptions": "interceptions"})
    frame.to_parquet(output_dir / "weekly_player_data.parquet", index=False)
    print(f"Saved {len(frame)} rows covering {years[0]}-{years[-1]}")


if __name__ == "__main__":
    update_data()
