from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.ping import router as ping_router

app = FastAPI(
    title="RunMetrics",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(ping_router)
