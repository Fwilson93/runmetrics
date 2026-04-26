from fastapi import APIRouter, Query
from datetime import datetime, timezone
import os
import requests

from app.db.session import SessionLocal
from app.db.models import StravaToken, Activity

router = APIRouter()

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")

def _iso_to_dt(s: str | None):
    if not s:
        return None
    # Strava returns Z; Python wants +00:00
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def _refresh_if_needed(db, token: StravaToken) -> StravaToken:
    now = int(datetime.now(timezone.utc).timestamp())
    # refresh 60 seconds early
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

@router.get("/strava/ingest")
def ingest_activities(
    after: str | None = Query(default=None, description="ISO date like 2026-01-01; ingests activities after this date (UTC)."),
    per_page: int = Query(default=50, ge=1, le=200),
    max_pages: int = Query(default=20, ge=1, le=200),
):
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        return {"error": "STRAVA_CLIENT_ID/STRAVA_CLIENT_SECRET not set"}

    after_ts = None
    if after:
        # interpret date as UTC midnight
        after_dt = datetime.fromisoformat(after).replace(tzinfo=timezone.utc)
        after_ts = int(after_dt.timestamp())

    db = SessionLocal()
    try:
        token = db.query(StravaToken).order_by(StravaToken.id.desc()).first()
        if not token:
            return {"error": "No stored Strava token found. Visit /auth/strava/login first."}

        token = _refresh_if_needed(db, token)

        headers = {"Authorization": f"Bearer {token.access_token}"}

        inserted = 0
        updated = 0
        fetched = 0

        for page in range(1, max_pages + 1):
            params = {"page": page, "per_page": per_page}
            if after_ts:
                params["after"] = after_ts

            r = requests.get(
                "https://www.strava.com/api/v3/athlete/activities",
                headers=headers,
                params=params,
                timeout=30,
            )
            if r.status_code != 200:
                return {"error": "Strava API error", "status_code": r.status_code, "response": r.text}

            batch = r.json()
            if not batch:
                break

            fetched += len(batch)

            for a in batch:
                aid = int(a["id"])
                existing = db.get(Activity, aid)

                row = existing if existing else Activity(id=aid)
                row.athlete_id = int(a["athlete"]["id"]) if a.get("athlete") else token.athlete_id
                row.name = a.get("name")
                row.type = a.get("type")
                row.sport_type = a.get("sport_type")
                row.start_date = _iso_to_dt(a.get("start_date"))
                row.distance_m = a.get("distance")
                row.moving_time_s = a.get("moving_time")
                row.elapsed_time_s = a.get("elapsed_time")
                row.total_elevation_gain_m = a.get("total_elevation_gain")
                row.average_speed_mps = a.get("average_speed")
                row.max_speed_mps = a.get("max_speed")
                row.average_heartrate = a.get("average_heartrate")
                row.max_heartrate = a.get("max_heartrate")
                row.has_heartrate = a.get("has_heartrate")
                row.private = a.get("private")
                row.raw = a

                if existing:
                    updated += 1
                else:
                    db.add(row)
                    inserted += 1

            db.commit()

        return {
            "status": "ok",
            "after": after,
            "fetched": fetched,
            "inserted": inserted,
            "updated": updated,
            "note": "Safe to re-run; activities are upserted by id.",
        }
    finally:
        db.close()
