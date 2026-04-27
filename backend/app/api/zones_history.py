from fastapi import APIRouter, Query
from datetime import datetime, timedelta, timezone

from app.db.session import SessionLocal
from app.db.models import Activity
from app.api.physiology import estimate_zone_thresholds, estimate_hrmax

router = APIRouter()

@router.get("/api/zones_history")
def zones_history(days_ago: int = Query(default=30, ge=7, le=180)):
    """
    Estimate zones using activities up to (today - days_ago).
    This is a simple 'as-of' snapshot to show direction of change.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_ago)
        acts = db.query(Activity).filter(Activity.start_date <= cutoff).all()
        hrmax = estimate_hrmax(acts)
        est = estimate_zone_thresholds(acts, hrmax)
        if not est:
            return {"status":"insufficient_data", "days_ago": days_ago}
        return {"status":"ok", "days_ago": days_ago, **est}
    finally:
        db.close()
