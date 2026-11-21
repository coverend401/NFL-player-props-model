"""Read-only slate-date disclosure; never changes a release or forecast."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from sgo_research.contracts import utc


def stale_sunday_notice(slate, release, now):
    today = now.astimezone(ZoneInfo("Europe/London")).date()
    sunday = today + timedelta(days=(6 - today.weekday()) % 7)
    dates = sorted(
        {
            utc(k).astimezone(ZoneInfo("Europe/London")).date()
            for k in release["game_kickoffs"].values()
        }
    )
    if sunday in dates:
        return None
    weeks = ", ".join(str(int(w)) for w in sorted(slate.week.unique()))
    span = f"{dates[0]:%d %b}–{dates[-1]:%d %b %Y}" if dates else "no fixtures"
    return f"Stale forecast slate: loaded week {weeks}, dated {span}. No forecasts are loaded for Sunday {sunday:%d %B %Y}. This is not the current Sunday slate; a reviewed forecast refresh is required. Old fixtures must not be treated as current picks."
