#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    raise SystemExit(
        "Missing dependency. Install with:\n"
        "  python -m pip install numpy pandas python-dateutil\n"
        f"Original error: {exc}"
    )

ROOT = Path(__file__).resolve().parents[1]
STREAM_DIR = ROOT / "data" / "strava" / "streams"
DOCS_DATA = ROOT / "docs" / "data"
DERIVED = ROOT / "data" / "derived"

DOCS_DATA.mkdir(parents=True, exist_ok=True)
DERIVED.mkdir(parents=True, exist_ok=True)


def utc_now() -> str:
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


def clean(x: Any, nd: int = 2) -> float | None:
    try:
        x = float(x)
        if not math.isfinite(x):
            return None
        return round(x, nd)
    except Exception:
        return None


def parse_date(value: Any) -> pd.Timestamp | pd.NaT:
    try:
        d = dtparser.isoparse(str(value))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return pd.Timestamp(d).tz_convert("UTC")
    except Exception:
        return pd.NaT


def get_stream_array(streams: dict[str, Any], key: str) -> list[Any] | None:
    item = streams.get(key, {})
    if not isinstance(item, dict):
        return None
    data = item.get("data")
    return data if isinstance(data, list) else None


def stream_frame(payload: dict[str, Any]) -> pd.DataFrame:
    streams = payload.get("streams", {})
    if not isinstance(streams, dict):
        return pd.DataFrame()

    time_s = get_stream_array(streams, "time")
    hr = get_stream_array(streams, "heartrate")
    if time_s is None or hr is None:
        return pd.DataFrame()

    distance = get_stream_array(streams, "distance")
    velocity = get_stream_array(streams, "velocity_smooth")
    moving = get_stream_array(streams, "moving")
    grade = get_stream_array(streams, "grade_smooth")

    n = min(len(time_s), len(hr))
    for arr in [distance, velocity, moving, grade]:
        if arr is not None:
            n = min(n, len(arr))

    if n < 60:
        return pd.DataFrame()

    df = pd.DataFrame({
        "time_s": pd.to_numeric(time_s[:n], errors="coerce"),
        "hr": pd.to_numeric(hr[:n], errors="coerce"),
        "distance_m": pd.to_numeric(distance[:n], errors="coerce") if distance is not None else np.nan,
        "velocity_mps": pd.to_numeric(velocity[:n], errors="coerce") if velocity is not None else np.nan,
        "moving": [bool(x) for x in moving[:n]] if moving is not None else True,
        "grade_pct": pd.to_numeric(grade[:n], errors="coerce") if grade is not None else np.nan,
    })

    df = df.dropna(subset=["time_s", "hr"]).sort_values("time_s")
    df = df[(df["hr"] >= 60) & (df["hr"] <= 230)]

    if df.empty:
        return df

    # Gentle smoothing only. Keep this deterministic and easy to inspect.
    df["hr_smooth"] = df["hr"].rolling(15, min_periods=1, center=True).median()
    df["speed_smooth"] = df["velocity_mps"].rolling(15, min_periods=1, center=True).median()

    return df.reset_index(drop=True)


