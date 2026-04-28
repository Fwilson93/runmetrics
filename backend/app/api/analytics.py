from fastapi import APIRouter, Query
from datetime import datetime, timedelta, timezone, date
import math
import statistics

from app.db.session import SessionLocal
from app.db.models import Activity

router = APIRouter()

def _to_date(dt):
    if not dt:
        return None
    if isinstance(dt, datetime):
        return dt.date()
    return None

def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())

def _pace_s_per_km(distance_m, moving_time_s):
    if not distance_m or not moving_time_s or distance_m <= 0:
        return None
    return moving_time_s / (distance_m / 1000.0)

def _pace_min_per_km(distance_m, moving_time_s):
    p = _pace_s_per_km(distance_m, moving_time_s)
    return (p / 60.0) if p else None

def _hrmax_observed(activities):
    vals = [a.max_heartrate for a in activities if a.max_heartrate]
    return max(vals) if vals else 190.0


def _banister_trimp(duration_min: float, hr_avg: float, hr_rest: float, hr_max: float, sex: str = "male") -> float:
    """
    Banister TRIMP (HR-reserve based):
      TRIMP = duration_min * HRR * a * exp(b * HRR)
    with sex-specific constants (male: a=0.64, b=1.92; female: a=0.86, b=1.67).
    """
    if duration_min <= 0 or hr_avg is None:
        return 0.0
    if hr_max <= hr_rest:
        return 0.0
    hrr = (float(hr_avg) - float(hr_rest)) / (float(hr_max) - float(hr_rest))
    hrr = max(0.0, min(1.0, hrr))

    sex = (sex or "male").lower()
    if sex.startswith("f"):
        a, b = 0.86, 1.67
    else:
        a, b = 0.64, 1.92

    # uses math from module imports
    return float(duration_min * hrr * a * math.exp(b * hrr))

def _load_proxy(a, hrmax, hr_rest: float = 50.0, sex: str = "male"):
    """
    TRIMP-based load (primary) with conservative fallback when HR missing.

    Returns: (load, used_hr)
      - used_hr=True if avg HR was available
      - used_hr=False if fallback estimate was used
    """
    if not a.moving_time_s:
        return 0.0, False

    dur_min = a.moving_time_s / 60.0

    # Primary: use avg HR if present
    if a.average_heartrate and hrmax and hrmax > 0:
        tr = _banister_trimp(dur_min, float(a.average_heartrate), hr_rest, float(hrmax), sex)
        return tr, True

    # Fallback (no HR): assume easy aerobic HRR ~0.60, then scale down to be conservative
    if hrmax and hrmax > hr_rest:
        hr_avg_est = hr_rest + 0.60 * (float(hrmax) - float(hr_rest))
        tr = _banister_trimp(dur_min, hr_avg_est, hr_rest, float(hrmax), sex)
        return 0.60 * tr, False

    # If hrmax unknown/unusable, return a low-confidence proxy (very conservative)
    return 0.0, False


def _ewma_series(daily_vals, tau_days):
    alpha = 1.0 - math.exp(-1.0 / float(tau_days))
    out = []
    ema = None
    for v in daily_vals:
        if ema is None:
            ema = v
        else:
            ema = alpha * v + (1 - alpha) * ema
        out.append(ema)
    return out

@router.get("/api/recent")
def api_recent(limit: int = Query(default=50, ge=1, le=200)):
    db = SessionLocal()
    try:
        rows = db.query(Activity).order_by(Activity.start_date.desc()).limit(limit).all()
        out = []
        for a in rows:
            out.append({
                "id": int(a.id),
                "date": a.start_date.isoformat() if a.start_date else None,
                "name": a.name,
                "sport_type": a.sport_type,
                "distance_km": (a.distance_m/1000.0) if a.distance_m else None,
                "pace_min_per_km": _pace_min_per_km(a.distance_m, a.moving_time_s),
                "avg_hr": a.average_heartrate,
                "ef": (a.distance_m / a.average_heartrate) if (a.distance_m and a.average_heartrate) else None,
            })
        return {"status":"ok","items":out}
    finally:
        db.close()

