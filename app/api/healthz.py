"""GET /v1/healthz — liveness and readiness probe."""
from __future__ import annotations

from fastapi import APIRouter

from app.models.requests import HealthzResponse, ContextCounts
from app.store.memory import get_store

router = APIRouter()


@router.get("/healthz", response_model=HealthzResponse)
async def healthz() -> HealthzResponse:
    store = get_store()
    counts = store.counts()
    return HealthzResponse(
        status="ok",
        uptime_seconds=store.uptime_seconds(),
        contexts_loaded=ContextCounts(**counts),
    )
