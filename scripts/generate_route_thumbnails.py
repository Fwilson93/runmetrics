#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install with:\n"
        "  python -m pip install numpy matplotlib\n"
        f"Original error: {exc}"
    )

ROOT = Path(__file__).resolve().parents[1]
DEBUG_CSV = ROOT / "data" / "derived" / "gps_matched_runs_efficiency_debug.csv"
STREAM_DIR = ROOT / "data" / "strava" / "streams"
MATCHED_JSON = ROOT / "docs" / "data" / "matched_runs.json"
OUT_DIR = ROOT / "docs" / "assets" / "routes"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def stream_array(streams: dict[str, Any], key: str) -> list[Any] | None:
    item = streams.get(key, {}) if isinstance(streams, dict) else {}
    data = item.get("data") if isinstance(item, dict) else None
    return data if isinstance(data, list) else None


def load_debug_groups() -> dict[int, list[dict[str, str]]]:
    if not DEBUG_CSV.exists():
        raise SystemExit(f"Missing {DEBUG_CSV}. Run scripts/match_runs_by_gps_efficiency.py first.")
    groups: dict[int, list[dict[str, str]]] = {}
    with DEBUG_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                gid = int(row["local_group"])
            except Exception:
                continue
            groups.setdefault(gid, []).append(row)
    return groups


def published_label_to_group(groups: dict[int, list[dict[str, str]]], min_group_size: int = 2) -> dict[str, int]:
    # This mirrors the labelling order in match_runs_by_gps_efficiency.py:
    # iterate local groups in ascending order, publish groups with enough rows,
    # and assign labels GPS matched route 1, 2, 3...
    out = {}
    published_idx = 0
    for gid in sorted(groups):
        if len(groups[gid]) >= min_group_size:
            published_idx += 1
            out[f"GPS matched route {published_idx}"] = gid
    return out


def latlng_to_xy(latlng: list[Any]) -> tuple[np.ndarray, np.ndarray] | None:
    pts = []
    for p in latlng:
        if isinstance(p, list) and len(p) >= 2:
            try:
                lat = float(p[0])
                lon = float(p[1])
            except Exception:
                continue
            if math.isfinite(lat) and math.isfinite(lon):
                pts.append((lat, lon))
    if len(pts) < 20:
        return None

    arr = np.asarray(pts, dtype=float)
    lat0 = float(np.nanmean(arr[:, 0]))
    lon0 = float(np.nanmean(arr[:, 1]))
    # Approx local projection. Coordinates are immediately centred and normalised;
    # the output image contains no absolute coordinate values.
    x = (arr[:, 1] - lon0) * 111_320.0 * math.cos(math.radians(lat0))
    y = (arr[:, 0] - lat0) * 110_540.0
    x = x - np.nanmean(x)
    y = y - np.nanmean(y)
    return x, y


def choose_representative(rows: list[dict[str, str]]) -> str | None:
    # Prefer the latest row with an existing stream file.
    rows_sorted = sorted(rows, key=lambda r: r.get("date", ""), reverse=True)
    for row in rows_sorted:
        aid = str(row.get("activity_id", "")).strip()
        if aid and (STREAM_DIR / f"{aid}.json").exists():
            return aid
    return None


def plot_route(activity_id: str, out_path: Path) -> bool:
    payload = read_json(STREAM_DIR / f"{activity_id}.json", {}) or {}
    streams = payload.get("streams", {})
    latlng = stream_array(streams, "latlng")
    if latlng is None:
        return False
    xy = latlng_to_xy(latlng)
    if xy is None:
        return False
    x, y = xy

    # Normalise into a neat pictographic panel. No axes, no scale, no start/end.
    span_x = float(np.nanmax(x) - np.nanmin(x))
    span_y = float(np.nanmax(y) - np.nanmin(y))
    span = max(span_x, span_y, 1.0)
    x = x / span
    y = y / span

    fig = plt.figure(figsize=(2.8, 1.8), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.plot(x, y, color="#67e8f9", linewidth=3.0, solid_capstyle="round", solid_joinstyle="round")
    ax.plot(x, y, color="#e8eefc", linewidth=1.0, alpha=0.9, solid_capstyle="round", solid_joinstyle="round")
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    pad = 0.08
    ax.set_xlim(float(np.nanmin(x)) - pad, float(np.nanmax(x)) + pad)
    ax.set_ylim(float(np.nanmin(y)) - pad, float(np.nanmax(y)) + pad)
    fig.savefig(out_path, transparent=True)
    plt.close(fig)
    return True


def safe_slug(label: str) -> str:
    m = re.search(r"(\d+)", label)
    if m:
        return f"gps_matched_route_{int(m.group(1)):02d}.png"
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") + ".png"


def main() -> int:
    matched = read_json(MATCHED_JSON, {}) or {}
    items = matched.get("items") or []
    if not items:
        print("[route-thumbs] No matched route items found; nothing to draw.")
        return 0

    groups = load_debug_groups()
    label_map = published_label_to_group(groups)
    generated = 0

    for item in items:
        label = item.get("label")
        gid = label_map.get(label)
        if gid is None:
            continue
        aid = choose_representative(groups.get(gid, []))
        if not aid:
            continue
        filename = safe_slug(label)
        out_path = OUT_DIR / filename
        if plot_route(aid, out_path):
            item["route_image"] = f"./assets/routes/{filename}"
            item["route_image_note"] = "Pictographic route sketch generated locally from GPS; no coordinates, map tiles, start/end markers or activity IDs are published."
            generated += 1

    matched["route_images"] = {
        "generated": generated,
        "privacy": "Images are normalised route silhouettes. They contain no coordinate values, no basemap, no labels, and no start/end markers."
    }
    write_json(MATCHED_JSON, matched)
    print(f"[route-thumbs] generated {generated} route thumbnail PNGs in {OUT_DIR}")
    print("[route-thumbs] updated docs/data/matched_runs.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
