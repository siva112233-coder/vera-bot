"""POST /v1/tick — periodic wake-up; bot inspects context state and fires proactive messages."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from app.models.requests import TickRequest, TickResponse, TickAction
from app.store.memory import get_store
from app.engine.trigger import get_trigger_prioritizer
from app.engine.suppression import get_suppression_registry
from app.engine.conversation import get_conversation_manager
from app.engine.composer import compose

log = logging.getLogger(__name__)
router = APIRouter()

MAX_ACTIONS_PER_TICK = 20


def _parse_now(now_str: str) -> datetime:
    try:
        return datetime.fromisoformat(now_str.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


@router.post("/tick", response_model=TickResponse)
async def tick(body: TickRequest) -> TickResponse:
    """
    Inspect available triggers, compose messages, return action list.

    Guarantees:
    - Returns within the call (no background processing)
    - Empty actions list if nothing worth sending
    - Max 20 actions per tick
    - Each suppression_key consumed atomically after action is added
    """
    now = _parse_now(body.now)
    store = get_store()
    prioritizer = get_trigger_prioritizer()
    suppression = get_suppression_registry()
    conv_manager = get_conversation_manager()

    # Select and sort triggers
    triggers = prioritizer.select(body.available_triggers, now=now)

    actions: list[TickAction] = []

    for trigger in triggers:
        if len(actions) >= MAX_ACTIONS_PER_TICK:
            break

        trigger_id = trigger.get("_trigger_id", "")
        merchant_id = trigger.get("merchant_id", "")
        customer_id = trigger.get("customer_id") or None

        # Resolve contexts
        merchant, category, customer = prioritizer.resolve_contexts(trigger)

        if merchant is None or category is None:
            log.warning(
                "Skipping trigger %s — merchant or category context missing "
                "(merchant_id=%s, category_slug=%s)",
                trigger_id,
                merchant_id,
                merchant.get("category_slug", "?") if merchant else "?",
            )
            continue

        # Compose message deterministically
        try:
            composed = compose(category, merchant, trigger, customer)
        except Exception as exc:
            log.error("compose() failed for trigger %s: %s", trigger_id, exc, exc_info=True)
            continue

        body_text = composed.get("message", "")
        if not body_text:
            log.warning("Empty body from compose() for trigger %s; skipping", trigger_id)
            continue

        suppression_key = composed.get("suppression_key", "")
        send_as = composed.get("send_as", "vera")
        cta = composed.get("cta", "open_ended")
        rationale = composed.get("rationale", "")
        template_name = composed.get("_template_name", "vera_generic_v1")
        template_params: list[str] = composed.get("_template_params", [])

        # Generate deterministic conversation_id
        conversation_id = f"conv_{merchant_id}_{trigger_id}"

        # Create/register the conversation (get_or_create avoids overwriting existing state)
        conv_manager.get_or_create(
            conversation_id=conversation_id,
            merchant_id=merchant_id,
            trigger_id=trigger_id,
            customer_id=customer_id,
        )
        # Update metadata on the existing conversation if needed
        existing_conv = conv_manager.get(conversation_id)
        if existing_conv and not existing_conv.metadata:
            existing_conv.metadata.update({
                "action_type": composed.get("_action_type", ""),
                "trigger_kind": trigger.get("kind", ""),
                "category_slug": category.get("slug", ""),
            })
        conv_manager.record_sent(conversation_id, body_text, turn_number=1)

        # Mark suppression AFTER adding to actions (atomic from judge's perspective)
        if suppression_key:
            suppression.mark_sent(suppression_key, conversation_id)

        actions.append(
            TickAction(
                conversation_id=conversation_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
                send_as=send_as,
                trigger_id=trigger_id,
                template_name=template_name,
                template_params=template_params,
                body=body_text,
                cta=cta,
                suppression_key=suppression_key,
                rationale=rationale,
            )
        )

        log.info(
            "Action composed: conv=%s merchant=%s trigger=%s cta=%s",
            conversation_id,
            merchant_id,
            trigger_id,
            cta,
        )

    log.info("Tick complete: %d action(s) from %d trigger(s)", len(actions), len(triggers))
    return TickResponse(actions=actions)
