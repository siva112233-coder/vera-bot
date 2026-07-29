"""
Vera FastAPI application — main entry point.

Startup lifecycle:
  1. Initialise singletons (context store, suppression registry, conversation manager)
  2. Mount all routers under /v1
  3. Global exception handler for unhandled errors
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.store.memory import get_store
from app.engine.suppression import get_suppression_registry
from app.engine.conversation import get_conversation_manager
from app.engine.trigger import get_trigger_prioritizer
from app.engine.decision import get_decision_engine
from app.api import healthz, metadata, context, tick, reply

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("vera")


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated startup/shutdown events)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up all singletons on startup."""
    log.info("Vera starting up — initialising singletons…")
    get_store()
    get_suppression_registry()
    get_conversation_manager()
    get_trigger_prioritizer()
    get_decision_engine()
    log.info("Vera ready. Version: %s", settings.version)
    yield
    log.info("Vera shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


app = FastAPI(
    title="Vera — Magicpin Merchant AI",
    description=(
        "Deterministic merchant growth assistant. "
        "Implements the 4-context framework (category, merchant, trigger, customer) "
        "to compose WhatsApp messages for merchant engagement."
    ),
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — open for judge harness access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "path": str(request.url.path)},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

for mod in (healthz, metadata, context, tick, reply):
    app.include_router(mod.router, prefix="/v1")


# ---------------------------------------------------------------------------
# Optional teardown endpoint (per testing brief §11)
# ---------------------------------------------------------------------------


@app.post("/v1/teardown")
async def teardown() -> dict:
    """Wipe all in-memory state after test ends."""
    get_store().clear()
    get_suppression_registry().clear()
    get_conversation_manager().clear()
    log.info("Teardown complete — all context cleared.")
    return {"cleared": True}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
        log_level="info",
    )
