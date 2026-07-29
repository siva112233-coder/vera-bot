"""POST /v1/context — receive and store context pushes from the judge."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.models.requests import ContextPushRequest, ContextAckResponse, ContextScope
from app.store.memory import get_store

log = logging.getLogger(__name__)
router = APIRouter()

_VALID_SCOPES = {s.value for s in ContextScope}


@router.post("/context")
async def push_context(body: ContextPushRequest):
    """
    Idempotent context push.

    - Same (scope, context_id, version) → no-op, returns accepted=True (idempotent)
    - Lower version than stored → HTTP 409 with stale_version
    - New or higher version → accepted=True, atomically replaces prior
    """
    if body.scope.value not in _VALID_SCOPES:
        raise HTTPException(
            status_code=400,
            detail={
                "accepted": False,
                "reason": "invalid_scope",
                "details": f"scope must be one of {sorted(_VALID_SCOPES)}",
            },
        )

    store = get_store()

    # True idempotency: same version already stored → return accepted=True (no-op)
    stored_version = store.get_version(body.scope.value, body.context_id)
    if stored_version is not None and stored_version == body.version:
        stored_at = store.get_stored_at(body.scope.value, body.context_id)
        ack_id = f"ack_{body.context_id}_v{body.version}"
        log.debug(
            "Idempotent re-post (same version): scope=%s id=%s version=%d",
            body.scope.value, body.context_id, body.version,
        )
        return ContextAckResponse(
            accepted=True,
            ack_id=ack_id,
            stored_at=stored_at or datetime.now(timezone.utc).isoformat(),
        )

    accepted, reason, current_version = store.put(
        scope=body.scope.value,
        context_id=body.context_id,
        version=body.version,
        payload=body.payload,
    )

    if not accepted:
        # Strict stale version (incoming < stored) → HTTP 409
        log.debug(
            "Stale version rejected: scope=%s id=%s incoming=%d stored=%d",
            body.scope.value,
            body.context_id,
            body.version,
            current_version,
        )
        return JSONResponse(
            status_code=409,
            content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": current_version,
            },
        )

    stored_at = store.get_stored_at(body.scope.value, body.context_id)
    ack_id = f"ack_{body.context_id}_v{body.version}"
    log.info(
        "Context stored: scope=%s id=%s version=%d",
        body.scope.value,
        body.context_id,
        body.version,
    )
    return ContextAckResponse(
        accepted=True,
        ack_id=ack_id,
        stored_at=stored_at or datetime.now(timezone.utc).isoformat(),
    )
