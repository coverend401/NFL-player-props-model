"""Evidence-only availability overlay; no cleared-player assumptions or model changes."""

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .store import ROOT, Store, encoded, sha

URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
POINTER = ROOT / "weekly_learning_state/availability_current.json"
FIELDS = {
    "timestamp": True,
    "season": {"year": True},
    "injuries": [
        {
            "id": True,
            "abbreviation": True,
            "team": {"abbreviation": True},
            "injuries": [
                {
                    "id": True,
                    "date": True,
                    "status": True,
                    "type": {"name": True, "description": True, "abbreviation": True},
                    "athlete": {
                        "id": True,
                        "displayName": True,
                        "links": [{"href": True}],
                    },
                }
            ],
        }
    ],
}


def collect(store, run_id, mapping, *, get=None):
    import requests

    from .fixture_evidence import metadata_json

    with (get or requests.get)(
        URL, timeout=(5, 30), stream=True, allow_redirects=False
    ) as r:
        if r.status_code != 200:
            raise ValueError(f"Availability source unavailable (HTTP {r.status_code})")
        raw = bytearray()
        for block in r.iter_content(65536):
            raw.extend(block)
            if len(raw) > 12 * 1024 * 1024:
                raise ValueError("Public injury source exceeds 12 MiB bound")
    data = metadata_json(raw, FIELDS)
    import pandas as pd

    observed = pd.Timestamp(datetime.now(UTC))
    published = pd.Timestamp(data.get("timestamp"))
    if (
        data.get("season", {}).get("year")
        != (observed.year - 1 if observed.month < 3 else observed.year)
        or pd.isna(published)
        or published.tzinfo is None
        or not pd.Timedelta(0) <= observed - published <= pd.Timedelta(days=2)
    ):
        raise ValueError(
            "Availability source season/publication freshness is unverified"
        )
    records = []
    unmatched = 0
    for group in data.get("injuries", []):
        for item in group.get("injuries", []):
            athlete = item.get("athlete", {})
            identity = str(athlete.get("id", ""))
            if not identity:
                ids = {
                    m.group(1)
                    for link in athlete.get("links", [])
                    if (
                        m := re.match(
                            r"https://www\.espn\.com/nfl/player/(?:[^?]*/)?id/(\d+)(?:/|$)",
                            str(link.get("href", "")),
                        )
                    )
                }
                if len(ids) == 1:
                    identity = ids.pop()
            player = mapping.get(identity)
            if not player:
                unmatched += 1
                continue
            status = str(
                item.get("status")
                or item.get("type", {}).get("description")
                or item.get("type", {}).get("name")
                or "unknown"
            )
            records.append(
                {
                    "player_id": player,
                    "status": status,
                    "source_date": item.get("date"),
                    "source": URL,
                }
            )
    if not records:
        raise ValueError(
            "No mapped current injury records; no healthy defaults or pointer update"
        )
    at = datetime.now(UTC).isoformat()
    report = {
        "schema": 1,
        "retrieved_at": at,
        "source": URL,
        "source_published_at": published.isoformat(),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "records": records,
        "unmatched": unmatched,
        "default_status": "unverified",
    }
    with store.transaction():
        folder = store.publish(
            "availability", run_id, documents={"report.json": report}
        )
        pointer = {
            "path": str(folder.relative_to(ROOT)),
            "manifest_sha256": sha(folder / "manifest.json"),
        }
        temp = POINTER.with_name(".availability.next.json")
        temp.write_text(encoded(pointer))
        temp.replace(POINTER)
    return {
        "status": "availability_recorded",
        "records": len(records),
        "unmatched": unmatched,
    }


def filter_frame(frame, *, now=None):
    """Only restrict upcoming candidates on explicit evidence; leave history intact."""
    import pandas as pd

    if not POINTER.exists():
        return frame.copy(), {"status": "unverified", "withheld": []}
    now = pd.Timestamp(now or datetime.now(UTC))
    try:
        p = json.loads(POINTER.read_text())
        folder = (ROOT / p["path"]).resolve()
        folder.relative_to(ROOT / "weekly_learning_state/availability")
        if sha(folder / "manifest.json") != p["manifest_sha256"]:
            raise ValueError("Availability pointer changed")
        Store(ROOT / "weekly_learning_state").validate(folder)
        report = json.loads((folder / "report.json").read_text())
        if (
            report["schema"] != 1
            or report["source"] != URL
            or report["default_status"] != "unverified"
            or pd.Timestamp(report["retrieved_at"]) > now
        ):
            raise ValueError("Invalid availability evidence")
        material = {
            r["player_id"]: r
            for r in report["records"]
            if str(r["status"]).strip().lower()
            in ["out", "inactive", "injured reserve", "suspended"]
        }
        upcoming = pd.to_datetime(frame.kickoff_at, utc=True) > now
        withheld = (
            frame.loc[upcoming & frame.player_id.isin(material), "player_id"]
            .unique()
            .tolist()
        )
        result = frame[~(upcoming & frame.player_id.isin(material))].copy()
        return result, {
            "status": "dated_public_reports",
            "retrieved_at": report["retrieved_at"],
            "stale": now - pd.Timestamp(report["retrieved_at"])
            > pd.Timedelta(hours=48),
            "withheld": withheld,
            "default": "unverified; absence is not injury clearance",
        }
    except (OSError, ValueError, KeyError, TypeError):
        # Forecasts remain visible, but pricing must not ignore a corrupt material-risk overlay.
        raise ValueError(
            "Availability evidence failed integrity checks; quoted selections withheld"
        ) from None


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--mapping", required=True)
    a = p.parse_args()
    print(
        encoded(
            collect(
                Store(ROOT / "weekly_learning_state"),
                a.id,
                json.loads(Path(a.mapping).read_text()),
            )
        )
    )
