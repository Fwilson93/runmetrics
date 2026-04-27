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
        ema = v if ema is None else (alpha*v + (1-alpha)*ema)
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
        return dur_min * (x*x) * 100.0
    return dur_min * 35.0

def load_proxy_from_workout(dur_min: float, intensity: float):
    return dur_min * (intensity*intensity) * 100.0

def simulate(hist_daily, add_load, days, tau_ctl=42, tau_atl=7):
    future = [add_load] + [0.0]*(days-1)
    seq = hist_daily + future
    ctl = ewma(seq, tau_ctl)[-days:]
    atl = ewma(seq, tau_atl)[-days:]
    tsb = [c-a for c,a in zip(ctl, atl)]
    return ctl, atl, tsb

def assess(tsb_final):
    if tsb_final > -5: return "good"
    if tsb_final > -15: return "caution"
    return "risky"

@router.get("/api/recommendation")
def recommendation(days: int = Query(default=7, ge=3, le=14)):
    db = SessionLocal()
    try:
        acts = db.query(Activity).order_by(Activity.start_date.asc()).all()
        acts = [a for a in acts if a.start_date and a.moving_time_s]
        if not acts:
            return {"status":"no_data"}

        hrmax = hrmax_observed(acts)

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=42-1)
        daily = {(start + timedelta(days=i)): 0.0 for i in range(42)}
        for a in acts:
            d = a.start_date.date()
            if d < start or d > end:
                continue
            daily[d] += load_proxy_from_activity(a, hrmax)

        hist_daily = [daily[start + timedelta(days=i)] for i in range(42)]
        ctl_hist = ewma(hist_daily, 42)
        atl_hist = ewma(hist_daily, 7)
        ctl0, atl0 = ctl_hist[-1], atl_hist[-1]

        candidates = [
            {"label":"Rest", "dur_min":0.0, "intensity":0.0},
            {"label":"45 min Aerobic (Z2)", "dur_min":45.0, "intensity":0.65},
            {"label":"60 min Steady", "dur_min":60.0, "intensity":0.72},
            {"label":"45 min Tempo", "dur_min":45.0, "intensity":0.80},
            {"label":"90 min Long Aerobic (Z2)", "dur_min":90.0, "intensity":0.65},
        ]

        scored = []
        for c in candidates:
            load = load_proxy_from_workout(c["dur_min"], c["intensity"])
            ctl, atl, tsb = simulate(hist_daily, load, days)
            scored.append({
                **c,
                "load_tomorrow": load,
                "delta_ctl": ctl[-1]-ctl0,
                "delta_atl": atl[-1]-atl0,
                "delta_tsb": (ctl[-1]-atl[-1]) - (ctl0-atl0),
                "tsb_final": tsb[-1],
                "recommendation": assess(tsb[-1]),
                "series": {"ctl": ctl, "atl": atl, "tsb": tsb},
            })

        scored.sort(key=lambda r: (r["tsb_final"], r["delta_ctl"]), reverse=True)
        return {"status":"ok", "best": scored[0], "candidates": scored}
    finally:
        db.close()
