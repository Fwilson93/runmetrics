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
    raise SystemExit(
        "Missing dependency. Install with:\n"
        "  python -m pip install numpy pandas python-dateutil\n"
        f"Original error: {exc}"
    )

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


def clean(x: Any, nd: int = 2) -> float | None:
    try:
        f = float(x)
        if not math.isfinite(f):
            return None
        return round(f, nd)
    except Exception:
        return None


def finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except Exception:
        return False


def parse_date(value: Any) -> pd.Timestamp | pd.NaT:
    try:
        d = dtparser.isoparse(str(value))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return pd.Timestamp(d).tz_convert("UTC")
    except Exception:
        return pd.NaT


def stream_array(streams: dict[str, Any], key: str) -> list[Any] | None:
    item = streams.get(key, {}) if isinstance(streams, dict) else {}
    data = item.get("data") if isinstance(item, dict) else None
    return data if isinstance(data, list) else None


def stream_frame(payload: dict[str, Any]) -> pd.DataFrame:
    streams = payload.get("streams", {})
    time_s = stream_array(streams, "time")
    hr = stream_array(streams, "heartrate")

    if time_s is None or hr is None:
        return pd.DataFrame()

    distance = stream_array(streams, "distance")
    velocity = stream_array(streams, "velocity_smooth")
    moving = stream_array(streams, "moving")
    grade = stream_array(streams, "grade_smooth")

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

    out = []

    for start in np.arange(t0, t1 - window_s + 1, 120):
        end = start + window_s
        w = df[(df["time_s"] >= start) & (df["time_s"] <= end)]

        if len(w) < window_s * 0.55:
            continue

        moving_frac = float(w["moving"].mean())
        hr_mean = float(w["hr_smooth"].mean())
        hr_std = float(w["hr_smooth"].std(ddof=0))
        hr_range = float(w["hr_smooth"].max() - w["hr_smooth"].min())
        speed = float(w["speed_smooth"].mean()) if w["speed_smooth"].notna().any() else np.nan
        grade_abs = float(w["grade_pct"].abs().mean()) if w["grade_pct"].notna().any() else np.nan
        grade_std = float(w["grade_pct"].std(ddof=0)) if w["grade_pct"].notna().sum() > 1 else np.nan

        reasons = []

        if moving_frac < 0.90:
            reasons.append("low_moving_fraction")
        if not math.isfinite(hr_mean) or hr_mean < 120:
            reasons.append("low_or_missing_hr")
        if hr_std > 12:
            reasons.append("unstable_hr")
        if hr_range > 35:
            reasons.append("large_hr_range")
        if math.isfinite(speed) and speed < 2.0:
            reasons.append("low_speed")
        if math.isfinite(grade_abs) and grade_abs > 4.0:
            reasons.append("hilly_window")
        if math.isfinite(grade_std) and grade_std > 5.0:
            reasons.append("variable_gradient")

        pace = (1000.0 / speed) / 60.0 if math.isfinite(speed) and speed > 0 else np.nan

        out.append({
            "start_s": clean(start, 1),
            "end_s": clean(end, 1),
            "window_min": window_min,
            "mean_hr": clean(hr_mean, 1),
            "hr_std": clean(hr_std, 1),
            "hr_range": clean(hr_range, 1),
            "pace_min_per_km": clean(pace, 2),
            "moving_fraction": clean(moving_frac, 3),
            "grade_abs_mean": clean(grade_abs, 2),
            "grade_std": clean(grade_std, 2),
            "accepted": len(reasons) == 0,
            "reject_reasons": ";".join(reasons),
        })

    return out


def candidate_score(c: dict[str, Any]) -> float:
    return (
        float(c.get("mean_hr") or 0)
        - 0.8 * float(c.get("hr_std") or 0)
        - 0.8 * float(c.get("grade_abs_mean") or 0)
    )


def drift_estimate(df: pd.DataFrame) -> dict[str, Any] | None:
    moving = df[df["moving"]].copy() if not df.empty else pd.DataFrame()

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

    def eff(part: pd.DataFrame) -> tuple[float, float, float]:
        speed = float(part["speed_smooth"].mean()) if part["speed_smooth"].notna().any() else np.nan
        hr = float(part["hr_smooth"].mean())
        eff_value = speed / hr if math.isfinite(speed) and hr > 0 else np.nan
        return speed, hr, eff_value

    s1, h1, e1 = eff(first)
    s2, h2, e2 = eff(second)

    if not all(math.isfinite(x) for x in [s1, h1, e1, s2, h2, e2]) or e1 <= 0:
        return None

    grade_abs = float(moving["grade_pct"].abs().mean()) if moving["grade_pct"].notna().any() else np.nan

    confidence = "medium" if (math.isfinite(grade_abs) and grade_abs > 3.5) or duration_s < 45 * 60 else "high"

    return {
        "duration_min": clean(duration_s / 60, 1),
        "first_half_hr": clean(h1, 1),
        "second_half_hr": clean(h2, 1),
        "hr_rise_bpm": clean(h2 - h1, 1),
        "speed_change_pct": clean(((s2 - s1) / s1) * 100, 1),
        "efficiency_change_pct": clean(((e2 - e1) / e1) * 100, 1),
        "grade_abs_mean": clean(grade_abs, 2),
        "confidence": confidence,
    }


