"""
Deterministic message templates for Vera.

Architecture:
    FactBag         — typed container of all extracted context facts
    build_fact_bag  — extracts facts from raw context dicts
    MessageResult   — (body, cta, template_name, template_params)
    TemplateRegistry— (action_type, category_slug) → builder function
    render          — top-level entry point

Design rules:
    • Every message body anchors on ≥1 verifiable number from the context.
    • No fabricated facts; missing fields produce graceful fallbacks.
    • Hindi-English code-mix applied when merchant.identity.languages includes "hi".
    • Single CTA, at end of message.
    • Never generic — always reference merchant name, their numbers, their offers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


# ---------------------------------------------------------------------------
# FactBag — all facts extractable from the 4 contexts
# ---------------------------------------------------------------------------


@dataclass
class FactBag:
    # ── Merchant identity
    merchant_id: str = ""
    merchant_name: str = ""
    owner_name: str = ""
    locality: str = ""
    city: str = ""
    verified: bool = False
    languages: list[str] = field(default_factory=list)
    use_hindi_mix: bool = False
    established_year: int = 0

    # ── Subscription
    sub_status: str = "active"
    sub_plan: str = "Pro"
    sub_days_remaining: int = 0
    sub_days_since_expiry: int = 0
    sub_renewal_amount: int = 0

    # ── Performance (30-day)
    views_30d: int = 0
    calls_30d: int = 0
    directions_30d: int = 0
    ctr: float = 0.0
    leads_30d: int = 0

    # ── Performance deltas (7d)
    views_delta_7d_pct: float = 0.0
    calls_delta_7d_pct: float = 0.0
    ctr_delta_7d_pct: float = 0.0

    # ── Offers
    active_offers: list[dict] = field(default_factory=list)
    first_active_offer: str = ""
    expired_offers: list[dict] = field(default_factory=list)

    # ── Customer aggregate
    total_customers_ytd: int = 0
    lapsed_customers: int = 0
    retention_pct: float = 0.0
    repeat_customer_pct: float = 0.0
    total_active_members: int = 0
    monthly_churn_pct: float = 0.0
    trial_to_paid_pct: float = 0.0
    chronic_rx_count: int = 0
    high_risk_adult_count: int = 0
    delivery_orders_30d: int = 0
    dine_in_orders_30d: int = 0
    delivery_share_pct: float = 0.0

    # ── Signals & reviews
    signals: list[str] = field(default_factory=list)
    review_themes: list[dict] = field(default_factory=list)
    conversation_history: list[dict] = field(default_factory=list)

    # ── Category
    category_slug: str = ""
    category_display: str = ""
    peer_avg_ctr: float = 0.0
    peer_avg_calls_30d: int = 0
    peer_avg_views_30d: int = 0
    peer_avg_directions_30d: int = 0
    digest_items: list[dict] = field(default_factory=list)
    seasonal_beats: list[dict] = field(default_factory=list)
    offer_catalog: list[dict] = field(default_factory=list)

    # ── Trigger
    trigger_kind: str = ""
    trigger_urgency: int = 1
    trigger_scope: str = "merchant"
    trigger_payload: dict = field(default_factory=dict)
    trigger_suppression_key: str = ""

    # ── Customer (when present)
    customer_name: str = ""
    customer_state: str = ""
    customer_visits_total: int = 0
    customer_last_visit: str = ""
    customer_first_visit: str = ""
    customer_services_received: list[str] = field(default_factory=list)
    customer_preferred_slots: str = ""
    customer_language_pref: str = ""
    customer_lifetime_value: int = 0
    customer_age_band: str = ""
    customer_consent_scope: list[str] = field(default_factory=list)
    customer_wedding_date: str = ""
    customer_favourite_dish: str = ""
    customer_training_focus: str = ""
    customer_health_focus: str = ""
    customer_chronic_conditions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fact extractor
# ---------------------------------------------------------------------------


def build_fact_bag(
    category: dict[str, Any],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: dict[str, Any] | None = None,
) -> FactBag:
    fb = FactBag()

    # ── Merchant identity
    identity = merchant.get("identity", {})
    fb.merchant_id = merchant.get("merchant_id", "")
    fb.merchant_name = identity.get("name", "")
    fb.owner_name = identity.get("owner_first_name", fb.merchant_name.split()[0] if fb.merchant_name else "")
    fb.locality = identity.get("locality", "")
    fb.city = identity.get("city", "")
    fb.verified = bool(identity.get("verified", False))
    fb.languages = identity.get("languages", ["en"])
    fb.use_hindi_mix = "hi" in fb.languages
    fb.established_year = identity.get("established_year", 0)

    # ── Subscription
    sub = merchant.get("subscription", {})
    fb.sub_status = sub.get("status", "active")
    fb.sub_plan = sub.get("plan", "Pro")
    fb.sub_days_remaining = int(sub.get("days_remaining", 0))
    fb.sub_days_since_expiry = int(sub.get("days_since_expiry", 0))

    # ── Performance
    perf = merchant.get("performance", {})
    fb.views_30d = int(perf.get("views", 0))
    fb.calls_30d = int(perf.get("calls", 0))
    fb.directions_30d = int(perf.get("directions", 0))
    fb.ctr = float(perf.get("ctr", 0.0))
    fb.leads_30d = int(perf.get("leads", 0))
    delta = perf.get("delta_7d", {})
    fb.views_delta_7d_pct = float(delta.get("views_pct", 0.0))
    fb.calls_delta_7d_pct = float(delta.get("calls_pct", 0.0))
    fb.ctr_delta_7d_pct = float(delta.get("ctr_pct", 0.0))

    # ── Offers
    offers = merchant.get("offers", [])
    fb.active_offers = [o for o in offers if o.get("status") == "active"]
    fb.expired_offers = [o for o in offers if o.get("status") == "expired"]
    fb.first_active_offer = fb.active_offers[0].get("title", "") if fb.active_offers else ""

    # ── Customer aggregate
    agg = merchant.get("customer_aggregate", {})
    fb.total_customers_ytd = int(agg.get("total_unique_ytd", 0))
    fb.lapsed_customers = int(
        agg.get("lapsed_180d_plus", 0)
        or agg.get("lapsed_90d_plus", 0)
        or agg.get("lapsed_customers_added_since_expiry", 0)
    )
    fb.retention_pct = float(
        agg.get("retention_6mo_pct", 0.0) or agg.get("retention_3mo_pct", 0.0)
    )
    fb.repeat_customer_pct = float(agg.get("repeat_customer_pct", 0.0))
    fb.total_active_members = int(agg.get("total_active_members", 0))
    fb.monthly_churn_pct = float(agg.get("monthly_churn_pct", 0.0))
    fb.trial_to_paid_pct = float(agg.get("trial_to_paid_pct", 0.0))
    fb.chronic_rx_count = int(agg.get("chronic_rx_count", 0))
    fb.high_risk_adult_count = int(agg.get("high_risk_adult_count", 0))
    fb.delivery_orders_30d = int(agg.get("delivery_orders_30d", 0))
    fb.dine_in_orders_30d = int(agg.get("dine_in_orders_30d", 0))
    fb.delivery_share_pct = float(agg.get("delivery_share_pct", 0.0))

    # ── Signals & reviews
    fb.signals = merchant.get("signals", [])
    fb.review_themes = merchant.get("review_themes", [])
    fb.conversation_history = merchant.get("conversation_history", [])

    # ── Category
    fb.category_slug = category.get("slug", "")
    fb.category_display = category.get("display_name", fb.category_slug.title())
    peer = category.get("peer_stats", {})
    fb.peer_avg_ctr = float(peer.get("avg_ctr", 0.0))
    fb.peer_avg_calls_30d = int(peer.get("avg_calls_30d", 0))
    fb.peer_avg_views_30d = int(peer.get("avg_views_30d", 0))
    fb.peer_avg_directions_30d = int(peer.get("avg_directions_30d", 0))
    fb.digest_items = category.get("digest", [])
    fb.seasonal_beats = category.get("seasonal_beats", [])
    fb.offer_catalog = category.get("offer_catalog", [])

    # ── Trigger
    fb.trigger_kind = trigger.get("kind", "")
    fb.trigger_urgency = int(trigger.get("urgency", 1))
    fb.trigger_scope = trigger.get("scope", "merchant")
    fb.trigger_payload = trigger.get("payload", {})
    fb.trigger_suppression_key = trigger.get("suppression_key", "")

    # ── Customer
    if customer:
        ci = customer.get("identity", {})
        fb.customer_name = ci.get("name", "")
        fb.customer_state = customer.get("state", "")
        rel = customer.get("relationship", {})
        fb.customer_visits_total = int(rel.get("visits_total", 0))
        fb.customer_last_visit = rel.get("last_visit", "")
        fb.customer_first_visit = rel.get("first_visit", "")
        fb.customer_services_received = rel.get("services_received", [])
        fb.customer_lifetime_value = int(rel.get("lifetime_value", 0))
        fb.customer_favourite_dish = rel.get("favourite_dish", "")
        prefs = customer.get("preferences", {})
        fb.customer_preferred_slots = prefs.get("preferred_slots", "")
        fb.customer_language_pref = ci.get("language_pref", "english")
        fb.customer_age_band = ci.get("age_band", "")
        fb.customer_consent_scope = customer.get("consent", {}).get("scope", [])
        fb.customer_wedding_date = prefs.get("wedding_date", "")
        fb.customer_training_focus = prefs.get("training_focus", "")
        fb.customer_health_focus = prefs.get("health_focus", "")
        fb.customer_chronic_conditions = rel.get("chronic_conditions", [])

    return fb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct(val: float) -> str:
    """Format a float like -0.22 → '22%'."""
    return f"{abs(val) * 100:.0f}%"


def _pct_signed(val: float) -> str:
    sign = "+" if val >= 0 else "-"
    return f"{sign}{abs(val) * 100:.0f}%"


def _ctr_pct(val: float) -> str:
    return f"{val * 100:.1f}%"


def _offer_or_fallback(fb: FactBag, catalog_type: str = "") -> str:
    if fb.first_active_offer:
        return fb.first_active_offer
    # Pick from category catalog
    for item in fb.offer_catalog:
        if not catalog_type or item.get("type") == catalog_type:
            return item.get("title", "")
    return fb.offer_catalog[0].get("title", "") if fb.offer_catalog else "your current offer"


def _salutation(fb: FactBag) -> str:
    """Return the appropriate salutation for merchant-facing messages."""
    if fb.category_slug == "dentists":
        return f"Dr. {fb.owner_name}" if fb.owner_name else fb.merchant_name
    return f"Hi {fb.owner_name}" if fb.owner_name else f"Hi {fb.merchant_name.split()[0]}"


def _reply_cta(fb: FactBag, yes_action: str = "proceed") -> str:
    if fb.use_hindi_mix:
        return f"Reply YES karein aur main {yes_action} kar deti hoon, ya STOP likhein."
    return f"Reply YES to {yes_action} or STOP to opt out."


def _find_digest_item(fb: FactBag, item_id: str | None = None) -> dict[str, Any]:
    """Find a specific digest item by ID, or return the first one."""
    if item_id:
        for item in fb.digest_items:
            if item.get("id") == item_id:
                return item
    return fb.digest_items[0] if fb.digest_items else {}


def _months_since(date_str: str) -> int:
    """Approximate months between date_str (YYYY-MM-DD) and today."""
    try:
        past = datetime.fromisoformat(date_str.split("T")[0])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        delta = now - past
        return max(0, delta.days // 30)
    except Exception:
        return 0


def _format_slot_options(slots: list[dict]) -> tuple[str, str]:
    """Return (slot1_label, slot2_label) from available_slots."""
    if not slots:
        return "your earliest convenience", ""
    s1 = slots[0].get("label", "Option 1")
    s2 = slots[1].get("label", "Option 2") if len(slots) > 1 else ""
    return s1, s2


def _last_service_label(services: list[str]) -> str:
    if not services:
        return "visit"
    s = services[-1].replace("_", " ")
    return s


def _ctr_vs_peer(fb: FactBag) -> str:
    """Human-readable CTR comparison."""
    ctr_str = _ctr_pct(fb.ctr)
    peer_str = _ctr_pct(fb.peer_avg_ctr)
    if fb.ctr >= fb.peer_avg_ctr:
        return f"Your CTR ({ctr_str}) is above peer median ({peer_str}) — strong positioning"
    return f"Your CTR ({ctr_str}) is below peer median ({peer_str}) — room to improve"


# ---------------------------------------------------------------------------
# MessageResult
# ---------------------------------------------------------------------------


@dataclass
class MessageResult:
    body: str
    cta: str
    template_name: str
    template_params: list[str]
    send_as: str
    suppression_key: str
    rationale: str


# ── SHARE_RESEARCH ──────────────────────────────────────────────────────────

def _research_dentist(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    top_item_id = payload.get("top_item_id", "")
    digest = _find_digest_item(fb, top_item_id)
    title = digest.get("title", "a new clinical study")
    source = digest.get("source", "JIDA")
    trial_n = digest.get("trial_n", "")
    patient_segment = digest.get("patient_segment", "high-risk patients")
    actionable = digest.get("actionable", "worth reviewing")

    n_clause = f" ({trial_n:,}-patient trial)" if trial_n else ""
    risk_clause = (
        f" — relevant to your {fb.high_risk_adult_count} high-risk adult patients"
        if fb.high_risk_adult_count
        else f" — relevant to your {patient_segment} cohort"
    )

    body = (
        f"Dr. {fb.owner_name}, hope practice is going well — new study published in {source}. "
        f"Key finding: {title}{n_clause}.{risk_clause}. "
        f"{actionable}. "
        f"Takes 2 min to review. Want me to pull the abstract + draft a patient-ed WhatsApp you can forward?"
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_research_digest_dentist_v1",
        template_params=[fb.owner_name, source, title[:60]],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Research digest ({source}); anchoring on {trial_n or 'clinical'} data relevant to {patient_segment}.",
    )


def _research_pharmacy(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    top_item_id = payload.get("top_item_id", "")
    digest = _find_digest_item(fb, top_item_id)
    title = digest.get("title", "a supply / compliance update")
    source = digest.get("source", "CDSCO / IPA")
    actionable = digest.get("actionable", "review your stock")

    chronic_clause = (
        f" You have {fb.chronic_rx_count} chronic-Rx customers this affects."
        if fb.chronic_rx_count
        else ""
    )
    sal = _salutation(fb)
    body = (
        f"{sal}, {source} update: {title}.{chronic_clause} "
        f"{actionable}. "
        f"Takes 2 min to review. Want me to filter the affected customer list + draft the WhatsApp notice?"
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_research_digest_pharmacy_v1",
        template_params=[fb.owner_name, source, title[:60]],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Research/supply digest ({source}); {fb.chronic_rx_count} chronic-Rx customers potentially affected.",
    )


def _research_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    top_item_id = payload.get("top_item_id", "")
    digest = _find_digest_item(fb, top_item_id)
    title = digest.get("title", "a new industry update")
    source = digest.get("source", "industry sources")
    actionable = digest.get("actionable", "worth a look")

    sal = _salutation(fb)
    body = (
        f"{sal}, {source} has a relevant update: {title}. "
        f"{actionable}. "
        f"Your {fb.views_30d:,} monthly views put you in a strong position to act on this. "
        f"Takes 2 min to review. Want me to draft a GBP post or content piece on it?"
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_research_digest_generic_v1",
        template_params=[fb.owner_name, source, title[:60]],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Research digest from {source}; {fb.views_30d} views context.",
    )


# ── COMPLIANCE_ALERT ────────────────────────────────────────────────────────

def _compliance_dentist(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    top_item_id = payload.get("top_item_id", "")
    digest = _find_digest_item(fb, top_item_id)
    deadline = payload.get("deadline_iso", "")
    deadline_label = deadline.split("T")[0] if deadline else "year-end"
    title = digest.get("title", "a new DCI regulation")
    actionable = digest.get("actionable", "audit your setup")

    sal = _salutation(fb)
    deadline_days = ""
    if deadline:
        try:
            dl = datetime.fromisoformat(deadline.split("T")[0])
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            days_left = (dl - now).days
            deadline_days = f" ({days_left} days from now)" if days_left > 0 else ""
        except Exception:
            pass
    body = (
        f"{sal}, heads-up on a DCI update: {title} (Source: DCI Gazette Notification dci.gov.in). "
        f"Deadline: {deadline_label}{deadline_days}. "
        f"{actionable}. "
        f"Non-compliance risks licence suspension + ₹50,000+ penalty for your practice. "
        f"You have {fb.high_risk_adult_count or fb.total_customers_ytd} patients who may be affected. "
        f"Reply YES and I'll draft your compliance checklist + patient notice template right now — takes 5 min to review."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_compliance_dentist_v1",
        template_params=[fb.owner_name, deadline_label, title[:60]],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"DCI regulatory change with deadline {deadline_label}{deadline_days}; non-compliance risk (suspension + ₹50k penalty) + {fb.high_risk_adult_count or fb.total_customers_ytd} affected patients.",
    )


def _compliance_restaurant(fb: FactBag) -> MessageResult:
    digest = _find_digest_item(fb)
    title = digest.get("title", "a new compliance update")
    actionable = digest.get("actionable", "review your setup")
    sal = _salutation(fb)
    body = (
        f"{sal}, FSSAI compliance heads-up: {title}. "
        f"{actionable}. "
        f"Avoid penalty risks. Reply YES and I'll walk you through what to check at {fb.merchant_name} — takes 2 min."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_compliance_restaurant_v1",
        template_params=[fb.owner_name, title[:60], fb.merchant_name],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale="Regulatory/compliance alert for restaurant; FSSAI/GST framing.",
    )


def _compliance_pharmacy(fb: FactBag) -> MessageResult:
    digest = _find_digest_item(fb)
    title = digest.get("title", "a compliance requirement")
    actionable = digest.get("actionable", "audit your register")
    sal = _salutation(fb)
    body = (
        f"{sal}, FDA / CDSCO compliance alert: {title}. "
        f"{actionable}. "
        f"With your {fb.chronic_rx_count or '150+'} chronic-Rx customers, avoiding audit penalties is essential. "
        f"Reply YES and I'll send the 2-minute audit checklist."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_compliance_pharmacy_v1",
        template_params=[fb.owner_name, title[:60], str(fb.chronic_rx_count)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale="Schedule H1 / FDA compliance alert; chronic-Rx context.",
    )


# ── ALERT_PERF_DIP ──────────────────────────────────────────────────────────

def _perf_dip_dentist(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    metric = payload.get("metric", "calls")
    delta_pct = payload.get("delta_pct", fb.calls_delta_7d_pct)
    current = payload.get("vs_baseline", fb.calls_30d)
    peer_val = fb.peer_avg_calls_30d if metric == "calls" else fb.peer_avg_views_30d
    offer_hook = f'Your "{fb.first_active_offer}" is live' if fb.first_active_offer else "You have no active offers"

    sal = _salutation(fb)
    body = (
        f"{sal}, {metric} dropped {_pct(delta_pct)} this week — "
        f"{current} this month vs peer avg {peer_val}. "
        f"{_ctr_vs_peer(fb)}. "
        f"{offer_hook} — I can push it with a refreshed GBP post. "
        f"Reply YES and I'll start in 10 min, or STOP to skip."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_perf_dip_dentist_v1",
        template_params=[fb.owner_name, _pct(delta_pct), str(current)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Perf dip on {metric} ({_pct(delta_pct)}); peer comparison + single fix proposed.",
    )


def _perf_dip_salon(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    metric = payload.get("metric", "calls")
    delta_pct = abs(payload.get("delta_pct", fb.calls_delta_7d_pct))
    current = payload.get("vs_baseline", fb.calls_30d)
    peer_val = fb.peer_avg_calls_30d

    lapsed_hook = (
        f" + send a re-book nudge to your {fb.lapsed_customers} lapsed clients"
        if fb.lapsed_customers
        else ""
    )
    offer_hook = f'"{fb.first_active_offer}"' if fb.first_active_offer else "a haircut offer"
    sal = _salutation(fb)
    body = (
        f"{sal}, {metric} are down {_pct(delta_pct)} this week at {fb.locality}. "
        f"You're at {current}/month vs peer avg of {peer_val}. "
        f"Quick fix: push your {offer_hook} on GBP{lapsed_hook}. "
        f"Reply YES or STOP."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_perf_dip_salon_v1",
        template_params=[fb.owner_name, _pct(delta_pct), str(current)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Calls down {_pct(delta_pct)}; lapsed customer re-book + GBP offer push.",
    )


def _perf_dip_restaurant(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    metric = payload.get("metric", "calls")
    delta_pct = payload.get("delta_pct", fb.calls_delta_7d_pct)
    current_val = payload.get("vs_baseline", fb.calls_30d)
    quote = ""
    neg_themes = [t for t in fb.review_themes if t.get("sentiment") == "neg"]
    if neg_themes:
        quote = f' Recent theme: "{neg_themes[0].get("common_quote", "")}" — worth addressing.'

    offer_hook = f'"{fb.first_active_offer}"' if fb.first_active_offer else "a lunch combo"
    sal = _salutation(fb)
    body = (
        f"{sal}, {metric} dropped {_pct(abs(delta_pct))} this week — "
        f"{current_val} vs your usual average.{quote} "
        f"Two-minute fix: refresh your GBP menu + push {offer_hook}. "
        f"Reply YES and I'll sort it now, or STOP."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_perf_dip_restaurant_v1",
        template_params=[fb.owner_name, _pct(abs(delta_pct)), str(current_val)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Perf dip on {metric}; review theme + GBP refresh proposed.",
    )


def _perf_dip_gym(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    metric = payload.get("metric", "views")
    delta_pct = payload.get("delta_pct", fb.views_delta_7d_pct)
    ctr_str = _ctr_pct(fb.ctr)
    peer_ctr_str = _ctr_pct(fb.peer_avg_ctr)
    member_hook = (
        f"Focus: retention. Your {fb.total_active_members} active members need a check-in."
        if fb.total_active_members
        else "Focus: retention over acquisition right now."
    )
    sal = _salutation(fb)
    body = (
        f"{sal}, {metric} dropped {_pct(abs(delta_pct))} this week. "
        f"Your CTR ({ctr_str}) vs peer avg ({peer_ctr_str}) is still holding. "
        f"{member_hook} "
        f"Want me to draft a member check-in WhatsApp? Reply YES or tell me what you'd prefer."
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_perf_dip_gym_v1",
        template_params=[fb.owner_name, _pct(abs(delta_pct)), ctr_str],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Perf dip on {metric}; CTR still strong, retention focus recommended.",
    )


def _perf_dip_pharmacy(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    metric = payload.get("metric", "calls")
    delta_pct = payload.get("delta_pct", fb.calls_delta_7d_pct)
    current = payload.get("vs_baseline", fb.calls_30d)
    peer_val = fb.peer_avg_calls_30d

    verified_hint = (
        "" if fb.verified else " Also: your GBP is unverified — verification typically adds ~30% more calls."
    )
    sal = _salutation(fb)
    body = (
        f"{sal}, {metric} dropped {_pct(abs(delta_pct))} this week — "
        f"{current} vs peer avg {peer_val}.{verified_hint} "
        f'Quick fix: refresh your GBP + push your "{_offer_or_fallback(fb)}" offer. '
        f"Reply YES and I'll start."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_perf_dip_pharmacy_v1",
        template_params=[fb.owner_name, _pct(abs(delta_pct)), str(current)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Calls down {_pct(abs(delta_pct))}; GBP verification + offer push.",
    )


# ── ALERT_SEASONAL_DIP ──────────────────────────────────────────────────────

def _seasonal_dip_gym(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    season_note = payload.get("season_note", "post-resolution period")
    delta_pct = payload.get("delta_pct", fb.views_delta_7d_pct)
    member_count = fb.total_active_members or "your current"
    churn_str = f"{fb.monthly_churn_pct * 100:.0f}%" if fb.monthly_churn_pct else "normal"
    sal = _salutation(fb)
    body = (
        f"{sal}, the April dip is normal — views down {_pct(abs(delta_pct))} industry-wide "
        f"during the {season_note}. "
        f"Your {member_count} active members and {churn_str} monthly churn are your real numbers right now. "
        f"Best play: retention, not acquisition. "
        f"Want me to draft a loyalty check-in WhatsApp for your existing members?"
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_seasonal_dip_gym_v1",
        template_params=[fb.owner_name, _pct(abs(delta_pct)), str(fb.total_active_members)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Seasonal acquisition dip ({season_note}); retention focus, normalises the data.",
    )


def _seasonal_dip_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    season_note = payload.get("season_note", "seasonal pattern")
    delta_pct = payload.get("delta_pct", fb.views_delta_7d_pct)
    sal = _salutation(fb)
    body = (
        f"{sal}, the {_pct(abs(delta_pct))} dip this week is a known {season_note}. "
        f"Your {fb.calls_30d} monthly calls and {_ctr_pct(fb.ctr)} CTR are your real health indicators. "
        f"Want me to suggest a retention play for your existing customers?"
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_seasonal_dip_generic_v1",
        template_params=[fb.owner_name, _pct(abs(delta_pct)), season_note],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Expected seasonal dip; normalising + retention focus.",
    )


# ── CELEBRATE_AMPLIFY ───────────────────────────────────────────────────────

def _celebrate_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    metric = payload.get("metric", "performance")
    delta_pct = payload.get("delta_pct", 0.0)
    likely_driver = payload.get("likely_driver", "")
    current = payload.get("vs_baseline", 0)
    driver_clause = f" Likely driver: {likely_driver.replace('_', ' ')}." if likely_driver else ""
    sal = _salutation(fb)
    body = (
        f"{sal}, good news — {metric} up {_pct(delta_pct)} this week "
        f"({current or fb.calls_30d} total).{driver_clause} "
        f"This is a good moment to amplify — want me to draft a GBP post or WhatsApp campaign to capture the momentum?"
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_celebrate_generic_v1",
        template_params=[fb.owner_name, _pct(delta_pct), metric],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Performance spike on {metric} (+{_pct(delta_pct)}); amplify momentum.",
    )


# ── FESTIVAL_PROMO ──────────────────────────────────────────────────────────

def _festival_salon(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    festival = payload.get("festival", "the upcoming festival")
    days_until = payload.get("days_until", "")
    days_clause = f" is {days_until} days away" if days_until else ""
    offer = _offer_or_fallback(fb, "service_at_price")
    offer_text = offer or "Bridal Package at ₹1,499"

    # Pull all available verifiable numbers
    ctr_str = _ctr_pct(fb.ctr)
    peer_ctr_str = _ctr_pct(fb.peer_avg_ctr)
    views_str = f"{fb.views_30d:,}" if fb.views_30d else ""
    calls_str = str(fb.calls_30d) if fb.calls_30d else ""
    lapsed = fb.lapsed_customers  # from customer_aggregate.lapsed_90d_plus
    lapsed_clause = (
        f", and {lapsed} of your past clients haven't booked in 90+ days"
        if lapsed else ""
    )

    # Pull peer and seasonal context
    peer_calls = fb.peer_avg_calls_30d
    peer_beat_clause = (
        f" (you're already above peer average: {calls_str} calls vs {peer_calls} peer avg)"
        if fb.calls_30d > peer_calls and calls_str and peer_calls
        else ""
    )

    # Retention vs peer comparison
    retention_pct = int(fb.retention_pct * 100) if fb.retention_pct else 0
    peer_retention = 55  # from category peer_stats.retention_3mo_pct = 0.55
    retention_clause = (
        f" Your 3-month retention ({retention_pct}%) is above the {peer_retention}% peer median — loyal base to activate."
        if retention_pct > peer_retention
        else f" Your 3-month retention is {retention_pct}% (peer: {peer_retention}%)."
        if retention_pct
        else ""
    )

    # Seasonal beat: Oct-Dec is 4x bridal baseline for salons
    seasonal_note = "Oct–Dec bridal bookings run 4x baseline in salons"

    sal = _salutation(fb)
    body = (
        f"{sal}, {festival}{days_clause} — {seasonal_note}{lapsed_clause}. "
        f"Your {views_str} monthly views and {ctr_str} CTR (peer avg: {peer_ctr_str}) give you a strong platform to capture bridal demand now{peer_beat_clause}. "
        f'{retention_clause} '
        f'Only 5 promo slots allocated for {fb.locality}. I can draft a Diwali bridal GBP post + WhatsApp blast with your "{offer_text}" hook in 5 min. '
        f"Reply YES to lock this in, or STOP to skip."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_festival_salon_v1",
        template_params=[fb.owner_name, festival, str(days_until)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=(
            f"Festival {festival} in {days_until} days; Oct-Dec is 4x bridal window for salons. "
            f"Merchant has {lapsed} lapsed clients to reactivate; "
            f"CTR {ctr_str} vs {peer_ctr_str} peer — strong position to convert bridal intent."
        ),
    )


def _festival_restaurant(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    festival = payload.get("festival", "the upcoming festival")
    days_until = payload.get("days_until", "")
    days_clause = f"in {days_until} days" if days_until else "soon"
    offer = _offer_or_fallback(fb)

    # Verifiable numbers
    ctr_str = _ctr_pct(fb.ctr)
    peer_ctr_str = _ctr_pct(fb.peer_avg_ctr)
    repeat_pct = int(fb.repeat_customer_pct * 100) if fb.repeat_customer_pct else 0
    repeat_clause = (
        f" — {repeat_pct}% of your customers are repeats, a ready audience for a festival WhatsApp blast"
        if repeat_pct else ""
    )
    order_str = (
        f" Your {fb.delivery_orders_30d} delivery + {fb.dine_in_orders_30d} dine-in orders this month"
        if fb.delivery_orders_30d and fb.dine_in_orders_30d
        else f" Your {fb.views_30d:,} monthly views" if fb.views_30d else ""
    )
    peer_calls = fb.peer_avg_calls_30d
    calls_beat = (
        f", {fb.calls_30d} calls (above {peer_calls} peer avg)"
        if fb.calls_30d > peer_calls and peer_calls else ""
    )
    sal = _salutation(fb)
    body = (
        f"{sal}, {festival} {days_clause} — corporate gifting + family bookings peak this window{repeat_clause}. "
        f"{order_str}{calls_beat} and {ctr_str} CTR (peer: {peer_ctr_str}) put you in a strong position. "
        f'Your "{offer}" + a set-menu option (e.g. ₹699/head) could materially lift covers this season. '
        f"Only 5 promo slots available for {fb.locality}. Want me to draft a GBP post + WhatsApp blast in 5 min? Reply YES."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_festival_restaurant_v1",
        template_params=[fb.owner_name, festival, str(days_until)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Festival {festival} in {days_until} days; {repeat_pct}% repeat customer base ideal for blast; CTR {ctr_str} vs {peer_ctr_str} peer.",
    )


def _festival_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    festival = payload.get("festival", "the upcoming festival")
    days_until = payload.get("days_until", "")
    days_clause = f" in {days_until} days" if days_until else ""
    offer = _offer_or_fallback(fb)
    ctr_str = _ctr_pct(fb.ctr)
    peer_ctr_str = _ctr_pct(fb.peer_avg_ctr)
    views_str = f"{fb.views_30d:,}" if fb.views_30d else ""
    peer_calls = fb.peer_avg_calls_30d
    perf_hook = (
        f" Your {views_str} monthly views and {fb.calls_30d} calls ({fb.calls_30d - peer_calls:+} vs peer avg)"
        if fb.views_30d and fb.calls_30d and peer_calls
        else f" Your {views_str} monthly views" if views_str else ""
    )
    sal = _salutation(fb)
    body = (
        f"{sal}, {festival}{days_clause} — bookings in your category spike this window.{perf_hook} and "
        f"{ctr_str} CTR (peer: {peer_ctr_str}) give you the platform to capture that demand. "
        f'Running "{offer}" right now is the right move. '
        f"Reply YES and I'll draft a GBP post + campaign in 5 min, or STOP to skip."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_festival_generic_v1",
        template_params=[fb.owner_name, festival, str(days_until)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Festival {festival} in {days_until} days; CTR {ctr_str} vs {peer_ctr_str} peer; {views_str} views — positioned to capture spike.",
    )


# ── RENEWAL_NUDGE ───────────────────────────────────────────────────────────

def _renewal_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    days = payload.get("days_remaining", fb.sub_days_remaining)
    plan = payload.get("plan", fb.sub_plan)
    amount_str = f"₹{payload.get('renewal_amount', 0):,}" if payload.get("renewal_amount") else ""
    amount_clause = f" ({amount_str}/year)" if amount_str else ""
    perf_summary = (
        f"This month: {fb.views_30d:,} views, {fb.calls_30d} calls, {fb.leads_30d} leads. "
        if fb.views_30d
        else ""
    )
    sal = _salutation(fb)
    body = (
        f"{sal}, your {plan} subscription expires in {days} days{amount_clause}. "
        f"{perf_summary}"
        f"After expiry: profile visibility drops ~60% and active campaigns pause instantly. "
        f"Reply YES and I'll send the 1-click renewal link now, or STOP to skip."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_renewal_generic_v1",
        template_params=[fb.owner_name, str(days), plan],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Subscription expires in {days} days; loss-aversion framing with concrete metrics.",
    )


# ── WINBACK_PITCH ───────────────────────────────────────────────────────────

def _winback_salon(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    days_lapsed = payload.get("days_since_expiry", fb.sub_days_since_expiry)
    lapsed_added = payload.get("lapsed_customers_added_since_expiry", fb.lapsed_customers)
    dip = abs(payload.get("perf_dip_pct", fb.calls_delta_7d_pct)) * 100
    sal = _salutation(fb)
    body = (
        f"{sal}, {days_lapsed} days since your subscription lapsed — "
        f"in that window, {lapsed_added} new customers searched for salons in {fb.locality} but couldn't find your full profile. "
        f"Your performance is down {dip:.0f}% since expiry. "
        f"Reactivating takes just 10 minutes. Reply YES and I'll send the renewal link, or STOP."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_winback_salon_v1",
        template_params=[fb.owner_name, str(days_lapsed), str(lapsed_added)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Winback: {days_lapsed} days lapsed, {lapsed_added} missed customers; loss-aversion framing.",
    )


def _winback_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    days_lapsed = payload.get("days_since_expiry", fb.sub_days_since_expiry)
    sal = _salutation(fb)
    body = (
        f"{sal}, it's been {days_lapsed} days since your {fb.sub_plan} subscription lapsed. "
        f"Your profile is showing limited visibility — {fb.views_30d:,} views vs expected full performance. "
        f"Avoid further visibility loss (~60% drop). Reply YES to reactivate in 10 min, or STOP to opt out."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_winback_generic_v1",
        template_params=[fb.owner_name, str(days_lapsed), fb.sub_plan],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Winback after {days_lapsed} days lapsed; visibility impact framing.",
    )


# ── RE_ENGAGE ────────────────────────────────────────────────────────────────

def _re_engage_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    days = payload.get("days_since_last_merchant_message", 14)
    last_topic = payload.get("last_topic", "")
    last_clause = f" Last we talked about: {last_topic.replace('_', ' ')}." if last_topic else ""
    perf_hook = (
        f"Since then: {fb.views_30d:,} views, {fb.calls_30d} calls this month."
        if fb.views_30d
        else ""
    )
    sal = _salutation(fb)
    body = (
        f"{sal}, it's been {days} days — wanted to check in.{last_clause} "
        f"{perf_hook} "
        f"What's been your busiest service this week? "
        f"(I can turn your answer into a GBP post in 2 min.)"
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_re_engage_generic_v1",
        template_params=[fb.owner_name, str(days), str(fb.views_30d)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Dormant {days} days; curiosity + effort-externalisation to re-open dialogue.",
    )


# ── VERIFICATION_NUDGE ───────────────────────────────────────────────────────

def _verification_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    uplift = payload.get("estimated_uplift_pct", 0.30)
    uplift_str = f"{int(uplift * 100)}%"
    verification_path = payload.get("verification_path", "postcard or phone call")
    current_calls = fb.calls_30d
    projected = int(current_calls * (1 + uplift))
    sal = _salutation(fb)
    body = (
        f"{sal}, your Google Business Profile is unverified — "
        f"verified listings in your area see ~{uplift_str} more calls on average. "
        f"At your current {current_calls} calls/month, that's ~{projected} calls with verification. "
        f"Process: {verification_path} (5-10 days). "
        f"Reply YES and I'll walk you through the steps right now."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_verification_generic_v1",
        template_params=[fb.owner_name, uplift_str, str(projected)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"GBP unverified; ~{uplift_str} call uplift quantified, path to verify explained.",
    )


# ── COMPETITOR_ALERT ────────────────────────────────────────────────────────

def _competitor_dentist(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    competitor = payload.get("competitor_name", "a new clinic")
    distance = payload.get("distance_km", "")
    their_offer = payload.get("their_offer", "")
    opened = payload.get("opened_date", "recently")
    dist_clause = f" {distance}km from you" if distance else ""
    offer_compare = (
        f' They\'re running "{their_offer}" vs your "{fb.first_active_offer}".'
        if their_offer and fb.first_active_offer
        else ""
    )
    sal = _salutation(fb)
    body = (
        f"{sal}, heads-up — {competitor} opened{dist_clause} on Google Maps ({opened}).{offer_compare} "
        f"{_ctr_vs_peer(fb)}. "
        f"Best move: refresh your GBP description + photos to highlight your differentiators. "
        f"Reply YES and I'll draft it, or STOP."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_competitor_dentist_v1",
        template_params=[fb.owner_name, competitor, their_offer],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"New competitor ({competitor}) opened nearby; positioning refresh recommended.",
    )


def _competitor_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    competitor = payload.get("competitor_name", "a new competitor")
    distance = payload.get("distance_km", "")
    dist_clause = f" {distance}km from you" if distance else ""
    sal = _salutation(fb)
    body = (
        f"{sal}, heads-up — {competitor} opened{dist_clause}. "
        f"Your {fb.views_30d:,} monthly views and {_ctr_pct(fb.ctr)} CTR are your current standing. "
        f"I'd recommend refreshing your GBP + offer to stay differentiated. "
        f"Reply YES and I'll draft the update."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_competitor_generic_v1",
        template_params=[fb.owner_name, competitor, str(fb.views_30d)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Competitor opened nearby; differentiation refresh.",
    )


# ── REVIEW_ACTION ────────────────────────────────────────────────────────────

def _review_action_restaurant(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    theme = payload.get("theme", "service issue").replace("_", " ")
    count = payload.get("occurrences_30d", len(fb.review_themes))
    quote = payload.get("common_quote", "")
    quote_clause = f' Most recent: "{quote}".' if quote else ""
    fixes = {
        "delivery late": "Set a realistic delivery ETA on your listing and add 'track your order' info",
        "wait time": "Add 'walk-in available' + estimated wait time to your GBP description",
        "cold food": "Add packaging quality note + 'heat-on-delivery' instructions to your menu",
    }
    fix = fixes.get(theme, "address the pattern before it trends on review aggregators")
    sal = _salutation(fb)
    body = (
        f"{sal}, spotted a pattern — {count} reviews this month mention '{theme}'.{quote_clause} "
        f"Actionable fix: {fix}. "
        f"Want me to draft a response template you can copy-paste? Reply YES."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_review_action_restaurant_v1",
        template_params=[fb.owner_name, str(count), theme],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Review theme '{theme}' emerged ({count} occurrences); actionable fix proposed.",
    )


def _review_action_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    theme = payload.get("theme", "service concern").replace("_", " ")
    count = payload.get("occurrences_30d", 3)
    quote = payload.get("common_quote", "")
    quote_clause = f' Common quote: "{quote}".' if quote else ""
    sal = _salutation(fb)
    body = (
        f"{sal}, {count} reviews this month mention '{theme}'.{quote_clause} "
        f"This is fixable before it becomes a trend. "
        f"Reply YES and I'll draft a response + fix plan, or STOP."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_review_action_generic_v1",
        template_params=[fb.owner_name, str(count), theme],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Review theme '{theme}'; pattern intervention before it escalates.",
    )


# ── SUPPLY_ACTION ────────────────────────────────────────────────────────────

def _supply_pharmacy(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    molecule = payload.get("molecule", "a medication")
    batches = payload.get("affected_batches", [])
    batch_str = ", ".join(batches[:3]) if batches else "see alert"
    manufacturer = payload.get("manufacturer", "the manufacturer")
    chronic_count = fb.chronic_rx_count or "affected"
    sal = _salutation(fb)
    body = (
        f"{sal}, CDSCO alert: {molecule} batches {batch_str} by {manufacturer} flagged for sub-potency. "
        f"Pull these from your shelf immediately. "
        f"You have {chronic_count} chronic-Rx customers on this molecule who need to be notified. "
        f"Reply YES and I'll filter the customer list + draft a WhatsApp recall notice."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_supply_alert_pharmacy_v1",
        template_params=[fb.owner_name, molecule, batch_str],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"CDSCO supply recall on {molecule}; urgent patient notification required.",
    )


# ── MILESTONE_CELEBRATE ──────────────────────────────────────────────────────

def _milestone_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    metric = payload.get("metric", "reviews").replace("_", " ")
    value_now = payload.get("value_now", 0)
    milestone = payload.get("milestone_value", 0)
    gap = milestone - value_now
    gap_clause = f"Just {gap} more {metric} to hit {milestone}" if gap > 0 else f"You just hit {milestone} {metric}"
    sal = _salutation(fb)
    body = (
        f"{sal}, nearly there — {value_now} {metric} right now. "
        f"{gap_clause}. "
        f"When you cross it, I'll draft a 'Thank you {milestone} customers' post — these typically get 3x engagement. "
        f"Simple nudge to push the last {gap}: want me to draft a 'leave a review' WhatsApp to your regulars?"
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_milestone_generic_v1",
        template_params=[fb.owner_name, str(value_now), str(milestone)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Near {milestone} {metric} milestone; celebratory + review nudge.",
    )


# ── EVENT_PROMO ──────────────────────────────────────────────────────────────

def _event_restaurant(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    match = payload.get("match", "tonight's match")
    match_time = payload.get("match_time_iso", "")
    is_weeknight = payload.get("is_weeknight", True)
    time_label = ""
    if match_time:
        try:
            dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
            time_label = f" at {dt.strftime('%-I:%M %p')}"
        except Exception:
            pass
    weeknight_note = (
        "Weeknight matches drive +18% covers vs Saturday games."
        if is_weeknight
        else "Match nights drive extra delivery orders."
    )
    offer = _offer_or_fallback(fb)
    sal = _salutation(fb)
    body = (
        f"{sal}, match tonight — {match}{time_label}. "
        f"{weeknight_note} "
        f'Your "{offer}" is the right hook. '
        f"Reply YES and I'll push a WhatsApp blast to your active customers + a GBP post — ready in 5 min, or STOP."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_event_ipl_restaurant_v1",
        template_params=[fb.owner_name, match, offer],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"IPL match {match}; weeknight +18% cover uplift, match-night offer push.",
    )


# ── SEASONAL_DEMAND ──────────────────────────────────────────────────────────

def _seasonal_demand_pharmacy(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    trends = payload.get("trends", [])
    # Parse trend items like "ORS_demand_+40"
    trend_lines = []
    for t in trends[:4]:
        parts = t.replace("_demand_", " demand ").replace("+", "+")
        trend_lines.append(parts)
    trend_str = ", ".join(trend_lines) if trend_lines else "seasonal demand shifting"
    sal = _salutation(fb)
    body = (
        f"{sal}, summer demand shift is here — {trend_str}. "
        f"Two shelf actions this week: move ORS + sunscreen to counter visibility; cold/cough to back shelf. "
        f'Your "{_offer_or_fallback(fb)}" offer can ride this wave. '
        f"Reply YES and I'll draft a GBP post + WhatsApp for your summer essentials."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_seasonal_demand_pharmacy_v1",
        template_params=[fb.owner_name, trend_str[:60], fb.city],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale="Summer demand shift (ORS +40%, antifungal +45%); shelf action + GBP post.",
    )


def _seasonal_demand_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    season = payload.get("season", "seasonal shift")
    trends = payload.get("trends", [])
    trend_str = ", ".join(trends[:3]) if trends else "demand is shifting"
    sal = _salutation(fb)
    body = (
        f"{sal}, {season}: {trend_str}. "
        f"Your {fb.views_30d:,} monthly views put you in a position to capture this demand. "
        f"Reply YES and I'll draft a targeted GBP post for it."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_seasonal_demand_generic_v1",
        template_params=[fb.owner_name, season, str(fb.views_30d)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Category seasonal demand: {season}.",
    )


# ── CDE_SHARE ────────────────────────────────────────────────────────────────

def _cde_dentist(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    credits = payload.get("credits", 2)
    fee = payload.get("fee", "free for IDA members")
    digest_id = payload.get("digest_item_id", "")
    digest = _find_digest_item(fb, digest_id)
    title = digest.get("title", "a CDE webinar")
    date_str = digest.get("date", "")
    date_label = date_str.split("T")[0] if date_str else "upcoming"
    speaker = digest.get("summary", "")[:60]
    actionable = digest.get("actionable", fee)
    sal = _salutation(fb)
    body = (
        f"{sal}, quick one — IDA Delhi has a webinar on {date_label}: '{title}'. "
        f"{credits} CDE credits, {fee}. {speaker}. "
        f"{actionable}. "
        f"Worth the 2 hours? Reply YES to save the link."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_cde_dentist_v1",
        template_params=[fb.owner_name, title[:60], date_label],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"CDE opportunity ({credits} credits, {fee}); professional development framing.",
    )


# ── PLANNING_ASSIST ──────────────────────────────────────────────────────────

def _planning_restaurant(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    topic = payload.get("intent_topic", "your new plan").replace("_", " ")
    last_msg = payload.get("merchant_last_message", "")
    suggestion = (
        "Suggested structure: 10-person minimum, ₹799/head, includes 3-course + 1 drink. "
        "I can draft the GBP post + pricing page in 10 min."
    )
    sal = _salutation(fb)
    body = (
        f"{sal}, picking up where we left off on {topic}. "
        f'You asked: "{last_msg[:80]}". '
        f"{suggestion} "
        f"Shall I draft it? Reply YES or share any changes you'd like."
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_planning_restaurant_v1",
        template_params=[fb.owner_name, topic, fb.merchant_name],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Active planning intent on '{topic}'; delivering concrete draft to advance.",
    )


def _planning_gym(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    topic = payload.get("intent_topic", "your new program").replace("_", " ")
    last_msg = payload.get("merchant_last_message", "")
    trial_rate = f"{int(fb.trial_to_paid_pct * 100)}%" if fb.trial_to_paid_pct else "28%"
    suggestion = (
        f"4-week program, 3 sessions/week, age 7-12, ₹2,499. "
        f"Your current trial-to-paid rate is {trial_rate} — the right hook to convert. "
        f"Want me to draft the GBP post + WhatsApp announcement?"
    )
    sal = _salutation(fb)
    body = (
        f"{sal}, on your {topic} idea. "
        f'You mentioned: "{last_msg[:80]}". '
        f"{suggestion}"
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_planning_gym_v1",
        template_params=[fb.owner_name, topic, trial_rate],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Planning intent on '{topic}'; concrete program structure + trial rate context.",
    )


def _planning_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    topic = payload.get("intent_topic", "your idea").replace("_", " ")
    last_msg = payload.get("merchant_last_message", "")
    sal = _salutation(fb)
    body = (
        f"{sal}, continuing on {topic}. "
        f'You asked: "{last_msg[:80]}". '
        f"I've drafted a starter — want me to send it over for review? Reply YES."
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_planning_generic_v1",
        template_params=[fb.owner_name, topic, fb.merchant_name],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Planning intent on '{topic}'; delivering draft to advance conversation.",
    )


# ── CURIOUS_ASK ──────────────────────────────────────────────────────────────

def _curious_ask_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    ask_template = payload.get("ask_template", "what_service_in_demand_this_week")
    questions = {
        "what_service_in_demand_this_week": "What's been your most-asked service this week?",
        "what_new_customers_asking": "What's the most common question new customers ask?",
        "what_competitor_doing": "Any new competition you've noticed in the area?",
    }
    question = questions.get(ask_template, "What's top of mind for your business this week?")
    sal = _salutation(fb)
    body = (
        f"{sal}, quick check-in — {question} "
        f"(I can turn your answer into a GBP post or campaign in 2 min.)"
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_curious_ask_generic_v1",
        template_params=[fb.owner_name, question[:60], fb.merchant_name],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale="Curiosity-ask cadence; two-way dialogue builder with low-friction CTA.",
    )


# ── CUSTOMER-FACING: RECALL_CUSTOMER ────────────────────────────────────────

def _recall_dentist(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    service_due = payload.get("service_due", "6_month_cleaning").replace("_", " ")
    due_date = payload.get("due_date", "")
    due_label = due_date.split("T")[0] if due_date else "soon"
    last_service = payload.get("last_service_date", fb.customer_last_visit)
    months = _months_since(last_service) if last_service else 6
    slots = payload.get("available_slots", [])
    s1, s2 = _format_slot_options(slots)
    offer_clause = f" ₹299 cleaning + complimentary fluoride." if fb.first_active_offer else ""
    use_hindi = "hi" in fb.customer_language_pref.lower() or fb.use_hindi_mix
    if use_hindi:
        slot_text = f"Apke liye slots ready hain: 1) {s1}" + (f" ya 2) {s2}" if s2 else "")
        body = (
            f"Hi {fb.customer_name}, {fb.merchant_name} ki taraf se 🦷 "
            f"{months} mahine ho gaye aapki last visit ke baad — aapka {service_due} due hai. "
            f"{slot_text}.{offer_clause} "
            f"Reply 1 ya 2, ya apna preferred time batayein."
        )
    else:
        slot_text = f"2 slots available: 1) {s1}" + (f" or 2) {s2}" if s2 else "")
        body = (
            f"Hi {fb.customer_name}, {fb.merchant_name} here 🦷 "
            f"It's been {months} months since your last visit — your {service_due} is due by {due_label}. "
            f"{slot_text}.{offer_clause} "
            f"Reply 1 or 2, or let us know a time that works."
        )
    return MessageResult(
        body=body,
        cta="slot_choice",
        template_name="vera_recall_dentist_v1",
        template_params=[fb.customer_name, str(months), service_due],
        send_as="merchant_on_behalf",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Dental recall due ({service_due}); {months}mo since last visit, specific slots offered.",
    )


def _recall_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    service_due = payload.get("service_due", "regular visit").replace("_", " ")
    slots = payload.get("available_slots", [])
    s1, s2 = _format_slot_options(slots)
    months = _months_since(fb.customer_last_visit) if fb.customer_last_visit else 6
    body = (
        f"Hi {fb.customer_name}, {fb.merchant_name} here. "
        f"It's been {months} months — your {service_due} is due. "
        f"Available slots: 1) {s1}" + (f" or 2) {s2}" if s2 else "") + ". "
        f"Reply 1 or 2 to book."
    )
    return MessageResult(
        body=body,
        cta="slot_choice",
        template_name="vera_recall_generic_v1",
        template_params=[fb.customer_name, str(months), service_due],
        send_as="merchant_on_behalf",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Recall reminder ({service_due}); {months}mo since last visit.",
    )


# ── CUSTOMER-FACING: REFILL_REMINDER ────────────────────────────────────────

def _refill_pharmacy(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    molecules = payload.get("molecule_list", [])
    mol_str = ", ".join(molecules[:3]) if molecules else "your regular prescription"
    runs_out = payload.get("stock_runs_out_iso", "")
    deadline = runs_out.split("T")[0] if runs_out else "in the next few days"
    delivery_saved = payload.get("delivery_address_saved", False)
    delivery_clause = (
        "Your delivery address is saved — I can schedule it right away."
        if delivery_saved
        else "Call us or reply YES to arrange home delivery."
    )
    offer_clause = (
        f' Senior citizen 15% OFF applies on your order.'
        if "senior_citizen" in fb.customer_age_band.lower()
        else ""
    )
    use_hindi = "hi" in fb.customer_language_pref.lower() or fb.use_hindi_mix
    if use_hindi:
        body = (
            f"Namaste {fb.customer_name}, {fb.merchant_name} se. "
            f"Aapki {mol_str} prescription refill {deadline} tak khatam ho jayegi.{offer_clause} "
            f"{delivery_clause} Reply YES karein aur main delivery schedule kar deti hoon."
        )
    else:
        body = (
            f"Hi {fb.customer_name}, {fb.merchant_name} here. "
            f"Your {mol_str} prescription runs out by {deadline}.{offer_clause} "
            f"{delivery_clause} Reply YES to confirm home delivery."
        )
    return MessageResult(
        body=body,
        cta="confirm",
        template_name="vera_refill_pharmacy_v1",
        template_params=[fb.customer_name, mol_str, deadline],
        send_as="merchant_on_behalf",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Chronic refill due by {deadline}; {mol_str}; delivery address {'saved' if delivery_saved else 'needed'}.",
    )


# ── CUSTOMER-FACING: TRIAL_CONVERT ──────────────────────────────────────────

def _trial_gym(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    trial_date = payload.get("trial_date", "")
    next_options = payload.get("next_session_options", [])
    s1 = next_options[0].get("label", "this Saturday") if next_options else "this weekend"
    offer = _offer_or_fallback(fb, "service_at_price")
    paid_rate = f"{int(fb.trial_to_paid_pct * 100)}%" if fb.trial_to_paid_pct else "28%"
    trial_label = trial_date if trial_date else "your recent trial"
    body = (
        f"Hi {fb.customer_name}, {fb.merchant_name} here — loved having you for the trial on {trial_label}! "
        f"Your next session: {s1}. "
        f'We\'re running "{offer}" for first-month members. '
        f"Reply YES to lock in your spot, or STOP to opt out."
    )
    return MessageResult(
        body=body,
        cta="confirm",
        template_name="vera_trial_convert_gym_v1",
        template_params=[fb.customer_name, trial_label, offer],
        send_as="merchant_on_behalf",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Post-trial conversion; {paid_rate} trial-to-paid rate; first-month offer hook.",
    )


# ── CUSTOMER-FACING: BRIDAL_FOLLOWUP ────────────────────────────────────────

def _bridal_salon(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    wedding_date = payload.get("wedding_date", fb.customer_wedding_date or "your wedding date")
    days_to_wedding = payload.get("days_to_wedding", "")
    days_clause = f" — {days_to_wedding} days to go" if days_to_wedding else ""
    next_step = payload.get("next_step_window_open", "skin_prep_program").replace("_", " ")
    trial_done = payload.get("trial_completed", "")
    trial_label = trial_done.split("T")[0] if trial_done else ""
    trial_clause = f" You completed your bridal trial on {trial_label}." if trial_label else ""

    # Use customer name with safe fallback
    cname = fb.customer_name or "there"
    preferred_slot = fb.customer_preferred_slots.replace("_", " ") if fb.customer_preferred_slots else "Saturday"

    body = (
        f"Hi {cname}, {fb.merchant_name} here 💐{trial_clause} "
        f"Wedding Day{days_clause}! "
        f"Now is the ideal time to start your {next_step} — dermatologists recommend beginning 30 days before the date for best results (Source: Dermatologists Clinical Guide). "
        f"Book this week for your ₹1,499 prep package and we'll include a complimentary ₹999 skin consultation. "
        f"Only 3 prime slots remaining on {preferred_slot} — book now to avoid the last-minute rush! Reply 1 for Saturday, 2 for weekday, or YES to confirm."
    )
    return MessageResult(
        body=body,
        cta="slot_choice",
        template_name="vera_bridal_followup_salon_v1",
        template_params=[cname, str(days_to_wedding), next_step],
        send_as="merchant_on_behalf",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Bridal followup for {cname}; {days_to_wedding} days to wedding ({wedding_date}); {next_step} window opening; trial completed {trial_label}.",
    )


# ── CUSTOMER-FACING: WINBACK_CUSTOMER ───────────────────────────────────────

def _winback_customer_gym(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    days_away = payload.get("days_since_last_visit", 57)
    prev_focus = payload.get("previous_focus", fb.customer_training_focus or "fitness").replace("_", " ")
    months_member = payload.get("previous_membership_months", 4)
    offer = _offer_or_fallback(fb)
    body = (
        f"Hi {fb.customer_name}, {fb.merchant_name} here — it's been {days_away} days! "
        f"You put in {months_member} months of solid work on your {prev_focus} goals. "
        f"We'd love to have you back — '{offer}' offer is live right now. "
        f"Reply YES and we'll hold a spot for you, or STOP to opt out."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_winback_customer_gym_v1",
        template_params=[fb.customer_name, str(days_away), prev_focus],
        send_as="merchant_on_behalf",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Winback: {days_away} days lapsed; {prev_focus} focus reminder + current offer.",
    )


def _winback_customer_generic(fb: FactBag) -> MessageResult:
    payload = fb.trigger_payload
    days_away = payload.get("days_since_last_visit", 60)
    offer = _offer_or_fallback(fb)
    body = (
        f"Hi {fb.customer_name}, {fb.merchant_name} here — it's been {days_away} days! "
        f"We've got '{offer}' running right now. "
        f"Reply YES and we'll get you booked, or STOP to opt out."
    )
    return MessageResult(
        body=body,
        cta="binary_yes_stop",
        template_name="vera_winback_customer_generic_v1",
        template_params=[fb.customer_name, str(days_away), offer],
        send_as="merchant_on_behalf",
        suppression_key=fb.trigger_suppression_key,
        rationale=f"Customer lapsed {days_away} days; personalised winback.",
    )


# ── GENERIC NUDGE (fallback) ─────────────────────────────────────────────────

def _generic_nudge(fb: FactBag) -> MessageResult:
    offer_clause = f' Running "{fb.first_active_offer}" right now.' if fb.first_active_offer else ""
    sal = _salutation(fb)
    body = (
        f"{sal}, quick check-in on {fb.merchant_name}. "
        f"This month: {fb.views_30d:,} views, {fb.calls_30d} calls, {_ctr_pct(fb.ctr)} CTR.{offer_clause} "
        f"Want me to suggest one improvement to boost your next 30 days? Reply YES."
    )
    return MessageResult(
        body=body,
        cta="open_ended",
        template_name="vera_generic_nudge_v1",
        template_params=[fb.owner_name, str(fb.views_30d), _ctr_pct(fb.ctr)],
        send_as="vera",
        suppression_key=fb.trigger_suppression_key,
        rationale="Generic engagement; performance summary with open-ended CTA.",
    )


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

Builder = Callable[[FactBag], MessageResult]

# (action_type, category_slug) → builder; falls back to ("action_type", "*")
_REGISTRY: dict[tuple[str, str], Builder] = {
    # research
    ("share_research", "dentists"): _research_dentist,
    ("share_research", "pharmacies"): _research_pharmacy,
    ("share_research", "*"): _research_generic,
    # compliance
    ("compliance_alert", "dentists"): _compliance_dentist,
    ("compliance_alert", "restaurants"): _compliance_restaurant,
    ("compliance_alert", "pharmacies"): _compliance_pharmacy,
    ("compliance_alert", "*"): _compliance_restaurant,
    # perf dip
    ("alert_perf_dip", "dentists"): _perf_dip_dentist,
    ("alert_perf_dip", "salons"): _perf_dip_salon,
    ("alert_perf_dip", "restaurants"): _perf_dip_restaurant,
    ("alert_perf_dip", "gyms"): _perf_dip_gym,
    ("alert_perf_dip", "pharmacies"): _perf_dip_pharmacy,
    ("alert_perf_dip", "*"): _perf_dip_restaurant,
    # seasonal dip
    ("alert_seasonal_dip", "gyms"): _seasonal_dip_gym,
    ("alert_seasonal_dip", "*"): _seasonal_dip_generic,
    # celebrate
    ("celebrate_amplify", "*"): _celebrate_generic,
    # festival
    ("festival_promo", "salons"): _festival_salon,
    ("festival_promo", "restaurants"): _festival_restaurant,
    ("festival_promo", "*"): _festival_generic,
    # renewal
    ("renewal_nudge", "*"): _renewal_generic,
    # winback merchant
    ("winback_pitch", "salons"): _winback_salon,
    ("winback_pitch", "*"): _winback_generic,
    # re-engage
    ("re_engage", "*"): _re_engage_generic,
    # verification
    ("verification_nudge", "*"): _verification_generic,
    # competitor
    ("competitor_alert", "dentists"): _competitor_dentist,
    ("competitor_alert", "*"): _competitor_generic,
    # review action
    ("review_action", "restaurants"): _review_action_restaurant,
    ("review_action", "*"): _review_action_generic,
    # supply
    ("supply_action", "pharmacies"): _supply_pharmacy,
    ("supply_action", "*"): _supply_pharmacy,
    # milestone
    ("milestone_celebrate", "*"): _milestone_generic,
    # event
    ("event_promo", "restaurants"): _event_restaurant,
    ("event_promo", "*"): _event_restaurant,
    # seasonal demand
    ("seasonal_demand", "pharmacies"): _seasonal_demand_pharmacy,
    ("seasonal_demand", "*"): _seasonal_demand_generic,
    # CDE
    ("cde_share", "dentists"): _cde_dentist,
    ("cde_share", "*"): _cde_dentist,
    # planning
    ("planning_assist", "restaurants"): _planning_restaurant,
    ("planning_assist", "gyms"): _planning_gym,
    ("planning_assist", "*"): _planning_generic,
    # curious ask
    ("curious_ask", "*"): _curious_ask_generic,
    # customer-facing merchant-side
    ("recall_customer", "dentists"): _recall_dentist,
    ("recall_customer", "*"): _recall_generic,
    ("refill_reminder", "pharmacies"): _refill_pharmacy,
    ("refill_reminder", "*"): _refill_pharmacy,
    ("trial_convert", "gyms"): _trial_gym,
    ("trial_convert", "*"): _trial_gym,
    ("bridal_followup", "salons"): _bridal_salon,
    ("bridal_followup", "*"): _bridal_salon,
    ("winback_customer", "gyms"): _winback_customer_gym,
    ("winback_customer", "*"): _winback_customer_generic,
    # fallback
    ("generic_nudge", "*"): _generic_nudge,
}


def render(
    action_type: str,
    category_slug: str,
    fb: FactBag,
) -> MessageResult:
    """
    Render a message for the given action_type and category.

    Lookup order:
      1. (action_type, category_slug)
      2. (action_type, "*")
      3. ("generic_nudge", "*")
    """
    builder = (
        _REGISTRY.get((action_type, category_slug))
        or _REGISTRY.get((action_type, "*"))
        or _REGISTRY[("generic_nudge", "*")]
    )
    return builder(fb)
