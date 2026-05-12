#!/usr/bin/env python3
"""
RunMetrics static-site updater.

Local-only responsibilities:
- Load .env/environment secrets without printing them.
- Reuse data/strava/activities_raw.json if fetched less than 1 hour ago.
- Otherwise fetch activities from Strava.
- Compute public-safe derived metrics.
- Write docs/data/*.json for a static GitHub Pages dashboard.

Public safety:
- Does NOT write tokens, raw Strava payloads, GPS coordinates, maps, polylines,
  activity names, start/end lat/lng, upload IDs, or external IDs to docs/.
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
    import pandas as pd
    import numpy as np
    from dateutil import parser as dtparser
except ImportError as exc:
    raise SystemExit(
        "Missing Python dependency. Install with:\n"
        "  python -m pip install requests pandas numpy python-dateutil python-dotenv\n"
        f"Original error: {exc}"
    )

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DATA_PATH = ROOT / "data" / "strava" / "activities_raw.json"
STATE_PATH = ROOT / "data" / "state.json"
DOCS_DATA = ROOT / "docs" / "data"
DOCS_DATA.mkdir(parents=True, exist_ok=True)

CACHE_MAX_AGE_SECONDS = 60 * 60
PER_PAGE = 200
MAX_PAGES = int(os.getenv("RUNMETRICS_MAX_PAGES", "10"))
FETCH_AFTER_EPOCH = os.getenv("RUNMETRICS_FETCH_AFTER_EPOCH")
INCLUDE_SPORTS = {"Run", "TrailRun"}

HR_REST = float(os.getenv("RUNMETRICS_HR_REST", "50"))
SEX = os.getenv("RUNMETRICS_SEX", "male")
CTL_TAU_DAYS = float(os.getenv("RUNMETRICS_CTL_TAU", "42"))
ATL_TAU_DAYS = float(os.getenv("RUNMETRICS_ATL_TAU", "7"))


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


def parse_updated_at(state: dict[str, Any] | None) -> datetime | None:
    if not state:
        return None
    raw = state.get("strava_activities_updated_at") or state.get("updated_at")
    if not raw:
        return None
    try:
        dt = dtparser.isoparse(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def cache_status() -> tuple[bool, str]:
    if not LOCAL_DATA_PATH.exists():
        return False, f"No local cache found at {LOCAL_DATA_PATH}"
    state = read_json(STATE_PATH, {}) or {}
    updated_at = parse_updated_at(state)
    if updated_at is None:
        updated_at = datetime.fromtimestamp(LOCAL_DATA_PATH.stat().st_mtime, tz=timezone.utc)
    age = (utc_now() - updated_at).total_seconds()
    if age <= CACHE_MAX_AGE_SECONDS:
        return True, f"Using local Strava cache ({age/60:.1f} minutes old)."
    return False, f"Local Strava cache is stale ({age/60:.1f} minutes old)."


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing {name}. Put STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET and "
            "STRAVA_REFRESH_TOKEN in .env or your shell environment."
        )
    return value


def refresh_access_token() -> dict[str, Any]:
    payload = {
        "client_id": env_required("STRAVA_CLIENT_ID"),
        "client_secret": env_required("STRAVA_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": env_required("STRAVA_REFRESH_TOKEN"),
    }
    r = requests.post("https://www.strava.com/api/v3/oauth/token", data=payload, timeout=30)
    r.raise_for_status()
    out = r.json()
    if "access_token" not in out:
        raise RuntimeError(f"Strava token refresh did not return access_token. Keys: {sorted(out)}")
    return out


def fetch_activities() -> list[dict[str, Any]]:
    token = refresh_access_token()
    access_token = token["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    activities: list[dict[str, Any]] = []

    for page in range(1, MAX_PAGES + 1):
        params: dict[str, Any] = {"per_page": PER_PAGE, "page": page}
        if FETCH_AFTER_EPOCH:
            params["after"] = int(FETCH_AFTER_EPOCH)
        r = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers=headers,
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected Strava response type: {type(batch).__name__}")
        if not batch:
            break
        activities.extend(batch)
        if len(batch) < PER_PAGE:
            break

    now_iso = utc_now().isoformat()
    write_json(LOCAL_DATA_PATH, activities)
    state = read_json(STATE_PATH, {}) or {}
    state.update({
        "updated_at": now_iso,
        "strava_activities_updated_at": now_iso,
        "strava_token_expires_at": token.get("expires_at"),
        "activity_count": len(activities),
    })
    write_json(STATE_PATH, state)
    return activities


def get_activities() -> list[dict[str, Any]]:
    fresh, message = cache_status()
    print(f"[runmetrics] {message}")
    if fresh:
        return read_json(LOCAL_DATA_PATH, []) or []
    try:
        print("[runmetrics] Fetching fresh Strava data...")
        return fetch_activities()
    except Exception as exc:
        if LOCAL_DATA_PATH.exists():
            print(f"[runmetrics] WARNING: fetch failed; using stale cache. Reason: {exc}", file=sys.stderr)
            return read_json(LOCAL_DATA_PATH, []) or []
        raise


def safe_ts(value: Any) -> pd.Timestamp | pd.NaT:
    if not value:
        return pd.NaT
    try:
        return pd.Timestamp(dtparser.isoparse(str(value))).tz_convert("UTC")
    except Exception:
        return pd.NaT


def to_float(value: Any) -> float:
    try:
        if value is None:
            return float("nan")
        return float(value)
    except Exception:
        return float("nan")


def parse_activities(raw: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for a in raw:
        sport = a.get("sport_type") or a.get("type")
        if sport not in INCLUDE_SPORTS:
            continue
        start = safe_ts(a.get("start_date"))
        if pd.isna(start):
            continue

        distance_m = to_float(a.get("distance"))
        moving_time_s = to_float(a.get("moving_time"))
        elapsed_time_s = to_float(a.get("elapsed_time"))
        elev_m = to_float(a.get("total_elevation_gain"))
        avg_hr = to_float(a.get("average_heartrate"))
        max_hr = to_float(a.get("max_heartrate"))
        cadence = to_float(a.get("average_cadence"))

        distance_km = distance_m / 1000.0 if math.isfinite(distance_m) else float("nan")
        moving_time_min = moving_time_s / 60.0 if math.isfinite(moving_time_s) else float("nan")
        pace = moving_time_min / distance_km if distance_km and math.isfinite(distance_km) and distance_km > 0 else float("nan")
        speed_kmh = distance_km / (moving_time_min / 60.0) if moving_time_min and math.isfinite(moving_time_min) and moving_time_min > 0 else float("nan")
        efficiency = distance_m / avg_hr if math.isfinite(distance_m) and math.isfinite(avg_hr) and avg_hr > 0 else float("nan")

        rows.append({
            "id": str(a.get("id", "")),  # internal only; not exported to docs recent table
            "date": pd.Timestamp(start.date()),
            "start_utc": start,
            "sport_type": sport,
            "distance_km": distance_km,
            "moving_time_min": moving_time_min,
            "elapsed_time_min": elapsed_time_s / 60.0 if math.isfinite(elapsed_time_s) else float("nan"),
            "pace_min_per_km": pace,
            "speed_kmh": speed_kmh,
            "elev_gain_m": elev_m,
            "avg_hr": avg_hr,
            "max_hr": max_hr,
            "average_cadence": cadence,
            "efficiency_factor": efficiency,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("start_utc").reset_index(drop=True)


def banister_trimp(duration_min: float, avg_hr: float, hr_rest: float, hr_max: float, sex: str) -> float:
    if not math.isfinite(duration_min) or duration_min <= 0:
        return 0.0
    if not math.isfinite(avg_hr) or not math.isfinite(hr_rest) or not math.isfinite(hr_max) or hr_max <= hr_rest:
        return 0.0
    hrr = max(0.0, min(1.0, (avg_hr - hr_rest) / (hr_max - hr_rest)))
    a, b = (0.64, 1.92) if sex.lower().startswith("m") else (0.86, 1.67)
    return float(duration_min * hrr * a * math.exp(b * hrr))


def add_load(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    hrmax = df["max_hr"].dropna().max()
    hrmax = float(hrmax) if math.isfinite(float(hrmax)) else 190.0
    df["hr_max_used"] = hrmax
    df["load_trimp"] = [
        banister_trimp(float(r.moving_time_min), float(r.avg_hr), HR_REST, hrmax, SEX)
        if pd.notna(r.avg_hr)
        else max(0.0, float(r.moving_time_min or 0.0) * 0.35)
        for r in df.itertuples(index=False)
    ]
    return df


def pmc_series(values: np.ndarray, tau: float) -> np.ndarray:
    out = []
    prev = 0.0
    for v in values:
        x = 0.0 if not math.isfinite(float(v)) else float(v)
        prev = prev + (x - prev) / tau
        out.append(prev)
    return np.asarray(out)


def build_daily(df: pd.DataFrame) -> pd.DataFrame:
    daily = df.groupby("date").agg(
        activities=("id", "count"),
        distance_km=("distance_km", "sum"),
        moving_time_min=("moving_time_min", "sum"),
        elev_gain_m=("elev_gain_m", "sum"),
        load_trimp=("load_trimp", "sum"),
        avg_hr=("avg_hr", "mean"),
        pace_min_per_km=("pace_min_per_km", "mean"),
        efficiency_factor=("efficiency_factor", "mean"),
    ).sort_index()

    full_index = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_index)
    for col in ["activities", "distance_km", "moving_time_min", "elev_gain_m", "load_trimp"]:
        daily[col] = daily[col].fillna(0.0)
    daily.index.name = "date"
    daily["ctl"] = pmc_series(daily["load_trimp"].values, CTL_TAU_DAYS)
    daily["atl"] = pmc_series(daily["load_trimp"].values, ATL_TAU_DAYS)
    daily["tsb"] = daily["ctl"] - daily["atl"]
    daily["distance_7d"] = daily["distance_km"].rolling(7, min_periods=1).sum()
    daily["load_7d"] = daily["load_trimp"].rolling(7, min_periods=1).sum()
    daily["load_28d"] = daily["load_trimp"].rolling(28, min_periods=1).sum()
    return daily


def build_weekly(df: pd.DataFrame) -> pd.DataFrame:
    weekly = df.set_index("date").sort_index().resample("W-MON", label="left", closed="left").agg(
        activities=("id", "count"),
        distance_km=("distance_km", "sum"),
        moving_time_min=("moving_time_min", "sum"),
        elev_gain_m=("elev_gain_m", "sum"),
        load_trimp=("load_trimp", "sum"),
        avg_hr=("avg_hr", "mean"),
        pace_min_per_km=("pace_min_per_km", "mean"),
        efficiency_factor=("efficiency_factor", "mean"),
    )
    weekly["distance_4w_avg"] = weekly["distance_km"].rolling(4, min_periods=1).mean()
    weekly["load_4w_avg"] = weekly["load_trimp"].rolling(4, min_periods=1).mean()
    return weekly


def clean_number(x: Any, digits: int = 3) -> float | None:
    try:
        f = float(x)
        if not math.isfinite(f):
            return None
        return round(f, digits)
    except Exception:
        return None


def records_from_indexed_frame(frame: pd.DataFrame, date_col: str = "date") -> list[dict[str, Any]]:
    out = frame.reset_index().copy()
    out[date_col] = pd.to_datetime(out[date_col]).dt.strftime("%Y-%m-%d")
    records = []
    for rec in out.to_dict(orient="records"):
        records.append({k: (clean_number(v) if isinstance(v, (float, int, np.floating, np.integer)) else v) for k, v in rec.items()})
    return records


def make_summary(df: pd.DataFrame, daily: pd.DataFrame, weekly: pd.DataFrame) -> dict[str, Any]:
    last_day = daily.index.max()
    last7 = daily.loc[last_day - pd.Timedelta(days=6): last_day]
    last28 = daily.loc[last_day - pd.Timedelta(days=27): last_day]
    latest = daily.iloc[-1]
    load7_avg = last7["load_trimp"].mean()
    load28_avg = last28["load_trimp"].mean()
    acwr = load7_avg / load28_avg if load28_avg > 0 else float("nan")

    current_week = weekly.iloc[-1]
    prev_4w = weekly["distance_km"].tail(5).head(4).mean() if len(weekly) >= 5 else weekly["distance_km"].mean()
    distance_ramp = current_week["distance_km"] / prev_4w if prev_4w and prev_4w > 0 else float("nan")

    advice = []
    tsb = float(latest["tsb"])
    if tsb <= -20:
        advice.append("TSB is very low: treat this as a recovery warning and avoid stacking intensity on fatigue.")
    elif tsb <= -10:
        advice.append("TSB is moderately negative: keep the next run controlled unless you feel unusually fresh.")
    elif tsb >= 0:
        advice.append("TSB is neutral or positive: you are relatively fresh for quality work if the legs feel good.")
    else:
        advice.append("TSB is slightly negative, which is normal during a productive training block.")

    if math.isfinite(acwr):
        if acwr > 1.5:
            advice.append(f"ACWR is high at {acwr:.2f}: reduce near-term load or intensity.")
        elif acwr < 0.8:
            advice.append(f"ACWR is low at {acwr:.2f}: rebuild gradually rather than jumping into a big week.")
        else:
            advice.append(f"ACWR is {acwr:.2f}, within the configured guardrail range.")

    if math.isfinite(float(distance_ramp)):
        if distance_ramp > 1.25:
            advice.append(f"This week's distance is up sharply versus the recent baseline ({distance_ramp:.2f}×). Be cautious.")
        elif distance_ramp < 0.75:
            advice.append(f"This week's distance is below baseline ({distance_ramp:.2f}×), which may be useful recovery.")

    activity_days = int((last7["activities"] > 0).sum())
    if activity_days <= 1:
        advice.append("Only 0–1 running days in the last week: consistency is the next target if injury-free.")
    elif activity_days >= 6:
        advice.append("6+ running days in the last week: watch for accumulating niggles and keep easy days easy.")

    return {
        "generated_at_utc": utc_now().isoformat(),
        "cache_file": "data/strava/activities_raw.json",
        "public_data_policy": "Summary metrics only. No raw Strava payloads, GPS, polylines, activity names, upload IDs, external IDs, or tokens are exported.",
        "activity_count": int(len(df)),
        "date_min": df["date"].min().strftime("%Y-%m-%d"),
        "date_max": df["date"].max().strftime("%Y-%m-%d"),
        "total_distance_km": clean_number(df["distance_km"].sum(), 1),
        "last_7d_distance_km": clean_number(last7["distance_km"].sum(), 1),
        "last_28d_distance_km": clean_number(last28["distance_km"].sum(), 1),
        "last_7d_activity_days": activity_days,
        "current_week_distance_km": clean_number(current_week["distance_km"], 1),
        "distance_ramp_vs_prev_4w": clean_number(distance_ramp, 2),
        "ctl": clean_number(latest["ctl"], 1),
        "atl": clean_number(latest["atl"], 1),
        "tsb": clean_number(latest["tsb"], 1),
        "acwr": clean_number(acwr, 2),
        "observed_hrmax": clean_number(df["max_hr"].dropna().max(), 0),
        "median_pace_min_per_km": clean_number(df["pace_min_per_km"].median(), 2),
        "median_avg_hr": clean_number(df["avg_hr"].median(), 1),
        "advice": advice,
    }


def make_recent_public(df: pd.DataFrame, limit: int = 20) -> list[dict[str, Any]]:
    # Deliberately no activity name, route, coordinates, IDs, upload IDs, external IDs, or raw JSON.
    cols = ["date", "sport_type", "distance_km", "moving_time_min", "pace_min_per_km", "elev_gain_m", "avg_hr", "max_hr", "load_trimp", "efficiency_factor"]
    recent = df.sort_values("date", ascending=False).head(limit)[cols].copy()
    recent["date"] = recent["date"].dt.strftime("%Y-%m-%d")
    records = []
    for rec in recent.to_dict(orient="records"):
        records.append({k: (clean_number(v) if isinstance(v, (float, int, np.floating, np.integer)) else v) for k, v in rec.items()})
    return records


def main() -> int:
    load_env()
    raw = get_activities()
    if not raw:
        raise SystemExit("No activities available.")

    df = add_load(parse_activities(raw))
    if df.empty:
        raise SystemExit("No Run/TrailRun activities available after filtering.")

    daily = build_daily(df)
    weekly = build_weekly(df)
    summary = make_summary(df, daily, weekly)

    write_json(DOCS_DATA / "summary.json", summary)
    write_json(DOCS_DATA / "daily_metrics.json", records_from_indexed_frame(daily.tail(365)))
    write_json(DOCS_DATA / "weekly_metrics.json", records_from_indexed_frame(weekly.tail(104)))
    write_json(DOCS_DATA / "activities_recent.json", make_recent_public(df, 20))

    print(f"[runmetrics] Wrote static data to {DOCS_DATA}")
    print(f"[runmetrics] Activities exported: {summary['activity_count']}; latest date: {summary['date_max']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