def confidence(n: int) -> str:
    if n >= 8:
        return "high"
    if n >= 4:
        return "medium"
    if n >= 2:
        return "low"
    return "very_low"


def load_activity_lookup() -> dict[str, dict[str, Any]]:
    acts = read_json(ACTIVITIES_PATH, []) or []
    return {str(a.get("id")): a for a in acts if a.get("id")}


def make_matched_runs(activity_lookup: dict[str, dict[str, Any]], per_activity_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []

    for r in per_activity_rows:
        a = activity_lookup.get(str(r.get("activity_id")))

        if not a:
            continue

        sport = a.get("sport_type") or a.get("type") or "Run"
        dist_km = float(a.get("distance") or 0) / 1000.0
        elev = float(a.get("total_elevation_gain") or 0)
        moving_min = float(a.get("moving_time") or 0) / 60.0

        if dist_km <= 0 or moving_min <= 0:
            continue

        # Privacy-safe approximation: no GPS, no polyline, no route names in public output.
        route_key = f"{sport}|{round(dist_km * 2) / 2:.1f}km|{round(elev / 25) * 25:.0f}m"

        rows.append({
            "route_key": route_key,
            "date": r["date"],
            "sport_type": sport,
            "distance_km": clean(dist_km, 2),
            "elev_gain_m": clean(elev, 0),
            "moving_time_min": clean(moving_min, 1),
            "pace_min_per_km": clean(moving_min / dist_km, 2),
            "avg_hr": clean(a.get("average_heartrate"), 1),
            "threshold_window_hr": clean(r.get("mean_hr"), 1),
        })

    if not rows:
        return {
            "generated_at_utc": now_iso(),
            "method": "No matched-run groups available yet.",
            "items": [],
        }

    df = pd.DataFrame(rows)
    items = []

    for key, g in df.groupby("route_key"):
        if len(g) < 2:
            continue

        g = g.sort_values("date")
        latest = g.iloc[-1]
        earliest = g.iloc[0]
        best_pace = float(g["pace_min_per_km"].min())
        latest_pace = float(latest["pace_min_per_km"])
        previous = g.iloc[:-1]
        previous_median = float(previous["pace_min_per_km"].median()) if len(previous) else np.nan

        delta = (
            ((latest_pace - previous_median) / previous_median) * 100
            if math.isfinite(previous_median) and previous_median > 0
            else None
        )

        items.append({
            "label": f"Matched run {len(items) + 1}",
            "match_basis": "similar sport, distance and elevation bins; not GPS route matching",
            "count": int(len(g)),
            "first_date": str(earliest["date"]),
            "latest_date": str(latest["date"]),
            "typical_distance_km": clean(g["distance_km"].median(), 1),
            "typical_elev_gain_m": clean(g["elev_gain_m"].median(), 0),
            "latest_pace_min_per_km": clean(latest_pace, 2),
            "best_pace_min_per_km": clean(best_pace, 2),
            "latest_vs_previous_median_pct": clean(delta, 1),
            "latest_avg_hr": clean(latest.get("avg_hr"), 1),
        })

    items = sorted(items, key=lambda x: (x["count"], x["latest_date"]), reverse=True)[:12]

    return {
        "generated_at_utc": now_iso(),
        "method": (
            "Approximate Strava matched-runs style grouping using local activity summaries only: "
            "sport + rounded distance + rounded elevation. No route, GPS, polyline or activity IDs are exported."
        ),
        "items": items,
    }


def enhance_advice(summary: dict[str, Any], threshold: dict[str, Any], drift: dict[str, Any], matched: dict[str, Any]) -> dict[str, Any]:
    advice = []

    ctl = summary.get("ctl")
    atl = summary.get("atl")
    tsb = summary.get("tsb")
    acwr = summary.get("acwr")
    d7 = summary.get("last_7d_distance_km")
    d28 = summary.get("last_28d_distance_km")
    days = summary.get("last_7d_activity_days")

    if finite(ctl) and finite(atl) and finite(tsb):
        tsb_f = float(tsb)

        if tsb_f < -20:
            tone = "you are carrying a lot of short-term fatigue"
            action = "make the next run genuinely easy or take a rest day"
        elif tsb_f < -10:
            tone = "you are in a productive but fairly loaded part of the block"
            action = "keep easy days easy and avoid adding extra intensity unless you feel unusually good"
        elif tsb_f >= 0:
            tone = "you look relatively fresh on the load model"
            action = "a quality session is more defensible if your legs feel good"
        else:
            tone = "you have a normal amount of training fatigue"
            action = "steady aerobic work is a sensible default"

        advice.append(f"Load model: CTL {ctl}, ATL {atl}, TSB {tsb}. In plain terms, {tone}; {action}.")

    if finite(acwr):
        a = float(acwr)

        if a > 1.5:
            advice.append(f"Ramp rate: ACWR is {a:.2f}, which is high. The useful move is not necessarily full rest, but reducing either volume or intensity for the next couple of runs.")
        elif a < 0.8:
            advice.append(f"Ramp rate: ACWR is {a:.2f}, so recent load is low relative to the last month. If you are healthy, rebuild with a small volume increase rather than a single big catch-up run.")
        else:
            advice.append(f"Ramp rate: ACWR is {a:.2f}, which is within the configured guardrail. This supports continuing the current pattern if niggles are quiet.")

    latest_thr = threshold.get("latest")

    if latest_thr:
        advice.append(
            f"Threshold proxy: latest estimate is about {latest_thr.get('threshold_hr_proxy')} bpm "
            f"with {latest_thr.get('confidence')} confidence from {latest_thr.get('eligible_windows')} eligible windows. "
            "Use this as a trend anchor, not as a lab-tested lactate threshold."
        )

    drift_items = drift.get("items") or []

    if drift_items:
        recent = drift_items[-5:]
        vals = [x.get("efficiency_change_pct") for x in recent if finite(x.get("efficiency_change_pct"))]

        if vals:
            avg = sum(float(v) for v in vals) / len(vals)

            if avg < -7:
                msg = "recent steady runs show noticeable decoupling; prioritise easier aerobic work, hydration/fuelling, and avoid turning easy runs into moderate efforts"
            elif avg < -3:
                msg = "there is mild drift, which is common, but worth watching alongside fatigue and terrain"
            else:
                msg = "recent drift looks controlled, suggesting aerobic durability is holding up reasonably well"

            advice.append(f"HR drift: recent average efficiency change is {avg:.1f}%. {msg}.")

    groups = matched.get("items") or []

    if groups:
        g = groups[0]
        delta = g.get("latest_vs_previous_median_pct")

        if finite(delta):
            if float(delta) < -2:
                txt = "faster than your previous median"
            elif float(delta) > 2:
                txt = "slower than your previous median"
            else:
                txt = "about in line with your previous median"

            advice.append(
                f"Matched-run check: {g.get('label')} has {g.get('count')} similar efforts; "
                f"the latest pace was {txt} ({delta}%). Treat this as approximate matching by distance/elevation, not exact GPS route matching."
            )

    if finite(d7) and finite(d28):
        advice.append(f"Context: last 7 days {d7} km, last 28 days {d28} km, across {days} running days in the last week. This is the basic sanity check against how your legs actually feel.")

    summary["advice"] = advice
    summary["advice_style"] = "dynamic_from_load_threshold_drift_and_matched_runs"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-min", type=int, default=20)
    parser.add_argument("--rolling-days", type=int, default=90)
    args = parser.parse_args()

    files = sorted(STREAM_DIR.glob("*.json"))

    if not files:
        raise SystemExit("No stream files found. Run scripts/fetch_strava_streams.py first.")

    debug_rows = []
    per_activity = []
    drift_rows = []
    activity_lookup = load_activity_lookup()

    for path in files:
        payload = read_json(path, {}) or {}
        activity_id = str(payload.get("activity_id") or path.stem)
        date_ts = parse_date(payload.get("start_date"))

        if pd.isna(date_ts):
            continue

        date_str = pd.Timestamp(date_ts.date()).strftime("%Y-%m-%d")
        df = stream_frame(payload)

        if df.empty:
            continue

        all_cands = threshold_candidates(df, args.window_min)
        accepted = [c for c in all_cands if c.get("accepted")]
        selected = max(accepted, key=candidate_score) if accepted else None

        sorted_candidates = sorted(all_cands, key=candidate_score, reverse=True)

        for rank, c in enumerate(sorted_candidates, start=1):
            row = dict(c)
            row.update({
                "date": date_str,
                "activity_id": activity_id,
                "rank_by_score": rank,
                "selected": bool(selected and c is selected),
                "score": clean(candidate_score(c), 2),
            })
            debug_rows.append(row)

        if selected:
            rec = dict(selected)
            rec.update({
                "date": date_str,
                "activity_id": activity_id,
                "candidate_count_activity": len(accepted),
            })
            per_activity.append(rec)

        dr = drift_estimate(df)

        if dr:
            dr["date"] = date_str
            drift_rows.append(dr)

    debug_csv = DERIVED / "threshold_candidates_debug.csv"

    if debug_rows:
        fieldnames = sorted({k for row in debug_rows for k in row.keys()})
        with debug_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(debug_rows)

    threshold_items = []
    latest = None

    if per_activity:
        cdf = pd.DataFrame(per_activity)
        cdf["date_ts"] = pd.to_datetime(cdf["date"])
        cdf = cdf.sort_values("date_ts")
        dates = list(pd.date_range(cdf["date_ts"].min(), cdf["date_ts"].max(), freq="7D"))

        if cdf["date_ts"].max() not in dates:
            dates.append(cdf["date_ts"].max())

        for d in dates:
            window = cdf[
                (cdf["date_ts"] >= d - pd.Timedelta(days=args.rolling_days - 1))
                & (cdf["date_ts"] <= d)
            ]

            if window.empty:
                continue

            thr = float(np.nanpercentile(window["mean_hr"].astype(float), 85))
            pace = (
                float(np.nanmedian(window["pace_min_per_km"].astype(float)))
                if window["pace_min_per_km"].notna().any()
                else np.nan
            )
            n = int(len(window))

            item = {
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
            }

            threshold_items.append(item)

        latest = threshold_items[-1] if threshold_items else None

    threshold_history = {
        "generated_at_utc": now_iso(),
        "latest": latest,
        "method": (
            f"Proxy estimate from local streams using filtered {args.window_min}-minute moving HR/speed windows; "
            f"rolling {args.rolling_days}-day 85th percentile of candidate mean HR. "
            "Not a lab lactate-threshold or ventilatory-threshold measurement."
        ),
        "zone_model": "Threshold-derived bands: Z1 <85%, Z2 85-89%, Z3 90-94%, Z4 95-99%, Z5 >=100% of threshold_hr_proxy.",
        "items": threshold_items,
    }

    drift_summary = {
        "generated_at_utc": now_iso(),
        "method": (
            "Compares speed-per-heartbeat in first vs second half of moving stream data for runs >=35 min. "
            "Negative efficiency_change_pct can indicate HR drift/decoupling, but route, heat, fatigue and sensor quality matter."
        ),
        "items": drift_rows[-60:],
    }

    matched_runs = make_matched_runs(activity_lookup, per_activity)

    summary_path = DOCS_DATA / "summary.json"
    summary = read_json(summary_path, {}) or {}
    summary = enhance_advice(summary, threshold_history, drift_summary, matched_runs)

    write_json(DOCS_DATA / "threshold_history.json", threshold_history)
    write_json(DOCS_DATA / "drift_summary.json", drift_summary)
    write_json(DOCS_DATA / "matched_runs.json", matched_runs)
    write_json(summary_path, summary)

    write_json(DERIVED / "stream_analysis_summary.json", {
        "generated_at_utc": now_iso(),
        "stream_files": len(files),
        "accepted_threshold_activities": len(per_activity),
        "debug_candidate_rows": len(debug_rows),
        "threshold_points": len(threshold_items),
        "drift_points": len(drift_rows),
        "matched_run_groups": len(matched_runs.get("items", [])),
        "debug_csv": str(debug_csv.relative_to(ROOT)) if debug_rows else None,
        "note": "Raw streams and candidate debug CSV remain local/private. Public docs contain derived summaries only.",
    })

    print(f"[stream-analysis] stream_files={len(files)}")
    print(f"[stream-analysis] accepted_threshold_activities={len(per_activity)}")
    print(f"[stream-analysis] debug_candidate_rows={len(debug_rows)}")
    print(f"[stream-analysis] threshold_points={len(threshold_items)}")
    print(f"[stream-analysis] drift_points={len(drift_rows)}")
    print(f"[stream-analysis] matched_run_groups={len(matched_runs.get('items', []))}")
    print("[stream-analysis] wrote docs/data/threshold_history.json")
    print("[stream-analysis] wrote docs/data/drift_summary.json")
    print("[stream-analysis] wrote docs/data/matched_runs.json")
    print("[stream-analysis] enhanced docs/data/summary.json advice")
    if debug_rows:
        print(f"[stream-analysis] wrote {debug_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
