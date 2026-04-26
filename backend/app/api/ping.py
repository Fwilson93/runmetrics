from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()

@router.get("/ping")
def ping():
    return {"pong": True, "time_utc": datetime.now(timezone.utc).isoformat()}