@router.get("/api/weekly")
def api_weekly(
    weeks: int = Query(default=16, ge=4, le=104),
    goal_km: float | None = Query(default=None, ge=1, le=500),
):
    db = SessionLocal()
    try:
        acts = db.query(Activity).order_by(Activity.start_date.desc()).all()
        acts = [a for a in acts if a.start_date and a.distance_m]

        if not acts:
            return {"status":"ok","weeks":[],"goal_km":goal_km,"goal_source":"none"}

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=7*weeks + 7)

        # group by ISO week (Monday start)
        wk = {}
        for a in acts:
            d = a.start_date.date()
            if d < start:
                continue
            w = _monday(d)
            wk.setdefault(w, 0.0)
            wk[w] += (a.distance_m / 1000.0)

        # build ordered list of weeks ending at current week
        week_starts = []
        cur = _monday(today)
        for i in range(weeks):
            week_starts.append(cur - timedelta(days=7*(weeks-1-i)))

        distances = [wk.get(ws, 0.0) for ws in week_starts]

        if goal_km is None:
            # auto goal = median(last up to 8 weeks) * 1.05 (gentle progression)
            tail = distances[-8:] if len(distances) >= 8 else distances
            med = statistics.median(tail) if tail else 0.0
            goal_km = max(5.0, round(med * 1.05, 1))
            goal_source = "auto(median_last_weeks*1.05)"
        else:
            goal_source = "fixed"

        out = []
        for ws, dist in zip(week_starts, distances):
            out.append({
                "week_start": ws.isoformat(),
                "distance_km": dist,
                "goal_km": goal_km,
                "fraction": (dist/goal_km) if goal_km else None,
            })

        return {"status":"ok","weeks":out,"goal_km":goal_km,"goal_source":goal_source}
    finally:
        db.close()

@router.get("/api/load")
def api_load(
    days: int = Query(default=140, ge=30, le=365),
    tau_ctl: int = Query(default=42, ge=7, le=120),
    tau_atl: int = Query(default=7, ge=3, le=42),
):
    db = SessionLocal()
    try:
        acts = db.query(Activity).order_by(Activity.start_date.asc()).all()
        acts = [a for a in acts if a.start_date and a.moving_time_s]

        if not acts:
            return {"status":"ok","series":[],"note":"No activities with timestamps."}

        hrmax = _hrmax_observed(acts)

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days-1)

        # daily load aggregation
        daily = {}
        hr_missing = 0
        for a in acts:
            d = a.start_date.date()
            if d < start or d > end:
                continue
            ld, had_hr = _load_proxy(a, hrmax)
            if not had_hr:
                hr_missing += 1
            daily[d] = daily.get(d, 0.0) + ld

        dates = [start + timedelta(days=i) for i in range(days)]
        daily_vals = [daily.get(d, 0.0) for d in dates]

        atl = _ewma_series(daily_vals, tau_atl)
        ctl = _ewma_series(daily_vals, tau_ctl)
        tsb = [c - a for c, a in zip(ctl, atl)]

        series = []
        for d, dl, c, a, t in zip(dates, daily_vals, ctl, atl, tsb):
            series.append({
                "date": d.isoformat(),
                "daily_load": dl,
                "ctl": c,
                "atl": a,
                "tsb": t,
            })

        return {
            "status":"ok",
            "hrmax_observed": hrmax,
            "hr_missing_sessions_in_window": hr_missing,
            "tau_ctl": tau_ctl,
            "tau_atl": tau_atl,
            "series": series,
            "note":"Load is an HR-based proxy (not lab TRIMP). Good for within-athlete trend + scenario planning later."
        }
    finally:
        db.close()
