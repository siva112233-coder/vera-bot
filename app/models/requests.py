"""Request/response models for all API endpoints (Pydantic v2)."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------


class ContextScope(str, Enum):
    category = "category"
    merchant = "merchant"
    customer = "customer"
    trigger = "trigger"


class ReplyAction(str, Enum):
    send = "send"
    wait = "wait"
    end = "end"


# ---------------------------------------------------------------------------
# /v1/context
# ---------------------------------------------------------------------------


class ContextPushRequest(BaseModel):
    scope: ContextScope
    context_id: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)
    payload: dict[str, Any]
    delivered_at: str


class ContextAckResponse(BaseModel):
    accepted: bool
    ack_id: str | None = None
    stored_at: str | None = None
    reason: str | None = None
    current_version: int | None = None
    details: str | None = None


# ---------------------------------------------------------------------------
# /v1/tick
# ---------------------------------------------------------------------------


class TickRequest(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class TickAction(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: str | None = None
    send_as: str  # "vera" | "merchant_on_behalf"
    trigger_id: str
    template_name: str
    template_params: list[str] = Field(default_factory=list)
    body: str
    cta: str
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: list[TickAction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# /v1/reply
# ---------------------------------------------------------------------------


class ReplyRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str = "merchant"  # "merchant" | "customer"
    message: str
    received_at: str
    turn_number: int = Field(..., ge=1)


class ReplyResponse(BaseModel):
    action: ReplyAction
    body: str | None = None
    cta: str | None = None
    wait_seconds: int | None = None
    rationale: str


# ---------------------------------------------------------------------------
# /v1/healthz
# ---------------------------------------------------------------------------


class ContextCounts(BaseModel):
    category: int = 0
    merchant: int = 0
    customer: int = 0
    trigger: int = 0


class HealthzResponse(BaseModel):
    status: str = "ok"
    uptime_seconds: int
    contexts_loaded: ContextCounts


# ---------------------------------------------------------------------------
# /v1/metadata
# ---------------------------------------------------------------------------


class MetadataResponse(BaseModel):
    team_name: str
    team_members: list[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str
