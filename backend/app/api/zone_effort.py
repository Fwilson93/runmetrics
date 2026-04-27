from fastapi import APIRouter, Query
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from app.db.session import SessionLocal
from app.db.models import Activity, ActivityStream
from app.api.physiology import estimate_zone_thresholds, estimate_hrmax

router = APIRouter()

@router.get("/api/zone_effort")
def zone_effort(weeks: int = Query(default=1, ge=1, le=8)):
    db = SessionLocal()
    try:
        acts = db.query(Activity).all()
        hrmax = estimate_hrmax(acts)
        zones = estimate_zone_thresholds(acts, hrmax)
        if not zones:
            return {"status": "insufficient_data"}

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7*weeks)

        zone_minutes = defaultdict(float)

        streams = (
            db.query(ActivityStream)
            .join(Activity, Activity.id == ActivityStream.activity_id)
            .filter(Activity.start_date >= start)
            .all()
        )

        for s in streams:
            data = s.raw
            if not data or "heartrate" not in data or "time" not in data:
                continue

            hr = data["heartrate"]["data"]
            t = data["time"]["data"]

            for i in range(1, len(t)):
                dt = t[i] - t[i-1]
                h = hr[i]
                for z, (lo, hi) in zones["zones"].items():
                    if lo <= h < hi:
                        zone_minutes[z] += dt / 60.0
                        break

        # simple goals (can refine later)
        goals = {"Z1": 60, "Z2": 180, "Z3": 60, "Z4": 20, "Z5": 10}

        out = {}
        for z in zones["zones"]:
            m = zone_minutes.get(z, 0.0)
            g = goals.get(z, 60)
            out[z] = {
                "minutes": round(m, 1),
                "goal": g,
                "fraction": round(m / g, 2) if g else None
            }

        return {
            "status": "ok",
            "weeks": weeks,
            "zones": out,
            "note": "Time-in-zone computed from HR streams using data-derived thresholds."
        }
    finally:
        db.close()
