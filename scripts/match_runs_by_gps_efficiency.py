#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import pandas as pd
    from dateutil import parser as dtparser
except ImportError as exc:
    raise SystemExit("Missing dependency. Install with: python -m pip install numpy pandas python-dateutil\n" + str(exc))

ROOT = Path(__file__).resolve().parents[1]
STREAM_DIR = ROOT / "data" / "strava" / "streams"
ACTIVITIES_PATH = ROOT / "data" / "strava" / "activities_raw.json"
DOCS_DATA = ROOT / "docs" / "data"
DERIVED = ROOT / "data" / "derived"
DOCS_DATA.mkdir(parents=True, exist_ok=True)
DERIVED.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except Exception:
        return False


def clean(x: Any, nd: int = 2) -> float | None:
    if not finite(x):
        return None
    return round(float(x), nd)


def parse_date(value: Any) -> str | None:
    try:
        d = dtparser.isoparse(str(value))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.date().isoformat()
    except Exception:
        return None


def stream_array(streams: dict[str, Any], key: str) -> list[Any] | None:
    item = streams.get(key, {}) if isinstance(streams, dict) else {}
    data = item.get("data") if isinstance(item, dict) else None
    return data if isinstance(data, list) else None


def load_activity_lookup() -> dict[str, dict[str, Any]]:
    activities = read_json(ACTIVITIES_PATH, []) or []
    return {str(a.get("id")): a for a in activities if a.get("id")}


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def route_vector(latlng: list[Any], distance: list[Any] | None, n_points: int) -> np.ndarray | None:
    pts = []
    for p in latlng:
        if isinstance(p, list) and len(p) >= 2 and finite(p[0]) and finite(p[1]):
            pts.append((float(p[0]), float(p[1])))
    if len(pts) < 20:
        return None
    arr = np.asarray(pts, dtype=float)
    if distance is not None and len(distance) >= len(arr):
        x = np.asarray(distance[: len(arr)], dtype=float)
        if not np.all(np.isfinite(x)) or float(np.nanmax(x) - np.nanmin(x)) <= 0:
            x = np.linspace(0, 1, len(arr))
        else:
            x = (x - np.nanmin(x)) / (np.nanmax(x) - np.nanmin(x))
    else:
        x = np.linspace(0, 1, len(arr))
    keep = np.concatenate([[True], np.diff(x) > 1e-8])
    x = x[keep]
    arr = arr[keep]
    if len(arr) < 20:
        return None
    grid = np.linspace(0, 1, n_points)
    lat = np.interp(grid, x, arr[:, 0])
    lon = np.interp(grid, x, arr[:, 1])
    return np.column_stack([lat, lon])


def route_distance_m(a: np.ndarray, b: np.ndarray) -> float:
    forward = haversine_m(a[:, 0], a[:, 1], b[:, 0], b[:, 1])
    rb = b[::-1]
    reverse = haversine_m(a[:, 0], a[:, 1], rb[:, 0], rb[:, 1])
    return float(min(np.nanmedian(forward), np.nanmedian(reverse)))


def activity_metrics(activity: dict[str, Any], streams: dict[str, Any]) -> dict[str, Any] | None:
    dist_km = float(activity.get("distance") or 0) / 1000.0
    elev_m = float(activity.get("total_elevation_gain") or 0)
    moving_min = float(activity.get("moving_time") or 0) / 60.0
    avg_hr = activity.get("average_heartrate")
    if dist_km <= 0 or moving_min <= 0:
        return None
    pace = moving_min / dist_km
    speed_kmh = dist_km / (moving_min / 60.0)
    efficiency = speed_kmh / float(avg_hr) if finite(avg_hr) and float(avg_hr) > 0 else None

    hr_stream = stream_array(streams, "heartrate")
    vel_stream = stream_array(streams, "velocity_smooth")
    moving_stream = stream_array(streams, "moving")
    stream_eff = None
    if hr_stream is not None and vel_stream is not None:
        n = min(len(hr_stream), len(vel_stream), len(moving_stream) if moving_stream is not None else len(hr_stream))
        hrs = []
        speeds = []
        for i in range(n):
            if moving_stream is not None and not bool(moving_stream[i]):
                continue
            if finite(hr_stream[i]) and finite(vel_stream[i]) and float(hr_stream[i]) > 0:
                hrs.append(float(hr_stream[i]))
                speeds.append(float(vel_stream[i]) * 3.6)
        if len(hrs) >= 60:
            stream_eff = float(np.nanmean(speeds)) / float(np.nanmean(hrs))

    return {
        "sport_type": activity.get("sport_type") or activity.get("type") or "Run",
        "distance_km": dist_km,
        "elev_gain_m": elev_m,
        "moving_time_min": moving_min,
        "pace_min_per_km": pace,
        "avg_hr": avg_hr,
        "speed_kmh": speed_kmh,
        "efficiency_kmh_per_bpm": efficiency,
        "stream_efficiency_kmh_per_bpm": stream_eff,
    }


