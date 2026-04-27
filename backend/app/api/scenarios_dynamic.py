from fastapi import APIRouter, Query
from datetime import datetime, timedelta, timezone
import math

from app.db.session import SessionLocal
from app.db.models import Activity

router = APIRouter()

def ewma(vals, tau_days: int):
    alpha = 1.0 - math.exp(-1.0 / float(tau_days))
    out, ema = [], None
    for v in vals:
        ema = v if ema is None else (alpha * v + (1.0 - alpha) * ema)
        out.append(ema)
    return out

def hrmax_observed(acts):
    vals = [a.max_heartrate for a in acts if a.max_heartrate]
    return max(vals) if vals else 190.0

def load_proxy_from_activity(a, hrmax):
    if not a.moving_time_s:
        return 0.0
    dur_min = a.moving_time_s / 60.0
    if a.average_heartrate and hrmax and hrmax > 0:
        x = (a.average_heartrate / hrmax)
        return dur_min * (x * x) * 100.0
    return dur_min * 35.0

def load_proxy_from_workout(dur_min: float, intensity: float):
    return dur_min * (intensity * intensity) * 100.0

def simulate(hist_daily, add_load, days, tau_ctl=42, tau_atl=7):
    future = [add_load] + [0.0] * (days - 1)
    seq = hist_daily + future
    ctl = ewma(seq, tau_ctl)[-days:]
    atl = ewma(seq, tau_atl)[-days:]
    tsb = [c - a for c, a in zip(ctl, atl)]
    return ctl, atl, tsb

def label(rec_tsb_final):
    if rec_tsb_final > -5:
        return "good"
    if rec_tsb_final > -15:
        return "caution"
    return "risky"

@router.get("/api/scenarios_dynamic")
def scenarios_dynamic(
    days: int = Query(default=14, ge=7, le=28),
    dur_min: float = Query(default=45.0, ge=0.0, le=240.0),
    intensity: float = Query(default=0.65, ge=0.40, le=0.98),
):
    db = SessionLocal()
    try:
        acts = db.query(Activity).order_by(Activity.start_date.asc()).all()
        acts = [a for a in acts if a.start_date and a.moving_time_s]
        if not acts:
            return {"status": "no_data"}

        hrmax = hrmax_observed(acts)

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=42 - 1)

        daily = { (start + timedelta(days=i)): 0.0 for i in range(42) }
        for a in acts:
            d = a.start_date.date()
            if d < start or d > end:
                continue
            daily[d] += load_proxy_from_activity(a, hrmax)

        dates = [start + timedelta(days=i) for i in range(42)]
        hist_daily = [daily[d] for d in dates]

        ctl_hist = ewma(hist_daily, 42)
        atl_hist = ewma(hist_daily, 7)
        ctl0, atl0, tsb0 = ctl_hist[-1], atl_hist[-1], (ctl_hist[-1] - atl_hist[-1])

        # candidates (structured)
        rest = {"name":"Rest", "dur_min":0.0, "intensity":0.0, "load":0.0}

        custom_load = load_proxy_from_workout(dur_min, intensity)
        custom = {"name":"Custom", "dur_min":dur_min, "intensity":intensity, "load":custom_load}

        if intensity >= 0.80:
            alt_intensity = max(0.55, intensity - 0.12)
        else:
            alt_intensity = min(0.85, intensity + 0.10)
        alt_load = load_proxy_from_workout(dur_min, alt_intensity)
        alt = {"name":"Alt", "dur_min":dur_min, "intensity":alt_intensity, "load":alt_load}

        candidates = [rest, custom, alt]

        results = []
        for c in candidates:
            ctl, atl, tsb = simulate(hist_daily, c["load"], days)
            results.append({
                "name": c["name"],
                "dur_min": c["dur_min"],
                "intensity": c["intensity"],
                "load_tomorrow": c["load"],
                "delta_ctl": ctl[-1] - ctl0,
                "delta_atl": atl[-1] - atl0,
                "delta_tsb": tsb[-1] - tsb0,
                "series": {"ctl": ctl, "atl": atl, "tsb": tsb},
                "recommendation": label(tsb[-1]),
            })

        results.sort(key=lambda r: (r["series"]["tsb"][-1], r["series"]["ctl"][-1]), reverse=True)

        return {
            "status": "ok",
            "hrmax_observed": hrmax,
            "dur_min": dur_min,
            "intensity": intensity,
            "days": days,
            "baseline": {"ctl": ctl0, "atl": atl0, "tsb": tsb0},
            "scenarios": results,
        }
    finally:
        db.close()
