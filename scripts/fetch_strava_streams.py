#!/usr/bin/env python3
"""
RunMetrics local Strava stream fetcher.

Purpose:
- Fetch per-activity telemetry streams into data/strava/streams/*.json.
- Keep stream data local/private and gitignored.
- Default stream keys avoid lat/lng for privacy and file size.
- Intended as the first batch toward threshold/HR-drift analysis.

Default stream keys:
  time,distance,altitude,velocity_smooth,heartrate,cadence,moving,grade_smooth

Optional:
  --include-latlng  adds latlng to the stream request, still local-only.

This script does not write anything to docs/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time as time_mod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    import requests
    from dateutil import parser as dtparser
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install with:\n"
        "  python -m pip install requests python-dateutil python-dotenv\n"
        f"Original error: {exc}"
    )

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_PATH = ROOT / "data" / "strava" / "activities_raw.json"
STREAM_DIR = ROOT / "data" / "strava" / "streams"
MANIFEST_PATH = ROOT / "data" / "strava" / "streams_manifest.json"
SUMMARY_PATH = ROOT / "data" / "derived" / "stream_coverage.json"
STATE_PATH = ROOT / "data" / "state.json"

DEFAULT_KEYS = [
    "time",
    "distance",
    "altitude",
    "velocity_smooth",
    "heartrate",
    "cadence",
    "moving",
    "grade_smooth",
]
RUN_SPORTS = {"Run", "TrailRun"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_env() -> None:
    env_path = ROOT / ".env"
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
        return
    except Exception:
        pass

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing {name}. Put STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET and "
            "STRAVA_REFRESH_TOKEN in .env or your shell environment."
        )
    return value


def refresh_access_token() -> str:
    payload = {
        "client_id": env_required("STRAVA_CLIENT_ID"),
        "client_secret": env_required("STRAVA_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": env_required("STRAVA_REFRESH_TOKEN"),
    }
    r = requests.post("https://www.strava.com/api/v3/oauth/token", data=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"No access_token in Strava response. Keys: {sorted(data)}")

    state = read_json(STATE_PATH, {}) or {}
    state.update({
        "updated_at": utc_now().isoformat(),
        "strava_token_expires_at": data.get("expires_at"),
    })
    write_json(STATE_PATH, state)
    return token


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = dtparser.isoparse(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def stream_path(activity_id: int | str) -> Path:
    return STREAM_DIR / f"{activity_id}.json"


def activity_has_hr(a: dict[str, Any]) -> bool:
    if a.get("has_heartrate") is True:
        return True
    return a.get("average_heartrate") is not None or a.get("max_heartrate") is not None


def select_activities(activities: list[dict[str, Any]], after_days: int, include_no_hr: bool) -> list[dict[str, Any]]:
    cutoff = utc_now() - timedelta(days=after_days)
    selected = []
    for a in activities:
        aid = a.get("id")
        if not aid:
            continue
        sport = a.get("sport_type") or a.get("type")
        if sport not in RUN_SPORTS:
            continue
        if not include_no_hr and not activity_has_hr(a):
            continue
        start = parse_dt(a.get("start_date"))
        if start is None or start < cutoff:
            continue
        selected.append(a)
    selected.sort(key=lambda x: str(x.get("start_date", "")), reverse=True)
    return selected


def normalise_stream_response(data: Any) -> dict[str, Any]:
    # Strava can return key_by_type=true dicts, while some wrappers/docs show lists.
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        out = {}
        for item in data:
            if isinstance(item, dict) and item.get("type"):
                out[item["type"]] = item
        return out
    return {"unexpected_response": data}


def fetch_streams(activity_id: int | str, access_token: str, keys: list[str]) -> dict[str, Any]:
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    params = {
        "keys": ",".join(keys),
        "key_by_type": "true",
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(url, headers=headers, params=params, timeout=30)

    if r.status_code == 429:
        raise RuntimeError("Strava rate limit reached (HTTP 429). Try again later.")
    if r.status_code in {401, 403}:
        raise RuntimeError(f"Strava auth/scope error HTTP {r.status_code}: {r.text[:300]}")
    r.raise_for_status()
    return normalise_stream_response(r.json())


def summarise_stream_file(path: Path) -> dict[str, Any]:
    data = read_json(path, {}) or {}
    streams = data.get("streams", {})
    keys = sorted(streams.keys()) if isinstance(streams, dict) else []

    def npoints(key: str) -> int | None:
        try:
            arr = streams.get(key, {}).get("data")
            return len(arr) if isinstance(arr, list) else None
        except Exception:
            return None

    return {
        "activity_id": data.get("activity_id"),
        "fetched_at_utc": data.get("fetched_at_utc"),
        "keys": keys,
        "has_heartrate": "heartrate" in keys,
        "has_distance": "distance" in keys,
        "has_velocity": "velocity_smooth" in keys,
        "has_grade": "grade_smooth" in keys,
        "has_latlng": "latlng" in keys,
        "points_time": npoints("time"),
        "points_heartrate": npoints("heartrate"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch local-only Strava streams for recent Run/TrailRun activities.")
    parser.add_argument("--after-days", type=int, default=120, help="Only consider activities from the last N days. Default: 120.")
    parser.add_argument("--max-new", type=int, default=25, help="Maximum new stream files to fetch in this run. Default: 25.")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if stream file already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched without calling Strava.")
    parser.add_argument("--include-latlng", action="store_true", help="Also fetch GPS lat/lng stream. Local-only, not published.")
    parser.add_argument("--include-no-hr", action="store_true", help="Fetch streams for activities without summary HR metadata.")
    parser.add_argument("--sleep", type=float, default=0.4, help="Seconds to sleep between Strava requests. Default: 0.4.")
    args = parser.parse_args()

    load_env()
    activities = read_json(ACTIVITIES_PATH, []) or []
    if not activities:
        raise SystemExit(
            f"No activities found at {ACTIVITIES_PATH}. Run scripts/update_static_site.py first."
        )

    selected = select_activities(activities, args.after_days, args.include_no_hr)
    missing = [a for a in selected if args.force or not stream_path(a["id"]).exists()]
    to_fetch = missing[: max(0, args.max_new)]

    print(f"[streams] Activities in cache: {len(activities)}")
    print(f"[streams] Eligible recent run activities: {len(selected)}")
    print(f"[streams] Missing/selected stream files: {len(missing)}")
    print(f"[streams] Will fetch this run: {len(to_fetch)}")

    if args.dry_run:
        for a in to_fetch:
            print(f"[dry-run] {a.get('start_date')} activity_id={a.get('id')} sport={a.get('sport_type') or a.get('type')}")
        return 0

    if not to_fetch:
        print("[streams] Nothing new to fetch.")
    else:
        token = refresh_access_token()
        keys = list(DEFAULT_KEYS)
        if args.include_latlng and "latlng" not in keys:
            keys.append("latlng")

        fetched = 0
        errors = []
        for a in to_fetch:
            aid = a["id"]
            try:
                streams = fetch_streams(aid, token, keys)
                payload = {
                    "activity_id": aid,
                    "sport_type": a.get("sport_type") or a.get("type"),
                    "start_date": a.get("start_date"),
                    "fetched_at_utc": utc_now().isoformat(),
                    "requested_keys": keys,
                    "streams": streams,
                }
                write_json(stream_path(aid), payload)
                fetched += 1
                available = ",".join(sorted(streams.keys())) if isinstance(streams, dict) else "unknown"
                print(f"[streams] fetched {aid} keys={available}")
            except Exception as exc:
                msg = f"activity_id={aid}: {exc}"
                errors.append(msg)
                print(f"[streams] ERROR {msg}", file=sys.stderr)
            time_mod.sleep(max(0.0, args.sleep))

        print(f"[streams] Fetched {fetched}; errors {len(errors)}")

    # Always refresh manifest/coverage from whatever is present locally.
    stream_files = sorted(STREAM_DIR.glob("*.json"))
    manifest = [summarise_stream_file(p) for p in stream_files]
    write_json(MANIFEST_PATH, {
        "generated_at_utc": utc_now().isoformat(),
        "stream_file_count": len(stream_files),
        "items": manifest,
    })

    coverage = {
        "generated_at_utc": utc_now().isoformat(),
        "stream_file_count": len(stream_files),
        "with_heartrate": sum(1 for x in manifest if x.get("has_heartrate")),
        "with_distance": sum(1 for x in manifest if x.get("has_distance")),
        "with_velocity": sum(1 for x in manifest if x.get("has_velocity")),
        "with_grade": sum(1 for x in manifest if x.get("has_grade")),
        "with_latlng": sum(1 for x in manifest if x.get("has_latlng")),
        "note": "Local/private stream cache coverage only. Raw streams are not written to docs/.",
    }
    write_json(SUMMARY_PATH, coverage)
    print(f"[streams] Wrote {MANIFEST_PATH}")
    print(f"[streams] Wrote {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
