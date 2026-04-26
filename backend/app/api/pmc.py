from fastapi import APIRouter, Query
from datetime import datetime, timezone, date, timedelta
import math
import os
from sqlalchemy import desc

from app.db.session import SessionLocal
from app.db.models import Activity, DailyPMC

router = APIRouter()

def _day(dts):
    if not dts:
        return None
    # ensure date in UTC
    try:
        return dts.astimezone(timezone.utc).date()
    except Exception:
        return dts.date()

def _banister_trimp(duration_min: float, hr_avg: float, hr_rest: float, hr_max: float, sex: str) -> float | None:
    if duration_min <= 0 or hr_avg is None:
        return None
    if hr_max <= hr_rest:
        return None
    hrr = (hr_avg - hr_rest) / (hr_max - hr_rest)
    # clamp
    hrr = max(0.0, min(1.0, hrr))

    sex = (sex or "male").lower()
    # Classic coefficients (male: 0.64, 1.92; female: 0.86, 1.67) 【4-98bbb0】【6-01a3fe】【5-c6e8c3】
    if sex.startswith("f"):
        a, b = 0.86, 1.67
    else:
        a, b = 0.64, 1.92

    return float(duration_min * hrr * a * math.exp(b * hrr))

def _ewma_update(prev: float, x: float, tau: float) -> float:
    # PMC update form (commonly presented as CTL_today = CTL_yesterday + (TSS_today - CTL_yesterday)/tau). 【3-dc96f1】
    return prev + (x - prev) / tau

@router.get("/pmc/recompute")
def pmc_recompute(
    hr_rest: float = Query(default=50.0, ge=30.0, le=100.0, description="Resting HR (bpm) used for TRIMP (default 50)."),
    hr_max: float = Query(default=190.0, ge=120.0, le=230.0, description="Max HR (bpm) used for TRIMP (default 190)."),
    sex: str = Query(default="male", description="male/female TRIMP weighting."),
    ctl_tau: int = Query(default=42, ge=14, le=90, description="CTL time constant in days (default 42)."),
    atl_tau: int = Query(default=7, ge=3, le=21, description="ATL time constant in days (default 7)."),
):
    """
    Recompute daily TRIMP + CTL/ATL/TSB across all stored activities.
    """
    db = SessionLocal()
    try:
        acts = db.query(Activity).order_by(Activity.start_date.asc()).all()
        if not acts:
            return {"status": "ok", "note": "No activities found."}

        athlete_id = int(acts[-1].athlete_id)

        # Build daily TRIMP sums
        daily = {}
        earliest = None
        latest = None

        for a in acts:
            d = _day(a.start_date)
            if not d:
                continue
            earliest = d if earliest is None else min(earliest, d)
            latest = d if latest is None else max(latest, d)

            if a.moving_time_s and a.average_heartrate:
                tr = _banister_trimp(a.moving_time_s / 60.0, float(a.average_heartrate), hr_rest, hr_max, sex)
            else:
                tr = None

            # if HR missing, treat as 0 load for PMC input (explicit)
            daily.setdefault(d, 0.0)
            if tr is not None:
                daily[d] += tr

        # Fill missing days with 0 load
        days = []
        cur = earliest
        while cur <= latest:
            days.append(cur)
            cur += timedelta(days=1)

        # Remove old rows for this athlete (simple approach for now)
        db.query(DailyPMC).filter(DailyPMC.athlete_id == athlete_id).delete()
        db.commit()

        ctl = 0.0
        atl = 0.0

        now = datetime.now(timezone.utc)

        for d in days:
            x = float(daily.get(d, 0.0))  # daily TRIMP
            ctl = _ewma_update(ctl, x, float(ctl_tau))
            atl = _ewma_update(atl, x, float(atl_tau))
            tsb = ctl - atl

            row = DailyPMC(
                day=d,
                athlete_id=athlete_id,
                trimp=x,
                ctl=float(ctl),
                atl=float(atl),
                tsb=float(tsb),
                computed_at=now,
                params={
                    "method": "banister_trimp",
                    "hr_rest": hr_rest,
                    "hr_max": hr_max,
                    "sex": sex,
                    "ctl_tau": ctl_tau,
                    "atl_tau": atl_tau
                }
            )
            db.add(row)

        db.commit()

        return {
            "status": "ok",
            "days": len(days),
            "athlete_id": athlete_id,
            "params": {"hr_rest": hr_rest, "hr_max": hr_max, "sex": sex, "ctl_tau": ctl_tau, "atl_tau": atl_tau},
            "note": "PMC recomputed. CTL=fitness(42d), ATL=fatigue(7d), TSB=form(CTL-ATL)."
        }
    finally:
        db.close()

@router.get("/api/pmc")
def api_pmc(days: int = Query(default=120, ge=7, le=1000)):
    """
    Return last N days of PMC (date, trimp, ctl, atl, tsb).
    """
    db = SessionLocal()
    try:
        rows = db.query(DailyPMC).order_by(desc(DailyPMC.day)).limit(days).all()
        rows = list(reversed(rows))

        out = []
        for r in rows:
            out.append({
                "day": r.day.isoformat(),
                "trimp": r.trimp,
                "ctl": r.ctl,
                "atl": r.atl,
                "tsb": r.tsb,
            })

        return {"status": "ok", "count": len(out), "pmc": out}
    finally:
        db.close()

@router.get("/api/status")
def api_status():
    """
    Return latest CTL/ATL/TSB and 7-day changes.
    """
    db = SessionLocal()
    try:
        latest = db.query(DailyPMC).order_by(desc(DailyPMC.day)).first()
        if not latest:
            return {"status": "ok", "note": "No PMC data yet. Call /pmc/recompute."}

        # 7 days ago (closest)
        seven = db.query(DailyPMC).order_by(desc(DailyPMC.day)).offset(6).limit(1).first()
        def d(x): return float(x) if x is not None else None

        return {
            "status": "ok",
            "day": latest.day.isoformat(),
            "ctl": d(latest.ctl),
            "atl": d(latest.atl),
            "tsb": d(latest.tsb),
            "delta7_ctl": (d(latest.ctl) - d(seven.ctl)) if seven and latest.ctl is not None and seven.ctl is not None else None,
            "delta7_atl": (d(latest.atl) - d(seven.atl)) if seven and latest.atl is not None and seven.atl is not None else None,
            "delta7_tsb": (d(latest.tsb) - d(seven.tsb)) if seven and latest.tsb is not None and seven.tsb is not None else None,
            "params": latest.params,
            "labels": {"ctl": "Fitness", "atl": "Fatigue", "tsb": "Form"}
        }
    finally:
        db.close()
