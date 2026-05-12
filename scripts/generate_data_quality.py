#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DOCS_DATA = ROOT / "docs" / "data"
DERIVED = ROOT / "data" / "derived"
STREAMS = ROOT / "data" / "strava" / "streams"

DERIVED.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def main() -> int:
    activities = read_json(DOCS_DATA / "activities_recent.json", [])
    threshold = read_json(DOCS_DATA / "threshold_history.json", {"items": []})
    drift = read_json(DOCS_DATA / "drift_summary.json", {"items": []})
    matched = read_json(DOCS_DATA / "matched_runs.json", {"items": []})
    run_types = read_json(DOCS_DATA / "run_types.json", {"classified_runs": []})

    stream_files = list(STREAMS.glob("*.json")) if STREAMS.exists() else []

    data_quality = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "activities_recent_public": len(activities),
        "local_stream_files": len(stream_files),
        "threshold_points": len(threshold.get("items") or []),
        "drift_points": len(drift.get("items") or []),
        "matched_route_groups": len(matched.get("items") or []),
        "classified_runs_public": len(run_types.get("classified_runs") or []),
        "note": "Public-safe quality summary only. No activity IDs, GPS, route names or coordinates are exported."
    }

    write_json(DOCS_DATA / "data_quality.json", data_quality)

    debug_path = DERIVED / "run_classification_debug.csv"
    classified = run_types.get("classified_runs") or []

    if classified:
        fields = [
            "date",
            "type",
            "labels",
            "distance_km",
            "duration_min",
            "elev_gain_m",
            "elev_per_km",
            "avg_hr",
            "hr_ratio_to_threshold",
            "pace_min_per_km",
            "efficiency_kmh_per_bpm"
        ]

        with debug_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in classified:
                out = dict(row)
                if isinstance(out.get("labels"), list):
                    out["labels"] = ";".join(out["labels"])
                writer.writerow({k: out.get(k) for k in fields})

        print(f"[quality] wrote {debug_path}")

    print("[quality] wrote docs/data/data_quality.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
