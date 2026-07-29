"""POST /v1/reply — receive merchant/customer reply; return next action."""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.models.requests import ReplyRequest, ReplyResponse, ReplyAction
from app.store.memory import get_store
from app.engine.conversation import get_conversation_manager
from app.engine.composer import compose_reply

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/reply", response_model=ReplyResponse)
async def reply(body: ReplyRequest) -> ReplyResponse:
    """
    Process an inbound reply from the merchant or customer.

    Signal detection priority:
    1. Hostile → end gracefully
    2. Auto-reply (pattern or repeated verbatim) → try once more, then end
    3. Intent accepted → switch to action mode, confirm + next step
    4. Question → contextual data-driven answer
    5. Normal → advance conversation or back off after turn 3

    Always responds within 30 seconds (pure in-memory logic, no LLM calls).
    """
    conv_manager = get_conversation_manager()
    store = get_store()

    merchant_id = body.merchant_id or ""
    trigger_id = "unknown"

    # Look up conversation metadata for richer reply composition
    existing_conv = conv_manager.get(body.conversation_id)
    action_type = "generic_nudge"
    if existing_conv:
        trigger_id = existing_conv.trigger_id
        action_type = existing_conv.metadata.get("action_type", "generic_nudge")
        merchant_id = merchant_id or existing_conv.merchant_id

    # Process the inbound message
    signal = conv_manager.process_reply(
        conversation_id=body.conversation_id,
        from_role=body.from_role,
        message=body.message,
        turn_number=body.turn_number,
        merchant_id=merchant_id,
        trigger_id=trigger_id,
    )

    # Resolve contexts for richer reply generation
    merchant: dict | None = store.get_merchant(merchant_id) if merchant_id else None
    category: dict | None = None
    customer: dict | None = None
    trigger: dict | None = None

    if merchant:
        cat_slug = merchant.get("category_slug", "")
        category = store.get_category(cat_slug) if cat_slug else None

    if body.customer_id:
        customer = store.get_customer(body.customer_id)

    if trigger_id and trigger_id != "unknown":
        trigger = store.get_trigger(trigger_id)

    # Compose reply
    reply_dict = compose_reply(
        conversation_signal=signal,
        inbound_message=body.message,
        action_type=action_type,
        merchant=merchant,
        category=category,
        customer=customer,
        trigger=trigger,
    )

    action_str = reply_dict.get("action", "send")
    reply_body = reply_dict.get("body")
    reply_cta = reply_dict.get("cta")
    wait_secs = reply_dict.get("wait_seconds")
    rationale = reply_dict.get("rationale", "")

    # Record Vera's reply in conversation (if sending)
    if action_str == "send" and reply_body:
        conv_manager.record_sent(
            body.conversation_id,
            reply_body,
            turn_number=body.turn_number + 1,
        )

    if action_str == "end":
        conv_manager.end(body.conversation_id)

    log.info(
        "Reply: conv=%s turn=%d action=%s",
        body.conversation_id,
        body.turn_number,
        action_str,
    )

    return ReplyResponse(
        action=ReplyAction(action_str),
        body=reply_body,
        cta=reply_cta,
        wait_seconds=wait_secs,
        rationale=rationale,
    )
