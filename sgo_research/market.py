"""Research benchmarks only. No consensus pricing, forecast adjustment or selection."""

from collections import defaultdict
from datetime import timedelta
from statistics import median

from .analysis import comparisons
from .contracts import utc

US_BOOKS = ("fanduel", "draftkings", "betmgm")


def benchmarks(snapshot, slate, release, now):
    rows, issues = comparisons(snapshot, slate, release, now)
    groups = defaultdict(list)
    for row in rows:
        # Both sides must be present and coherent. One book contributes one line.
        if (
            row.get("projection") is None
            or row["bookmaker"] not in US_BOOKS
            or not row.get("primary_scope_verified")
            or not row.get("authenticated_response")
        ):
            continue
        try:
            updated, captured = (
                utc(row["provider_updated_at"]),
                utc(row["retrieved_at"]),
            )
            cutoff = utc(row["kickoff_at"]) - timedelta(minutes=60)
        except ValueError:
            continue
        if not updated <= captured <= now <= cutoff:
            continue
        if (now - updated).total_seconds() > 900 or (
            now - captured
        ).total_seconds() > 900:
            continue
        if any(
            x in row["comparison_status"]
            for x in (
                "missing_same_line_opposite_side",
                "opposite_side_stale_or_invalid",
                "forecast_",
                "invalid_forecast",
                "future_provider_timestamp",
            )
        ):
            continue
        groups[(row["game_id"], row["player_id"], row["model_market"])].append(row)
    result = []
    for (gid, pid, market), candidates in groups.items():
        books = {}
        for book in US_BOOKS:
            own = [r for r in candidates if r["bookmaker"] == book]
            lines = {r["line"] for r in own}
            if len(lines) != 1 or {r["side"] for r in own} != {"Over", "Under"}:
                continue
            # Preserve both exact definitions and timestamps; never pick a best price.
            books[book] = {"line": own[0]["line"], "quotes": own}
        if not books:
            continue
        row = candidates[0]
        center = median(b["line"] for b in books.values())
        delta = row["projection"] - center
        percent = 100 * delta / abs(center) if center else None
        result.append(
            {
                "game_id": gid,
                "player_id": pid,
                "player": row["player"],
                "market": market,
                "projection": row["projection"],
                "median_line": center,
                "difference": delta,
                "absolute_difference": abs(delta),
                "percentage_difference": percent,
                "book_count": len(books),
                "books": books,
                "label": "multi-book median"
                if len(books) > 1
                else "single-book benchmark",
                "substantial_disagreement": percent is not None and abs(percent) >= 20,
                "oldest_update": min(
                    q["provider_updated_at"]
                    for b in books.values()
                    for q in b["quotes"]
                ),
                "retrieved_at": snapshot["retrieved_at"],
            }
        )
    return sorted(
        result, key=lambda r: abs(r["percentage_difference"] or 0), reverse=True
    ), issues
