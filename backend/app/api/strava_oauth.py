from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import os
import requests

router = APIRouter()

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")

REDIRECT_URI = "https://runmetrics.onrender.com/auth/strava/callback"

@router.get("/auth/strava/login")
def strava_login():
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

    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        },
    )

    data = response.json()

    # For now: just confirm success.
    # We will store these properly in Step 3.
    return {
        "status": "authorised",
        "athlete": data.get("athlete"),
        "expires_at": data.get("expires_at"),
    }
