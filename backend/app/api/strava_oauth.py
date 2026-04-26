from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import os
import requests

from app.db.session import SessionLocal
from app.db.models import StravaToken

router = APIRouter()

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = "https://runmetrics.onrender.com/auth/strava/callback"

@router.get("/auth/strava/login")
def strava_login():
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        return {"error": "STRAVA_CLIENT_ID/STRAVA_CLIENT_SECRET not set in environment"}

    auth_url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={STRAVA_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        "&response_type=code"
        "&approval_prompt=auto"
        "&scope=read,activity:read_all"
    )
    return RedirectResponse(auth_url)

@router.get("/auth/strava/callback")
def strava_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return {"error": "Missing code from Strava redirect"}

    resp = requests.post(
        "https://www.strava.com/api/v3/oauth/token",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    data = resp.json()

    if "athlete" not in data or "access_token" not in data or "refresh_token" not in data:
        return {"error": "Token exchange failed", "response": data}

    athlete_id = data["athlete"]["id"]

    db = SessionLocal()
    try:
        token = db.query(StravaToken).filter(StravaToken.athlete_id == athlete_id).first()
        if token:
            token.access_token = data["access_token"]
            token.refresh_token = data["refresh_token"]
            token.expires_at = data["expires_at"]
        else:
            token = StravaToken(
                athlete_id=athlete_id,
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=data["expires_at"],
            )
            db.add(token)
        db.commit()
    finally:
        db.close()

    return {"status": "authorised_and_stored"}
