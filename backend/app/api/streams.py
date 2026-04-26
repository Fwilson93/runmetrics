from fastapi import APIRouter, Query
from datetime import datetime, timezone
import os
import requests

from app.db.session import SessionLocal
from app.db.models import StravaToken, Activity, ActivityStream

router = APIRouter()

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")

def _refresh_if_needed(db, token: StravaToken) -> StravaToken:
    now = int(datetime.now(timezone.utc).timestamp())
    if token.expires_at and now < (token.expires_at - 60):
        return token

    resp = requests.post(
        "https://www.strava.com/api/v3/oauth/token",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
        },
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data or "refresh_token" not in data or "expires_at" not in data:
        raise RuntimeError(f"Token refresh failed: {data}")

    token.access_token = data["access_token"]
    token.refresh_token = data["refresh_token"]
    token.expires_at = data["expires_at"]
    db.commit()
    return token

def _parse_after(after: str | None):
    if not after:
        return None
    # interpret YYYY-MM-DD as UTC midnight
    dt = datetime.fromisoformat(after).replace(tzinfo=timezone.utc)
    return dt

@router.get("/strava/streams")
def ingest_streams(
    after: str | None = Query(default=None, description="ISO date like 2026-01-01; select activities after this date (UTC)."),
    max_activities: int = Query(default=25, ge=1, le=200, description="Max activities to fetch streams for in this call."),
    include_latlng: bool = Query(default=False, description="Include lat/lng stream (large)."),
):
    """
    Fetch streams for activities in DB (after=...) that do not yet have streams stored.
    Stores one JSONB blob per activity (key_by_type=true).
    """
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        return {"error": "STRAVA_CLIENT_ID/STRAVA_CLIENT_SECRET not set"}

    after_dt = _parse_after(after)

    db = SessionLocal()
    try:
        token = db.query(StravaToken).order_by(StravaToken.id.desc()).first()
        if not token:
            return {"error": "No stored Strava token found. Visit /auth/strava/login first."}

        token = _refresh_if_needed(db, token)
        headers = {"Authorization": f"Bearer {token.access_token}"}

        # Find candidate activities missing streams
        q = db.query(Activity).order_by(Activity.start_date.desc())
        if after_dt:
            q = q.filter(Activity.start_date >= after_dt)

        # Only ones not already in activity_streams
        candidates = []
        for a in q.limit(1000).all():
            if db.get(ActivityStream, a.id) is None:
                candidates.append(a)
            if len(candidates) >= max_activities:
                break

        if not candidates:
            return {"status": "ok", "after": after, "considered": 0, "fetched": 0, "inserted": 0, "note": "No missing streams found."}

        base_keys = ["time", "distance", "altitude", "velocity_smooth", "grade_smooth", "cadence", "heartrate"]
        if include_latlng:
            base_keys.append("latlng")

        fetched = 0
        inserted = 0
        errors = 0

        for a in candidates:
            url = f"https://www.strava.com/api/v3/activities/{int(a.id)}/streams"
            params = {"keys": ",".join(base_keys), "key_by_type": "true"}
            r = requests.get(url, headers=headers, params=params, timeout=45)

            if r.status_code != 200:
                errors += 1
                # keep going; record a minimal failure payload for later inspection
                payload = {"error": True, "status_code": r.status_code, "text": r.text[:2000]}
                stream = ActivityStream(
                    activity_id=int(a.id),
                    athlete_id=int(a.athlete_id),
                    fetched_at=datetime.now(timezone.utc),
                    keys=base_keys,
                    raw=payload,
                )
                db.add(stream)
                db.commit()
                inserted += 1
                continue

            data = r.json()
            fetched += 1

            stream = ActivityStream(
                activity_id=int(a.id),
                athlete_id=int(a.athlete_id),
                fetched_at=datetime.now(timezone.utc),
                keys=base_keys,
                raw=data,
            )
            db.add(stream)
            db.commit()
            inserted += 1

        return {
            "status": "ok",
            "after": after,
            "considered": len(candidates),
            "fetched": fetched,
            "inserted": inserted,
            "errors": errors,
            "note": "Safe to re-run; only missing streams are fetched (existing are skipped).",
        }
    finally:
        db.close()
