import math
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query
from app.db.session import SessionLocal
from app.db.models import Activity

router = APIRouter()

def _hrmax_observed(activities):
    vals = [a.max_heartrate for a in activities if a.max_heartrate]
    return float(max(vals)) if vals else 190.0

def _banister_trimp(duration_min: float, hr_avg: float, hr_rest: float, hr_max: float, sex: str = "male") -> float:
    """
    Banister TRIMP (HR-reserve):
      TRIMP = duration_min * HRR * a * exp(b * HRR)
    male: a=0.64, b=1.92
    female: a=0.86, b=1.67
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

    return float(duration_min * hrr * a * math.exp(b * hrr))

def _ewma(values, tau_days: int):
    alpha = 1.0 - math.exp(-1.0 / float(tau_days))
    out = []
    ema = None
    for v in values:
        ema = v if ema is None else (alpha * v + (1.0 - alpha) * ema)
        out.append(ema)
    return out

def _load_from_activity(a, hrmax, hr_rest: float, sex: str):
    """
    TRIMP load from stored activity. Conservative fallback if HR missing.
    """
    if not a.moving_time_s:
        return 0.0
    dur_min = float(a.moving_time_s) / 60.0

    if a.average_heartrate and hrmax and hrmax > 0:
        return _banister_trimp(dur_min, float(a.average_heartrate), hr_rest, float(hrmax), sex)

    # conservative fallback: assume easy aerobic HRR ~ 0.60 and downscale
    if hrmax and hrmax > hr_rest:
        hr_avg_est = hr_rest + 0.60 * (float(hrmax) - float(hr_rest))
        return 0.60 * _banister_trimp(dur_min, hr_avg_est, hr_rest, float(hrmax), sex)

    return 0.0

def _load_for_planned(dur_min: float, intensity_frac_hrmax: float, hrmax: float, hr_rest: float, sex: str) -> float:
    """
    Planned workout TRIMP from (duration, intensity as fraction of HRmax).
    """
    hr_avg = float(intensity_frac_hrmax) * float(hrmax)
    return _banister_trimp(float(dur_min), hr_avg, hr_rest, float(hrmax), sex)

def _label(tsb_final: float) -> str:
    if tsb_final > -5:
        return "good"
    if tsb_final > -15:
        return "caution"
    return "risky"

@router.get("/api/scenarios_dynamic")
def scenarios_dynamic(
    days: int = Query(default=7, ge=3, le=14),
    dur_min: float = Query(default=45.0, ge=5.0, le=240.0),
    intensity: float = Query(default=0.65, ge=0.40, le=0.98),
    hr_rest: float = Query(default=50.0, ge=30.0, le=100.0),
    sex: str = Query(default="male"),
):
    """
    TRIMP-consistent scenario projection:
    - builds a 42-day TRIMP history from stored activities
    - simulates one planned workout tomorrow, then zeros for rest of horizon
    Returns schema compatible with existing frontend: {"status":"ok","scenarios":[...], ...}
    """
    db = SessionLocal()
    try:
        acts = db.query(Activity).order_by(Activity.start_date.asc()).all()
        acts = [a for a in acts if a.start_date and a.moving_time_s]
        if not acts:
            return {"status": "no_data"}

        hrmax = _hrmax_observed(acts)

        # Build 42-day history
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=42 - 1)
        daily = {(start + timedelta(days=i)): 0.0 for i in range(42)}

        for a in acts:
            d = a.start_date.astimezone(timezone.utc).date() if a.start_date.tzinfo else a.start_date.date()
            if d < start or d > end:
                continue
            daily[d] += _load_from_activity(a, hrmax, hr_rest, sex)

        hist_dates = [start + timedelta(days=i) for i in range(42)]
        hist_load = [daily[d] for d in hist_dates]

        # Baseline today
        ctl_hist = _ewma(hist_load, 42)
        atl_hist = _ewma(hist_load, 7)
        ctl0 = ctl_hist[-1]
        atl0 = atl_hist[-1]
        tsb0 = ctl0 - atl0

        # Candidate set: Rest, Custom (slider), Alt (slightly easier/harder)
        load_rest = 0.0
        load_custom = _load_for_planned(dur_min, intensity, hrmax, hr_rest, sex)

        if intensity >= 0.80:
            alt_intensity = max(0.55, intensity - 0.12)
        else:
            alt_intensity = min(0.85, intensity + 0.10)
        load_alt = _load_for_planned(dur_min, alt_intensity, hrmax, hr_rest, sex)

        candidates = [
            ("Rest", 0.0, 0.0, load_rest),
            ("Custom", float(dur_min), float(intensity), load_custom),
            ("Alt", float(dur_min), float(alt_intensity), load_alt),
        ]

        scenarios = []
        for name, dmin, inten, add_load in candidates:
            seq = hist_load + [add_load] + [0.0] * (days - 1)
            ctl = _ewma(seq, 42)[-days:]
            atl = _ewma(seq, 7)[-days:]
            tsb = [c - a for c, a in zip(ctl, atl)]
            scenarios.append({
                "name": name,
                "dur_min": dmin,
                "intensity": inten,
                "load_tomorrow": add_load,
                "delta_ctl": ctl[-1] - ctl0,
                "delta_atl": atl[-1] - atl0,
                "delta_tsb": (tsb[-1] - tsb0),
                "recommendation": _label(tsb[-1]),
                "series": {"ctl": ctl, "atl": atl, "tsb": tsb},
            })

        # rank: prefer higher final freshness, then higher ctl
        scenarios.sort(key=lambda r: (r["series"]["tsb"][-1], r["series"]["ctl"][-1]), reverse=True)

        return {
            "status": "ok",
            "days": days,
            "hrmax_observed": hrmax,
            "hr_rest": hr_rest,
            "sex": sex,
            "baseline": {"ctl": ctl0, "atl": atl0, "tsb": tsb0},
            "scenarios": scenarios,
        }
    finally:
        db.close()
