from fastapi import APIRouter
from datetime import datetime, timedelta, timezone
import math
import statistics

from app.db.session import SessionLocal
from app.db.models import Activity

router = APIRouter()

def ewma(vals, tau):
    a = 1 - math.exp(-1/tau)
    out, ema = [], None
    for v in vals:
        ema = v if ema is None else a*v + (1-a)*ema
        out.append(ema)
    return out

def estimate_hrmax(acts):
    vals = [a.max_heartrate for a in acts if a.max_heartrate]
    return max(vals) if vals else 190

def estimate_zone_thresholds(acts, hrmax):
    hrs, speeds = [], []
    for a in acts:
        if a.average_heartrate and a.average_speed_mps:
            hrs.append(a.average_heartrate)
            speeds.append(a.average_speed_mps)

    if len(hrs) < 10:
        return None

    # crude but defensible: percentiles of HR distribution weighted by speed
    lt1 = statistics.quantiles(hrs, n=4)[0]   # ~25th %ile
    lt2 = statistics.quantiles(hrs, n=4)[2]   # ~75th %ile

    return {
        "hrmax": hrmax,
        "lt1_hr": int(lt1),
        "lt2_hr": int(lt2),
        "zones": {
            "Z1": (0.60*hrmax, lt1),
            "Z2": (lt1, 0.85*lt2),
            "Z3": (0.85*lt2, lt2),
            "Z4": (lt2, 0.95*hrmax),
            "Z5": (0.95*hrmax, hrmax)
        }
    }

@router.get("/api/zones")
def zones():
    db = SessionLocal()
    try:
        acts = db.query(Activity).all()
        hrmax = estimate_hrmax(acts)
        est = estimate_zone_thresholds(acts, hrmax)
        if not est:
            return {"status":"insufficient_data"}
        return {"status":"ok", **est}
    finally:
        db.close()

@router.get("/api/scenarios")
def scenarios(days: int = 14):
    db = SessionLocal()
    try:
        acts = db.query(Activity).order_by(Activity.start_date.asc()).all()
        acts = [a for a in acts if a.start_date and a.moving_time_s]

        if not acts:
            return {"status":"no_data"}

        hrmax = estimate_hrmax(acts)

        # build daily historical load
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=42)

        daily = {}
        for a in acts:
            d = a.start_date.date()
            if d < start or d > end:
                continue
            if a.average_heartrate:
                x = (a.average_heartrate/hrmax)**2
                load = (a.moving_time_s/60)*x*100
            else:
                load = (a.moving_time_s/60)*30
            daily[d] = daily.get(d, 0) + load

        days_hist = [start + timedelta(days=i) for i in range((end-start).days+1)]
        hist_load = [daily.get(d,0) for d in days_hist]

        ctl = ewma(hist_load, 42)
        atl = ewma(hist_load, 7)

        ctl0, atl0 = ctl[-1], atl[-1]

        scenarios = [
            ("Rest", 0),
            ("45min Z2", 45*0.65*100),
            ("Steady 60min", 60*0.72*100),
            ("Long easy 90min", 90*0.65*100),
            ("Hard intervals", 60*0.88*100)
        ]

        out = []
        for name, load in scenarios:
            loads = hist_load + [load] + [0]*(days-1)
            ctl_s = ewma(loads, 42)[-days:]
            atl_s = ewma(loads, 7)[-days:]
            tsb_s = [c-a for c,a in zip(ctl_s, atl_s)]
            out.append({
                "name": name,
                "delta_ctl": ctl_s[-1]-ctl0,
                "delta_atl": atl_s[-1]-atl0,
                "delta_tsb": tsb_s[-1],
                "recommendation": "good" if tsb_s[-1] > -10 else "risky",
                "series": {
                    "ctl": ctl_s,
                    "atl": atl_s,
                    "tsb": tsb_s
                }
            })

        # simple ranking
        out.sort(key=lambda x: (-x["delta_tsb"], -x["delta_ctl"]))
        return {"status":"ok","scenarios":out}
    finally:
        db.close()
