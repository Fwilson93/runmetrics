from fastapi import APIRouter
from app.db.session import SessionLocal
from app.db.models import Activity, ActivityMetric

router = APIRouter()

@router.get("/metrics/derive")
def derive_metrics():
    db = SessionLocal()
    inserted = 0
    updated = 0

    try:
        activities = db.query(Activity).all()

        for a in activities:
            m = db.get(ActivityMetric, a.id)
            if not m:
                m = ActivityMetric(activity_id=a.id, athlete_id=a.athlete_id)
                db.add(m)
                inserted += 1
            else:
                updated += 1

            m.distance_m = a.distance_m
            m.moving_time_s = a.moving_time_s
            m.avg_heartrate = a.average_heartrate

            # Pace (s/km)
            if a.distance_m and a.moving_time_s and a.distance_m > 0:
                m.avg_pace_s_per_km = (a.moving_time_s / (a.distance_m / 1000.0))
            else:
                m.avg_pace_s_per_km = None

            # Elevation rate (m/hour)
            if a.total_elevation_gain_m and a.moving_time_s and a.moving_time_s > 0:
                m.elevation_rate_m_per_h = (
                    a.total_elevation_gain_m / (a.moving_time_s / 3600.0)
                )
            else:
                m.elevation_rate_m_per_h = None

            # Efficiency Factor (distance / HR)
            if a.average_heartrate and a.distance_m:
                m.efficiency_factor = a.distance_m / a.average_heartrate
            else:
                m.efficiency_factor = None

        db.commit()
        return {
            "status": "ok",
            "activities": len(activities),
            "inserted": inserted,
            "updated": updated,
            "note": "Metrics stored; safe to re-run."
        }
    finally:
        db.close()
