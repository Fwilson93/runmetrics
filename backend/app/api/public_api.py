from fastapi import APIRouter, Query
from datetime import datetime, timezone
from sqlalchemy import desc

from app.db.session import SessionLocal
from app.db.models import Activity, ActivityMetric

router = APIRouter()

def _dt_to_iso(dt):
    if not dt:
        return None
    try:
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        # if it's naive, treat as UTC
        return dt.replace(tzinfo=timezone.utc).isoformat()

@router.get("/api/activities")
def api_activities(limit: int = Query(default=50, ge=1, le=500)):
    """
    Returns recent activities joined with derived metrics (if present).
    """
    db = SessionLocal()
    try:
        # newest first
        acts = db.query(Activity).order_by(desc(Activity.start_date)).limit(limit).all()

        # pull metrics in one go
        ids = [a.id for a in acts]
        metrics = {}
        if ids:
            ms = db.query(ActivityMetric).filter(ActivityMetric.activity_id.in_(ids)).all()
            metrics = {m.activity_id: m for m in ms}

        out = []
        for a in acts:
            m = metrics.get(a.id)
            out.append({
                "activity_id": int(a.id),
                "start_date": _dt_to_iso(a.start_date),
                "name": a.name,
                "type": a.type,
                "sport_type": a.sport_type,
                "distance_km": (a.distance_m / 1000.0) if a.distance_m else None,
                "moving_time_s": a.moving_time_s,
                "avg_heartrate": a.average_heartrate,
                "avg_pace_min_per_km": (m.avg_pace_s_per_km / 60.0) if (m and m.avg_pace_s_per_km) else None,
                "efficiency_factor": m.efficiency_factor if m else None,
                "elevation_rate_m_per_h": m.elevation_rate_m_per_h if m else None,
            })
        return {"status": "ok", "count": len(out), "activities": out}
    finally:
        db.close()

@router.get("/api/metrics")
def api_metrics(limit: int = Query(default=200, ge=1, le=2000)):
    """
    Returns EF time series (and pace/HR) joined with Activity start_date.
    """
    db = SessionLocal()
    try:
        q = (
            db.query(ActivityMetric, Activity)
              .join(Activity, Activity.id == ActivityMetric.activity_id)
              .order_by(desc(Activity.start_date))
              .limit(limit)
        )
        rows = q.all()

        out = []
        for m, a in rows:
            out.append({
                "activity_id": int(a.id),
                "start_date": _dt_to_iso(a.start_date),
                "distance_km": (a.distance_m / 1000.0) if a.distance_m else None,
                "avg_heartrate": a.average_heartrate,
                "avg_pace_min_per_km": (m.avg_pace_s_per_km / 60.0) if m.avg_pace_s_per_km else None,
                "efficiency_factor": m.efficiency_factor,
                "elevation_rate_m_per_h": m.elevation_rate_m_per_h,
            })
        return {"status": "ok", "count": len(out), "metrics": out}
    finally:
        db.close()
