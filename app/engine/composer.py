"""
compose() — top-level deterministic message composition function.

Orchestrates: DecisionEngine → FactBag → TemplateRegistry → MessageResult.
Also handles reply composition for the conversation manager.
"""
from __future__ import annotations

from typing import Any

from app.engine.decision import get_decision_engine
from app.templates.messages import build_fact_bag, render, FactBag, _offer_or_fallback


# ---------------------------------------------------------------------------
# Primary compose function
# ---------------------------------------------------------------------------


def compose(
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Deterministic message composition.

    Inputs are raw payload dicts (from context store or seed JSON).
    Returns:
        {
            "message": str,          # WhatsApp body
            "cta": str,              # CTA type string
            "send_as": str,          # "vera" | "merchant_on_behalf"
            "suppression_key": str,
            "rationale": str,
        }
    """
    engine = get_decision_engine()
    spec = engine.decide(trigger, merchant, category, customer)
    rationale = engine.build_rationale(spec, trigger, merchant, category, customer)

    fb = build_fact_bag(category, merchant, trigger, customer)
    result = render(spec.action_type, fb.category_slug, fb)

    # The decision engine's send_as takes priority (handles customer-scope override)
    send_as = spec.send_as

    return {
        "message": result.body,
        "cta": result.cta,
        "send_as": send_as,
        "suppression_key": result.suppression_key or trigger.get("suppression_key", ""),
        "rationale": rationale,
        # Internal fields used by tick handler
        "_template_name": result.template_name,
        "_template_params": result.template_params,
    }


# ---------------------------------------------------------------------------
# Reply composition — generates follow-up responses in an ongoing conversation
# ---------------------------------------------------------------------------


_INTENT_FOLLOWUPS: dict[str, str] = {
    "share_research": (
        "Sending the abstract now. I'll also draft a 90-second patient-ed WhatsApp you can forward — "
        "just confirm you're happy with the tone and I'll push it."
    ),
    "compliance_alert": (
        "Here's your compliance checklist — I'll keep it to the 3 highest-priority items. "
        "Let me know when you've reviewed and I'll help file the documentation."
    ),
    "alert_perf_dip": (
        "Starting on it now. I'll refresh your GBP description + push your offer to the top. "
        "Should be live within 15 minutes."
    ),
    "festival_promo": (
        "Drafting the GBP post + WhatsApp campaign now. I'll have a preview for you in a few minutes."
    ),
    "renewal_nudge": (
        "Sending the renewal link now. Your profile stays active and all campaigns continue without interruption."
    ),
    "winback_pitch": (
        "Great — here are the reactivation steps. Takes about 10 minutes. "
        "I'll monitor your profile and let you know when it's fully live."
    ),
    "verification_nudge": (
        "Starting the GBP verification walkthrough. Step 1: log into your Google account "
        "and go to business.google.com. Let me know when you're there."
    ),
    "competitor_alert": (
        "Drafting the GBP description update now to highlight your differentiators. "
        "I'll send a preview for your approval."
    ),
    "review_action": (
        "Here's a copy-paste response template for the reviews. "
        "I'd also recommend adding 'estimated wait time' to your GBP description this week."
    ),
    "supply_action": (
        "Filtering your customer list for this molecule now. "
        "I'll draft a WhatsApp recall notice for your review in the next few minutes."
    ),
    "event_promo": (
        "Sending the WhatsApp blast + GBP post now. "
        "I'll time the blast for 4 PM so customers see it before the match."
    ),
    "seasonal_demand": (
        "Drafting the GBP post for your summer essentials now. "
        "I'll also suggest shelf placement for your top 3 summer products."
    ),
    "planning_assist": (
        "Here's the first draft. Review it and let me know what to change — "
        "I can have the final version ready in 10 minutes."
    ),
    "cde_share": (
        "Saving the webinar link for you. I'll send a reminder 2 hours before it starts on the day."
    ),
    "recall_customer": (
        "Booking confirmed — I'll send a reminder to the customer 24 hours before the appointment."
    ),
    "refill_reminder": (
        "Delivery scheduled. I'll send a confirmation to the customer with the expected delivery window."
    ),
    "trial_convert": (
        "Spot locked in! I'll send the customer a confirmation and a welcome message for their first paid class."
    ),
    "bridal_followup": (
        "Appointment booked. I'll follow up with a prep checklist for the customer 48 hours before."
    ),
}

_GENERIC_INTENT_FOLLOWUP = (
    "On it — I'll have the first version ready shortly. "
    "Let me know if there's anything specific you'd like me to focus on."
)

_QUESTION_FOLLOWUP = (
    "Good question. Based on your current numbers — {perf_summary} — "
    "the most impactful move right now is {top_recommendation}. "
    "Want me to go ahead?"
)

_AUTO_REPLY_ATTEMPT = (
    "Looks like this might be an auto-reply. "
    "If you're there and want to continue, just send any message. "
    "Happy to help when you're ready."
)

_GRACEFUL_EXIT_MERCHANT = (
    "Understood, no problem. I'll check back in when something relevant comes up. "
    "Best of luck with the business! 🙂"
)

_GRACEFUL_EXIT_HINDI = (
    "Samajh gaya. Koi baat nahi — jab zaroorat ho, main yahan hoon. "
    "Business ke liye best wishes! 🙂"
)


from app.engine.conversation import ConversationState


def compose_reply(
    conversation_signal: dict[str, Any],
    inbound_message: str,
    action_type: str,
    merchant: dict[str, Any] | None = None,
    category: dict[str, Any] | None = None,
    customer: dict[str, Any] | None = None,
    trigger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Compose a reply given the conversation signal dict from ConversationManager.

    Returns a ReplyResponse-compatible dict:
        { action, body?, cta?, wait_seconds?, rationale }
    """
    state = conversation_signal.get("state", "qualifying")
    is_auto = conversation_signal.get("is_auto_reply", False)
    is_hostile = conversation_signal.get("is_hostile", False)
    is_intent = conversation_signal.get("is_intent_accept", False)
    is_question = conversation_signal.get("is_question", False)
    auto_count = conversation_signal.get("auto_reply_count", 0)
    vera_turns = conversation_signal.get("vera_turn_count", 1)

    # ── Ended state / hostile
    if is_hostile or state == ConversationState.ENDED or getattr(state, "value", state) == "ended":
        use_hindi = False
        if merchant:
            langs = merchant.get("identity", {}).get("languages", [])
            use_hindi = "hi" in langs
        body = _GRACEFUL_EXIT_HINDI if use_hindi else _GRACEFUL_EXIT_MERCHANT
        return {
            "action": "end",
            "body": body,
            "rationale": "Merchant signalled not-interested or hostile; gracefully exiting.",
        }

    # ── Auto-reply detected
    if is_auto:
        return {
            "action": "end",
            "body": None,
            "rationale": "Auto-reply pattern detected; ending conversation to prevent auto-reply loop.",
        }

    # ── Intent accepted → action mode
    if is_intent:
        followup = _INTENT_FOLLOWUPS.get(action_type, _GENERIC_INTENT_FOLLOWUP)
        return {
            "action": "send",
            "body": followup,
            "cta": "open_ended",
            "rationale": f"Merchant accepted; switching to action mode for {action_type}.",
        }

    # ── Question from merchant
    if is_question and merchant:
        perf = merchant.get("performance", {})
        views = perf.get("views", 0)
        calls = perf.get("calls", 0)
        ctr = perf.get("ctr", 0.0)
        perf_summary = f"{views:,} views, {calls} calls, {ctr * 100:.1f}% CTR this month"
        rec_map = {
            "share_research": "review the digest item and decide on recall interval changes",
            "alert_perf_dip": "push a refreshed GBP description with your top offer",
            "festival_promo": "launch the festival campaign before competitors do",
        }
        top_rec = rec_map.get(action_type, "take the next step we discussed")
        body = _QUESTION_FOLLOWUP.format(
            perf_summary=perf_summary,
            top_recommendation=top_rec,
        )
        return {
            "action": "send",
            "body": body,
            "cta": "open_ended",
            "rationale": "Merchant asked a follow-up question; contextual data-driven answer.",
        }

    # ── Normal follow-up (turn 3+)
    if vera_turns >= 3:
        return {
            "action": "wait",
            "wait_seconds": 1800,
            "rationale": "Conversation advanced; backing off 30 min before next nudge.",
        }

    # ── Generic contextual advance
    offer = ""
    if merchant:
        offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
        offer = offers[0].get("title", "") if offers else ""
    offer_clause = f' Your "{offer}" offer could be the hook.' if offer else ""
    body = (
        f"Got it — noted.{offer_clause} "
        f"Want me to take the next step, or is there something specific you'd like to try first?"
    )
    return {
        "action": "send",
        "body": body,
        "cta": "open_ended",
        "rationale": "Normal reply; advancing conversation with open next-step.",
    }
