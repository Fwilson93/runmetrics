#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dateutil import parser as dtparser
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STRAVA_DIR = DATA_DIR / "strava"
DOCS_DATA_DIR = ROOT / "docs" / "data"
STATE_PATH = DATA_DIR / "state.json"

STRAVA_OAUTH_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"

DEFAULT_HRMAX = 190.0
TAU_CTL = 42.0
TAU_ATL = 7.0

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def ensure_dirs() -> None:
    STRAVA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_state(st: Dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(st, indent=2, sort_keys=True), encoding="utf-8")

def require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v

def iso_to_dt(s: str) -> datetime:
    dt = dtparser.isoparse(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def dt_to_day(dts: datetime) -> date:
    return dts.astimezone(timezone.utc).date()

@dataclass
class StravaTokens:
    access_token: str
    refresh_token: str
    expires_at: int

def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> StravaTokens:
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    r = requests.post(STRAVA_OAUTH_TOKEN_URL, data=payload, timeout=30)
    r.raise_for_status()
    j = r.json()
    return StravaTokens(
        access_token=j["access_token"],
        refresh_token=j.get("refresh_token", refresh_token),
        expires_at=int(j["expires_at"]),
    )

def fetch_activities(access_token: str, after_epoch: Optional[int], per_page: int = 200, max_pages: int = 50) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    out: List[Dict[str, Any]] = []
    page = 1
    while page <= max_pages:
        params: Dict[str, Any] = {"per_page": per_page, "page": page}
        if after_epoch is not None:
            params["after"] = int(after_epoch)
        r = requests.get(STRAVA_ACTIVITIES_URL, headers=headers, params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(2.0)
            continue
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return out

def hrmax_observed(activities: List[Dict[str, Any]]) -> float:
    vals = []
    for a in activities:
        mh = a.get("max_heartrate")
        if mh is not None:
            try:
                vals.append(float(mh))
            except Exception:
                pass
    return max(vals) if vals else DEFAULT_HRMAX

def load_proxy(activity: Dict[str, Any], hrmax: float) -> Tuple[float, bool]:
    mt = activity.get("moving_time")
    if not mt:
        return 0.0, False
    dur_min = float(mt) / 60.0
    avg_hr = activity.get("average_heartrate")
    if avg_hr is not None and hrmax and hrmax > 0:
        x = float(avg_hr) / float(hrmax)
        return dur_min * (x * x) * 100.0, True
    return dur_min * 35.0, False

def ewma_update(prev: float, x: float, tau: float) -> float:
    return prev + (x - prev) / float(tau)

def build_daily_series(activities: List[Dict[str, Any]], days: int = 365) -> Dict[str, Any]:
    acts = []
    for a in activities:
        sd = a.get("start_date")
        if not sd:
            continue
        try:
            d = dt_to_day(iso_to_dt(sd))
        except Exception:
            continue
        acts.append((d, a))

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    dates = [start + timedelta(days=i) for i in range(days)]

    if not acts:
        series = [{"date": d.isoformat(), "daily_load": 0.0, "ctl": 0.0, "atl": 0.0, "tsb": 0.0} for d in dates]
        return {"status": "ok", "generated_at": utc_now_iso(), "hrmax": DEFAULT_HRMAX, "series": series}

    hrmax = hrmax_observed([a for _, a in acts])

    daily: Dict[date, float] = {}
    for d, a in acts:
        load, _ = load_proxy(a, hrmax)
        daily[d] = daily.get(d, 0.0) + float(load)

    loads = [daily.get(d, 0.0) for d in dates]

    ctl = 0.0
    atl = 0.0
    series = []
    for d, x in zip(dates, loads):
        ctl = ewma_update(ctl, x, TAU_CTL)
        atl = ewma_update(atl, x, TAU_ATL)
        series.append({"date": d.isoformat(), "daily_load": float(x), "ctl": float(ctl), "atl": float(atl), "tsb": float(ctl - atl)})

    zones = {
        "status": "ok",
        "generated_at": utc_now_iso(),
        "hrmax": float(hrmax),
        "lt1_hr": float(0.83 * hrmax),
        "lt2_hr": float(0.88 * hrmax),
        "note": "Zone thresholds are heuristic fractions of observed HRmax for offline static publishing.",
    }

    zmins = {z: 0.0 for z in ["Z1", "Z2", "Z3", "Z4", "Z5"]}
    cutoff = today - timedelta(days=6)
    for d, a in acts:
        if d < cutoff:
            continue
        mt = a.get("moving_time")
        hr = a.get("average_heartrate")
        if not mt or hr is None:
            continue
        frac = float(hr) / float(hrmax) if hrmax else 0.0
        mins = float(mt) / 60.0
        if frac < 0.75:
            zmins["Z1"] += mins
        elif frac < 0.83:
            zmins["Z2"] += mins
        elif frac < 0.88:
            zmins["Z3"] += mins
        elif frac < 0.93:
            zmins["Z4"] += mins
        else:
            zmins["Z5"] += mins

    zone_eff = {"status": "ok", "generated_at": utc_now_iso(), "days": 7, "zones": {z: {"minutes": int(round(m))} for z, m in zmins.items()}}

    return {"status": "ok", "generated_at": utc_now_iso(), "hrmax": float(hrmax), "series": series, "zones": zones, "zone_effort_1w": zone_eff}

def simplify_activity(a: Dict[str, Any]) -> Dict[str, Any]:
    sd = a.get("start_date")
    d_iso = None
    if sd:
        try:
            d_iso = iso_to_dt(sd).isoformat()
        except Exception:
            d_iso = sd
    dist_m = a.get("distance")
    mt = a.get("moving_time")
    pace_min_per_km = None
    if dist_m and mt and dist_m > 0:
        pace_s_per_km = float(mt) / (float(dist_m) / 1000.0)
        pace_min_per_km = pace_s_per_km / 60.0
    avg_hr = a.get("average_heartrate")
    ef = None
    if dist_m and avg_hr:
        try:
            ef = float(dist_m) / float(avg_hr)
        except Exception:
            ef = None
    return {
        "id": int(a["id"]) if "id" in a else None,
        "date": d_iso,
        "name": a.get("name"),
        "sport_type": a.get("sport_type") or a.get("type"),
        "distance_km": (float(dist_m) / 1000.0) if dist_m else None,
        "pace_min_per_km": pace_min_per_km,
        "avg_hr": float(avg_hr) if avg_hr is not None else None,
        "ef": ef,
    }

def dedupe_by_id(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[int, Dict[str, Any]] = {}
    for a in existing:
        if "id" in a:
            by_id[int(a["id"])] = a
    for a in new:
        if "id" in a:
            by_id[int(a["id"])] = a
    def key(a: Dict[str, Any]) -> float:
        sd = a.get("start_date")
        if not sd:
            return 0.0
        try:
            return iso_to_dt(sd).timestamp()
        except Exception:
            return 0.0
    merged = list(by_id.values())
    merged.sort(key=key, reverse=True)
    return merged

def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(ROOT / ".env.local", override=False)

    ensure_dirs()

    try:
        cid = require_env("STRAVA_CLIENT_ID")
        csec = require_env("STRAVA_CLIENT_SECRET")
        rtok = require_env("STRAVA_REFRESH_TOKEN")
    except Exception as e:
        print(f"[runmetrics] {e}", file=sys.stderr)
        return 2

    st = load_state()
    after_epoch = st.get("strava_after_epoch")
    if after_epoch is None:
        after_epoch = int((datetime.now(timezone.utc) - timedelta(days=400)).timestamp())

    toks = refresh_access_token(cid, csec, rtok)
    st["strava_token_expires_at"] = toks.expires_at
    st["updated_at"] = utc_now_iso()
    save_state(st)

    new_acts = fetch_activities(toks.access_token, after_epoch=after_epoch, per_page=200, max_pages=50)

    raw_path = STRAVA_DIR / "activities_raw.json"
    existing = []
    if raw_path.exists():
        try:
            existing = json.loads(raw_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    merged = dedupe_by_id(existing, new_acts)
    raw_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    max_ts = None
    for a in merged:
        sd = a.get("start_date")
        if not sd:
            continue
        try:
            ts = iso_to_dt(sd).timestamp()
            max_ts = ts if (max_ts is None or ts > max_ts) else max_ts
        except Exception:
            continue
    if max_ts is not None:
        st["strava_after_epoch"] = int(max_ts) - 24 * 3600
    st["updated_at"] = utc_now_iso()
    save_state(st)

    daily = build_daily_series(merged, days=365)
    recent_items = [simplify_activity(a) for a in merged[:50]]
    recent = {"status": "ok", "generated_at": utc_now_iso(), "items": recent_items}

    (DOCS_DATA_DIR / "load_365.json").write_text(json.dumps({
        "status": "ok",
        "generated_at": daily.get("generated_at"),
        "hrmax": daily.get("hrmax"),
        "series": daily.get("series"),
    }, indent=2), encoding="utf-8")
    (DOCS_DATA_DIR / "recent.json").write_text(json.dumps(recent, indent=2), encoding="utf-8")
    (DOCS_DATA_DIR / "zones.json").write_text(json.dumps(daily.get("zones", {"status": "insufficient_data"}), indent=2), encoding="utf-8")
    (DOCS_DATA_DIR / "zone_effort_1w.json").write_text(json.dumps(daily.get("zone_effort_1w", {"status": "insufficient_data"}), indent=2), encoding="utf-8")
    (DOCS_DATA_DIR / "meta.json").write_text(json.dumps({
        "status": "ok",
        "generated_at": utc_now_iso(),
        "counts": {"activities_total": len(merged), "recent_items": len(recent_items), "series_days": len(daily.get("series", []))},
    }, indent=2), encoding="utf-8")

    print("[runmetrics] OK: wrote docs/data/*.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