def pct_change(latest: Any, baseline: Any) -> float | None:
    if not finite(latest) or not finite(baseline) or float(baseline) == 0:
        return None
    return ((float(latest) - float(baseline)) / float(baseline)) * 100.0


def make_public_group(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = sorted(rows, key=lambda r: r["date"])
    latest = rows[-1]
    previous = rows[:-1]

    def vals(field: str, source: list[dict[str, Any]] = rows) -> list[float]:
        return [float(r[field]) for r in source if finite(r.get(field))]

    median_eff = float(np.median(vals("efficiency_kmh_per_bpm", previous))) if vals("efficiency_kmh_per_bpm", previous) else None
    median_stream_eff = float(np.median(vals("stream_efficiency_kmh_per_bpm", previous))) if vals("stream_efficiency_kmh_per_bpm", previous) else None
    median_pace = float(np.median(vals("pace_min_per_km", previous))) if vals("pace_min_per_km", previous) else None
    median_hr = float(np.median(vals("avg_hr", previous))) if vals("avg_hr", previous) else None

    eff_delta = pct_change(latest.get("efficiency_kmh_per_bpm"), median_eff)
    stream_eff_delta = pct_change(latest.get("stream_efficiency_kmh_per_bpm"), median_stream_eff)
    pace_delta = pct_change(latest.get("pace_min_per_km"), median_pace)
    hr_delta = pct_change(latest.get("avg_hr"), median_hr)

    if finite(eff_delta):
        if float(eff_delta) >= 3:
            signal = "more efficient"
        elif float(eff_delta) <= -3:
            signal = "less efficient"
        else:
            signal = "similar efficiency"
    else:
        signal = "insufficient HR data"

    return {
        "label": label,
        "match_basis": "local GPS route-shape matching; public output contains aggregate efficiency stats only",
        "count": len(rows),
        "first_date": rows[0]["date"],
        "latest_date": latest["date"],
        "typical_distance_km": clean(np.median(vals("distance_km")), 1),
        "typical_elev_gain_m": clean(np.median(vals("elev_gain_m")), 0),
        "latest_pace_min_per_km": clean(latest.get("pace_min_per_km"), 2),
        "latest_avg_hr": clean(latest.get("avg_hr"), 1),
        "latest_efficiency_kmh_per_bpm": clean(latest.get("efficiency_kmh_per_bpm"), 4),
        "best_efficiency_kmh_per_bpm": clean(max(vals("efficiency_kmh_per_bpm")) if vals("efficiency_kmh_per_bpm") else None, 4),
        "latest_vs_previous_median_efficiency_pct": clean(eff_delta, 1),
        "latest_vs_previous_median_stream_efficiency_pct": clean(stream_eff_delta, 1),
        "latest_vs_previous_median_pace_pct": clean(pace_delta, 1),
        "latest_vs_previous_median_hr_pct": clean(hr_delta, 1),
        "fitness_signal": signal,
        "plain_english": "Efficiency is speed divided by heart rate. A positive efficiency change means more speed per heartbeat on the same GPS-matched route.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Local GPS matched runs focused on efficiency; publishes aggregate stats only.")
    parser.add_argument("--threshold-m", type=float, default=90.0)
    parser.add_argument("--min-group-size", type=int, default=2)
    parser.add_argument("--n-points", type=int, default=80)
    args = parser.parse_args()

    activity_lookup = load_activity_lookup()
    candidates = []

    for path in sorted(STREAM_DIR.glob("*.json")):
        payload = read_json(path, {}) or {}
        activity_id = str(payload.get("activity_id") or path.stem)
        activity = activity_lookup.get(activity_id)
        if not activity:
            continue
        sport = activity.get("sport_type") or activity.get("type")
        if sport not in {"Run", "TrailRun"}:
            continue
        streams = payload.get("streams", {})
        latlng = stream_array(streams, "latlng")
        distance = stream_array(streams, "distance")
        if latlng is None:
            continue
        vec = route_vector(latlng, distance, n_points=args.n_points)
        if vec is None:
            continue
        date = parse_date(payload.get("start_date") or activity.get("start_date"))
        if not date:
            continue
        metrics = activity_metrics(activity, streams)
        if metrics is None:
            continue
        candidates.append({"activity_id": activity_id, "date": date, "vector": vec, **metrics})

    if not candidates:
        existing = read_json(DOCS_DATA / "matched_runs.json", None)
        if existing:
            print("[gps-eff-match] No GPS latlng streams available; leaving existing matched_runs.json unchanged.")
            return 0
        write_json(DOCS_DATA / "matched_runs.json", {"generated_at_utc": now_iso(), "method": "No GPS streams available yet. Run fetch_strava_streams.py with --include-latlng.", "items": []})
        return 0

    groups: list[dict[str, Any]] = []
    for c in sorted(candidates, key=lambda x: x["date"]):
        assigned = False
        for g in groups:
            rep = g["representative"]
            gps_dist = route_distance_m(c["vector"], rep["vector"])
            dist_ratio = abs(c["distance_km"] - rep["distance_km"]) / max(rep["distance_km"], 0.01)
            elev_abs = abs(c["elev_gain_m"] - rep["elev_gain_m"])
            if gps_dist <= args.threshold_m and dist_ratio <= 0.12 and elev_abs <= max(60.0, 0.45 * max(rep["elev_gain_m"], 1.0)):
                g["rows"].append(c)
                assigned = True
                break
        if not assigned:
            groups.append({"representative": c, "rows": [c]})

    public_items = []
    debug_rows = []
    for i, g in enumerate(groups, start=1):
        rows = g["rows"]
        for r in rows:
            debug_rows.append({
                "activity_id": r["activity_id"],
                "date": r["date"],
                "local_group": i,
                "distance_km": clean(r["distance_km"], 2),
                "elev_gain_m": clean(r["elev_gain_m"], 0),
                "pace_min_per_km": clean(r["pace_min_per_km"], 2),
                "avg_hr": clean(r.get("avg_hr"), 1),
                "efficiency_kmh_per_bpm": clean(r.get("efficiency_kmh_per_bpm"), 4),
            })
        if len(rows) >= args.min_group_size:
            public_items.append(make_public_group(f"GPS matched route {len(public_items) + 1}", rows))

    public_items = sorted(public_items, key=lambda x: (x["count"], x["latest_date"]), reverse=True)[:12]

    write_json(DOCS_DATA / "matched_runs.json", {
        "generated_at_utc": now_iso(),
        "method": "Matched locally using GPS route-shape similarity. Public output contains anonymous aggregate efficiency stats only.",
        "privacy": "GPS is used locally only. Published JSON contains no coordinates, polylines, maps, activity IDs, activity names, route names or start/end points.",
        "efficiency_definition": "Primary fitness signal is speed_kmh / average_heart_rate_bpm. Higher is better.",
        "items": public_items,
    })

    debug_csv = DERIVED / "gps_matched_runs_efficiency_debug.csv"
    with debug_csv.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["activity_id", "date", "local_group", "distance_km", "elev_gain_m", "pace_min_per_km", "avg_hr", "efficiency_kmh_per_bpm"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(debug_rows)

    write_json(DERIVED / "gps_matched_runs_efficiency_summary.json", {
        "generated_at_utc": now_iso(),
        "candidate_routes_with_gps": len(candidates),
        "local_groups": len(groups),
        "published_groups": len(public_items),
        "threshold_m": args.threshold_m,
        "debug_csv": str(debug_csv.relative_to(ROOT)),
        "note": "Local debug includes activity IDs but no coordinates. Public docs contain aggregate efficiency stats only.",
    })

    print(f"[gps-eff-match] candidate_routes_with_gps={len(candidates)}")
    print(f"[gps-eff-match] local_groups={len(groups)}")
    print(f"[gps-eff-match] published_groups={len(public_items)}")
    print("[gps-eff-match] wrote docs/data/matched_runs.json")
    print(f"[gps-eff-match] wrote {debug_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
