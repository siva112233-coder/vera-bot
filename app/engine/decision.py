"""
Deterministic decision engine.

Maps (trigger_kind, category_slug) → ActionSpec
which drives: action_type, CTA type, send_as, template_key, rationale template.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionSpec:
    action_type: str
    cta: str                  # "open_ended" | "binary_yes_stop" | "slot_choice" | "confirm" | "none"
    send_as: str              # "vera" | "merchant_on_behalf"
    template_key: str         # (action_type, category_slug) for template lookup
    rationale_template: str   # short rationale describing why this action was chosen


# ---------------------------------------------------------------------------
# Trigger kind → base ActionSpec (category-agnostic defaults)
# ---------------------------------------------------------------------------

_TRIGGER_KIND_DEFAULTS: dict[str, ActionSpec] = {
    # ── Research / knowledge
    "research_digest": ActionSpec(
        action_type="share_research",
        cta="open_ended",
        send_as="vera",
        template_key="share_research",
        rationale_template="External research digest relevant to {category}; anchoring on clinical/peer data to drive engagement.",
    ),
    "cde_opportunity": ActionSpec(
        action_type="cde_share",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="cde_share",
        rationale_template="CDE / continuing-education opportunity for {category} professional; low-urgency information value.",
    ),
    # ── Compliance / regulation
    "regulation_change": ActionSpec(
        action_type="compliance_alert",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="compliance_alert",
        rationale_template="Regulatory change with deadline; compliance framing creates urgency without hype.",
    ),
    # ── Performance signals
    "perf_dip": ActionSpec(
        action_type="alert_perf_dip",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="alert_perf_dip",
        rationale_template="Performance dip detected on {metric}; loss-aversion framing + single fix proposed.",
    ),
    "seasonal_perf_dip": ActionSpec(
        action_type="alert_seasonal_dip",
        cta="open_ended",
        send_as="vera",
        template_key="alert_seasonal_dip",
        rationale_template="Expected seasonal dip; re-frame as normal, shift focus to retention.",
    ),
    "perf_spike": ActionSpec(
        action_type="celebrate_amplify",
        cta="open_ended",
        send_as="vera",
        template_key="celebrate_amplify",
        rationale_template="Performance spike detected; amplify momentum with low-friction next step.",
    ),
    # ── Customer triggers (customer-facing)
    "recall_due": ActionSpec(
        action_type="recall_customer",
        cta="slot_choice",
        send_as="merchant_on_behalf",
        template_key="recall_customer",
        rationale_template="6-month recall window open for {customer_name}; sending on behalf of merchant with available slots.",
    ),
    "chronic_refill_due": ActionSpec(
        action_type="refill_reminder",
        cta="confirm",
        send_as="merchant_on_behalf",
        template_key="refill_reminder",
        rationale_template="Chronic prescription refill due; high-compliance customer, delivery address saved.",
    ),
    "trial_followup": ActionSpec(
        action_type="trial_convert",
        cta="confirm",
        send_as="merchant_on_behalf",
        template_key="trial_convert",
        rationale_template="Post-trial conversion window; personalised follow-up to convert to paid membership.",
    ),
    "wedding_package_followup": ActionSpec(
        action_type="bridal_followup",
        cta="slot_choice",
        send_as="merchant_on_behalf",
        template_key="bridal_followup",
        rationale_template="Wedding date approaching; next skincare/prep step open for the bridal customer.",
    ),
    "customer_lapsed_hard": ActionSpec(
        action_type="winback_customer",
        cta="binary_yes_stop",
        send_as="merchant_on_behalf",
        template_key="winback_customer",
        rationale_template="Hard-lapsed customer; personalised winback referencing prior focus area.",
    ),
    # ── Merchant account triggers
    "renewal_due": ActionSpec(
        action_type="renewal_nudge",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="renewal_nudge",
        rationale_template="Subscription renewal due in {days_remaining} days; loss-aversion framing with concrete metrics.",
    ),
    "winback_eligible": ActionSpec(
        action_type="winback_pitch",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="winback_pitch",
        rationale_template="Merchant subscription lapsed; winback pitch showing cost of inaction.",
    ),
    "dormant_with_vera": ActionSpec(
        action_type="re_engage",
        cta="open_ended",
        send_as="vera",
        template_key="re_engage",
        rationale_template="Merchant has been silent for {days} days; curiosity-led re-engagement.",
    ),
    "gbp_unverified": ActionSpec(
        action_type="verification_nudge",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="verification_nudge",
        rationale_template="GBP unverified; quantified uplift framing to motivate action.",
    ),
    # ── External / contextual
    "festival_upcoming": ActionSpec(
        action_type="festival_promo",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="festival_promo",
        rationale_template="Festival in {days_until} days; category-relevant promo window with effort-externalisation.",
    ),
    "ipl_match_today": ActionSpec(
        action_type="event_promo",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="event_promo",
        rationale_template="IPL match tonight; weeknight match drives +18% restaurant covers.",
    ),
    "category_seasonal": ActionSpec(
        action_type="seasonal_demand",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="seasonal_demand",
        rationale_template="Category-level seasonal demand shift; shelf/stock action recommended.",
    ),
    "supply_alert": ActionSpec(
        action_type="supply_action",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="supply_action",
        rationale_template="Product recall/supply alert; urgency 5, immediate action required.",
    ),
    "competitor_opened": ActionSpec(
        action_type="competitor_alert",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="competitor_alert",
        rationale_template="New competitor nearby; repositioning prompt with factual offer comparison.",
    ),
    "review_theme_emerged": ActionSpec(
        action_type="review_action",
        cta="binary_yes_stop",
        send_as="vera",
        template_key="review_action",
        rationale_template="Negative review theme emerged; actionable fix proposed before it trends.",
    ),
    "milestone_reached": ActionSpec(
        action_type="milestone_celebrate",
        cta="open_ended",
        send_as="vera",
        template_key="milestone_celebrate",
        rationale_template="Merchant near a milestone; celebratory + curiosity framing for momentum.",
    ),
    "active_planning_intent": ActionSpec(
        action_type="planning_assist",
        cta="open_ended",
        send_as="vera",
        template_key="planning_assist",
        rationale_template="Merchant expressed planning intent; delivering concrete next-step to advance conversation.",
    ),
    "curious_ask_due": ActionSpec(
        action_type="curious_ask",
        cta="open_ended",
        send_as="vera",
        template_key="curious_ask",
        rationale_template="Scheduled curiosity-ask cadence; two-way question to build engagement.",
    ),
}

# Category-specific CTA overrides where the default doesn't fit
_CATEGORY_CTA_OVERRIDES: dict[tuple[str, str], str] = {
    ("dentists", "share_research"): "open_ended",
    ("gyms", "alert_seasonal_dip"): "open_ended",
    ("restaurants", "event_promo"): "binary_yes_stop",
}

# Fallback for unknown trigger kinds
_FALLBACK_SPEC = ActionSpec(
    action_type="generic_nudge",
    cta="open_ended",
    send_as="vera",
    template_key="generic_nudge",
    rationale_template="Generic engagement trigger; using best-available category context.",
)


class DecisionEngine:
    """
    Pure rule-based, deterministic engine.
    No randomness. Same inputs → same ActionSpec every time.
    """

    def decide(
        self,
        trigger: dict[str, Any],
        merchant: dict[str, Any],
        category: dict[str, Any],
        customer: dict[str, Any] | None = None,
    ) -> ActionSpec:
        kind = trigger.get("kind", "")
        category_slug = category.get("slug", "")
        spec = _TRIGGER_KIND_DEFAULTS.get(kind, _FALLBACK_SPEC)

        # Apply category-level CTA override if defined
        override_cta = _CATEGORY_CTA_OVERRIDES.get((category_slug, spec.action_type))
        if override_cta:
            spec = ActionSpec(
                action_type=spec.action_type,
                cta=override_cta,
                send_as=spec.send_as,
                template_key=spec.template_key,
                rationale_template=spec.rationale_template,
            )

        # Customer-scoped triggers always go to merchant_on_behalf
        if trigger.get("scope") == "customer" and customer is not None:
            spec = ActionSpec(
                action_type=spec.action_type,
                cta=spec.cta,
                send_as="merchant_on_behalf",
                template_key=spec.template_key,
                rationale_template=spec.rationale_template,
            )

        return spec

    def build_rationale(
        self,
        spec: ActionSpec,
        trigger: dict[str, Any],
        merchant: dict[str, Any],
        category: dict[str, Any],
        customer: dict[str, Any] | None = None,
    ) -> str:
        """Render the rationale template with available facts."""
        payload = trigger.get("payload", {})
        identity = merchant.get("identity", {})
        customer_name = (
            customer.get("identity", {}).get("name", "customer") if customer else "customer"
        )
        sub = merchant.get("subscription", {})

        return spec.rationale_template.format(
            category=category.get("slug", "unknown"),
            metric=payload.get("metric", "key metric"),
            days_remaining=sub.get("days_remaining", "?"),
            days_until=payload.get("days_until", "?"),
            days=payload.get("days_since_last_merchant_message", "?"),
            customer_name=customer_name,
        )


# Module-level singleton
_engine: DecisionEngine | None = None


def get_decision_engine() -> DecisionEngine:
    global _engine
    if _engine is None:
        _engine = DecisionEngine()
    return _engine
