from fastapi import FastAPI

from app.db.session import engine, Base
from app.db import models as _models  # noqa: F401 (registers tables)

from app.api.health import router as health_router
from app.api.ping import router as ping_router
from app.api.strava_oauth import router as strava_oauth_router
from app.api.ingest import router as ingest_router
from app.api.streams import router as streams_router

app = FastAPI(title="RunMetrics", version="0.1.0")

Base.metadata.create_all(bind=engine)

app.include_router(health_router)
app.include_router(ping_router)
app.include_router(strava_oauth_router)
app.include_router(ingest_router)
app.include_router(streams_router)
