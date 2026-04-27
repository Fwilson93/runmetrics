from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import engine, Base
from app.db import models as _models  # ensure tables are registered

# Routers
from app.api.health import router as health_router
from app.api.ping import router as ping_router
from app.api.strava_oauth import router as strava_oauth_router
from app.api.ingest import router as ingest_router
from app.api.streams import router as streams_router
from app.api.metrics import router as metrics_router
from app.api.analytics import router as analytics_router
from app.api.physiology import router as phys_router

app = FastAPI(title="RunMetrics", version="0.1.0")

# Allow GitHub Pages dashboard to read data
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Create tables
Base.metadata.create_all(bind=engine)

# Register routers
app.include_router(health_router)
app.include_router(ping_router)
app.include_router(strava_oauth_router)
app.include_router(ingest_router)
app.include_router(streams_router)
app.include_router(metrics_router)
app.include_router(analytics_router)
app.include_router(phys_router)
