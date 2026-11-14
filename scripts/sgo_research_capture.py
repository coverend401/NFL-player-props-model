"""Manual future-event coverage test. Never schedules collection or fetches results."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sgo_research.analysis import normalise
from sgo_research.client import Client
from sgo_research.contracts import STAT_MARKETS, Unavailable
from sgo_research.store import Store


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--starts-after", required=True, help="Future ISO timestamp with timezone"
    )
    p.add_argument("--starts-before", required=True)
    p.add_argument("--books", default="williamhill,unibet")
    args = p.parse_args()
    try:
        if not os.environ.get("SPORTSGAMEODDS_API_KEY"):
            raise Unavailable(
                "SPORTSGAMEODDS_API_KEY is not configured; no request made"
            )
        if (
            os.environ.get("SGO_PERSISTENT_VOLUME_APPROVED") != "1"
            or os.environ.get("SGO_PRIVATE_CACHE_TERMS_ACK") != "1"
        ):
            raise Unavailable(
                "Persistent private storage and cache/data-use acknowledgements required"
            )
        path = os.environ.get("SGO_RESEARCH_STORE")
        if not path:
            raise Unavailable("SGO_RESEARCH_STORE must point outside the repository")
        snapshot = Client(
            os.environ["SPORTSGAMEODDS_API_KEY"],
            Store(path, persistent=True),
            terms_ack=True,
            object_cap=int(os.environ.get("SGO_OBJECT_CAP", "2000")),
        ).fetch(args.starts_after, args.starts_before, books=args.books.split(","))
        quotes, issues = normalise(snapshot)
        # Counts only. Private odds, identifiers and account metadata stay local.
        report = {
            "at": datetime.now(UTC).isoformat(),
            "authenticated_response": True,
            "events": len(snapshot["events"]),
            "cache_hit": snapshot["cache_hit"],
            "truncated": snapshot["truncated"],
            "books": sorted({q["bookmaker"] for q in quotes}),
            "markets": {
                stat: sum(q["canonical_stat"] == stat for q in quotes)
                for stat in STAT_MARKETS
            },
            "excluded_records": len(issues),
            "UK_variant_verified": False,
            "retention_and_settlement_activated": False,
        }
        print(json.dumps(report, indent=2))
    except (Unavailable, OSError, ValueError, TypeError, KeyError):
        print(
            "Coverage test stopped: key, free-tier entitlement, schema, persistent quota store or request safety could not be established. No retry, paid fallback or result request."
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