def threshold_candidates(df: pd.DataFrame, window_min: int) -> list[dict[str, Any]]:
    if df.empty:
        return []

    window_s = window_min * 60
    t0 = float(df["time_s"].min())
    t1 = float(df["time_s"].max())

    if t1 - t0 < window_s:
        return []

    candidates: list[dict[str, Any]] = []

    # Step every 2 minutes. Simple and inspectable.
    for start in np.arange(t0, t1 - window_s + 1, 120):
        end = start + window_s
        w = df[(df["time_s"] >= start) & (df["time_s"] <= end)]

        # Allow reduced stream resolution, but reject tiny windows.
        if len(w) < window_s * 0.55:
            continue

        moving_frac = float(w["moving"].mean())
        hr_mean = float(w["hr_smooth"].mean())
        hr_std = float(w["hr_smooth"].std(ddof=0))
        hr_range = float(w["hr_smooth"].max() - w["hr_smooth"].min())

        speed = float(w["speed_smooth"].mean()) if w["speed_smooth"].notna().any() else np.nan
        grade_abs = float(w["grade_pct"].abs().mean()) if w["grade_pct"].notna().any() else np.nan
        grade_std = float(w["grade_pct"].std(ddof=0)) if w["grade_pct"].notna().sum() > 1 else np.nan

        # Conservative filters. We want sustained, moving, not obviously noisy, not very hilly.
        if moving_frac < 0.90:
            continue
        if not math.isfinite(hr_mean) or hr_mean < 120:
            continue
        if hr_std > 12 or hr_range > 35:
            continue
        if math.isfinite(speed) and speed < 2.0:
            continue
        if math.isfinite(grade_abs) and grade_abs > 4.0:
            continue
        if math.isfinite(grade_std) and grade_std > 5.0:
            continue

        pace = (1000.0 / speed) / 60.0 if math.isfinite(speed) and speed > 0 else np.nan

        candidates.append({
            "mean_hr": clean(hr_mean, 1),
            "hr_std": clean(hr_std, 1),
            "pace_min_per_km": clean(pace, 2),
            "moving_fraction": clean(moving_frac, 3),
            "grade_abs_mean": clean(grade_abs, 2),
        })

    return candidates


def best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None

    def score(c: dict[str, Any]) -> float:
        return (
            float(c.get("mean_hr") or 0)
            - 0.8 * float(c.get("hr_std") or 0)
            - 0.8 * float(c.get("grade_abs_mean") or 0)
        )

    return max(candidates, key=score)


def drift_estimate(df: pd.DataFrame) -> dict[str, Any] | None:
    if df.empty:
        return None

    moving = df[df["moving"]].copy()
    if moving.empty:
        return None

    duration_s = float(moving["time_s"].max() - moving["time_s"].min())
    if duration_s < 35 * 60:
        return None

    mid = moving["time_s"].min() + duration_s / 2
    first = moving[moving["time_s"] <= mid]
    second = moving[moving["time_s"] > mid]

    if len(first) < 60 or len(second) < 60:
        return None

    def efficiency(part: pd.DataFrame) -> tuple[float, float, float]:
        speed = float(part["speed_smooth"].mean()) if part["speed_smooth"].notna().any() else np.nan
        hr = float(part["hr_smooth"].mean())
        eff = speed / hr if math.isfinite(speed) and hr > 0 else np.nan
        return speed, hr, eff

    s1, h1, e1 = efficiency(first)
    s2, h2, e2 = efficiency(second)

    if not all(math.isfinite(x) for x in [s1, h1, e1, s2, h2, e2]) or e1 <= 0:
        return None

    grade_abs = float(moving["grade_pct"].abs().mean()) if moving["grade_pct"].notna().any() else np.nan

    return {
        "duration_min": clean(duration_s / 60.0, 1),
        "first_half_hr": clean(h1, 1),
        "second_half_hr": clean(h2, 1),
        "hr_rise_bpm": clean(h2 - h1, 1),
        "speed_change_pct": clean(((s2 - s1) / s1) * 100.0, 1),
        "efficiency_change_pct": clean(((e2 - e1) / e1) * 100.0, 1),
        "grade_abs_mean": clean(grade_abs, 2),
        "confidence": "medium" if (math.isfinite(grade_abs) and grade_abs > 3.5) or duration_s < 45 * 60 else "high",
    }


