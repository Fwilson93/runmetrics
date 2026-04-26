from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import engine, Base
from app.db import models as _models  # noqa: F401

from app.api.health import router as health_router
from app.api.ping import router as ping_router
from app.api.strava_oauth import router as strava_oauth_router
from app.api.ingest import router as ingest_router
from app.api.streams import router as streams_router
from app.api.metrics import router as metrics_router
from app.api.public_api import router as public_api_router
from app.api.pmc import router as pmc_router

app = FastAPI(title="RunMetrics", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(health_router)
app.include_router(ping_router)
app.include_router(strava_oauth_router)
app.include_router(ingest_router)
app.include_router(streams_router)
app.include_router(metrics_router)
app.include_router(public_api_router)
app.include_router(pmc_router)
