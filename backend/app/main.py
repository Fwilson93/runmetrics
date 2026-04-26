from fastapi import FastAPI

from app.db.session import engine, Base
from app.db.models import StravaToken  # noqa: F401 (ensures table is registered)

from app.api.health import router as health_router
from app.api.ping import router as ping_router
from app.api.strava_oauth import router as strava_oauth_router

app = FastAPI(title="RunMetrics", version="0.1.0")

Base.metadata.create_all(bind=engine)

app.include_router(health_router)
app.include_router(ping_router)
app.include_router(strava_oauth_router)