def confidence(n: int) -> str:
    if n >= 8:
        return "high"
    if n >= 4:
        return "medium"
    if n >= 2:
        return "low"
    return "very_low"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-min", type=int, default=20)
    parser.add_argument("--rolling-days", type=int, default=90)
    args = parser.parse_args()

    files = sorted(STREAM_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No stream files found. Run scripts/fetch_strava_streams.py first.")

    per_activity = []
    drift_rows = []

    for path in files:
        payload = read_json(path, {}) or {}
        date = parse_date(payload.get("start_date"))

        if pd.isna(date):
            continue

        df = stream_frame(payload)
        if df.empty:
            continue

        candidates = threshold_candidates(df, args.window_min)
        best = best_candidate(candidates)

        if best:
            best = dict(best)
            best["date"] = pd.Timestamp(date.date())
            best["candidate_count_activity"] = len(candidates)
            per_activity.append(best)

        dr = drift_estimate(df)
        if dr:
            dr["date"] = pd.Timestamp(date.date()).strftime("%Y-%m-%d")
            drift_rows.append(dr)

    threshold_items = []

    if per_activity:
        cdf = pd.DataFrame(per_activity).sort_values("date")
        dates = list(pd.date_range(cdf["date"].min(), cdf["date"].max(), freq="7D"))

        if cdf["date"].max() not in dates:
            dates.append(cdf["date"].max())

        for d in dates:
            window = cdf[
                (cdf["date"] >= d - pd.Timedelta(days=args.rolling_days - 1))
                & (cdf["date"] <= d)
            ]

            if window.empty:
                continue

            # 85th percentile of candidate mean HRs: a conservative threshold-like proxy.
            thr = float(np.nanpercentile(window["mean_hr"].astype(float), 85))
            pace = (
                float(np.nanmedian(window["pace_min_per_km"].astype(float)))
                if window["pace_min_per_km"].notna().any()
                else np.nan
            )
            n = int(len(window))

            threshold_items.append({
                "date": d.strftime("%Y-%m-%d"),
                "threshold_hr_proxy": clean(thr, 1),
                "threshold_pace_proxy_min_per_km": clean(pace, 2),
                "eligible_windows": n,
                "confidence": confidence(n),
                "z1_upper": clean(thr * 0.85, 0),
                "z2_lower": clean(thr * 0.85, 0),
                "z2_upper": clean(thr * 0.89, 0),
                "z3_upper": clean(thr * 0.94, 0),
                "z4_upper": clean(thr * 0.99, 0),
                "z5_lower": clean(thr, 0),
            })

    threshold_history = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": (
            f"Proxy estimate from local streams using filtered {args.window_min}-minute moving HR/speed windows; "
            f"rolling {args.rolling_days}-day 85th percentile of candidate mean HR. "
            "This is not a lab lactate-threshold or ventilatory-threshold measurement."
        ),
        "zone_model": (
            "Threshold-derived bands: Z1 <85%, Z2 85-89%, Z3 90-94%, "
            "Z4 95-99%, Z5 >=100% of threshold_hr_proxy."
        ),
        "items": threshold_items,
    }

    drift_summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": (
            "Compares speed-per-heartbeat in first vs second half of moving stream data for runs >=35 min. "
            "Negative efficiency_change_pct can indicate HR drift/decoupling, but route, heat, fatigue and sensor quality matter."
        ),
        "items": drift_rows[-60:],
    }

    write_json(DOCS_DATA / "threshold_history.json", threshold_history)
    write_json(DOCS_DATA / "drift_summary.json", drift_summary)
    write_json(DERIVED / "stream_analysis_summary.json", {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stream_files": len(files),
        "analysed_threshold_activities": len(per_activity),
        "threshold_points": len(threshold_items),
        "drift_points": len(drift_rows),
        "note": "Raw streams remain local/private. Only derived summaries are written to docs/data.",
    })

    print(f"[stream-analysis] stream_files={len(files)}")
    print(f"[stream-analysis] analysed_threshold_activities={len(per_activity)}")
    print(f"[stream-analysis] threshold_points={len(threshold_items)}")
    print(f"[stream-analysis] drift_points={len(drift_rows)}")
    print("[stream-analysis] wrote docs/data/threshold_history.json")
    print("[stream-analysis] wrote docs/data/drift_summary.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
