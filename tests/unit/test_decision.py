"""Unit tests for DecisionEngine."""
from __future__ import annotations

import pytest

from app.engine.decision import DecisionEngine


@pytest.fixture
def engine():
    return DecisionEngine()


def _make_trigger(kind: str, scope: str = "merchant") -> dict:
    return {"kind": kind, "scope": scope, "payload": {}, "urgency": 2, "merchant_id": "m_001"}


def _make_merchant(langs=("en",)) -> dict:
    return {
        "identity": {"owner_first_name": "Test", "languages": list(langs)},
        "performance": {}, "offers": [], "subscription": {},
        "customer_aggregate": {},
    }


def _make_category(slug: str = "dentists") -> dict:
    return {"slug": slug, "peer_stats": {}, "digest": []}


@pytest.mark.parametrize("kind,expected_action,expected_send_as", [
    ("research_digest", "share_research", "vera"),
    ("perf_dip", "alert_perf_dip", "vera"),
    ("seasonal_perf_dip", "alert_seasonal_dip", "vera"),
    ("perf_spike", "celebrate_amplify", "vera"),
    ("festival_upcoming", "festival_promo", "vera"),
    ("renewal_due", "renewal_nudge", "vera"),
    ("winback_eligible", "winback_pitch", "vera"),
    ("dormant_with_vera", "re_engage", "vera"),
    ("gbp_unverified", "verification_nudge", "vera"),
    ("competitor_opened", "competitor_alert", "vera"),
    ("review_theme_emerged", "review_action", "vera"),
    ("supply_alert", "supply_action", "vera"),
    ("milestone_reached", "milestone_celebrate", "vera"),
    ("ipl_match_today", "event_promo", "vera"),
    ("category_seasonal", "seasonal_demand", "vera"),
    ("cde_opportunity", "cde_share", "vera"),
    ("active_planning_intent", "planning_assist", "vera"),
    ("curious_ask_due", "curious_ask", "vera"),
    ("regulation_change", "compliance_alert", "vera"),
    ("recall_due", "recall_customer", "merchant_on_behalf"),
    ("chronic_refill_due", "refill_reminder", "merchant_on_behalf"),
    ("trial_followup", "trial_convert", "merchant_on_behalf"),
    ("wedding_package_followup", "bridal_followup", "merchant_on_behalf"),
    ("customer_lapsed_hard", "winback_customer", "merchant_on_behalf"),
])
def test_known_trigger_kinds(engine, kind, expected_action, expected_send_as):
    trigger = _make_trigger(kind, scope="customer" if expected_send_as == "merchant_on_behalf" else "merchant")
    customer = {"identity": {"name": "Test Customer"}} if expected_send_as == "merchant_on_behalf" else None
    spec = engine.decide(trigger, _make_merchant(), _make_category(), customer)
    assert spec.action_type == expected_action
    assert spec.send_as == expected_send_as


def test_unknown_trigger_kind_returns_generic_nudge(engine):
    trigger = _make_trigger("nonexistent_trigger_xyz")
    spec = engine.decide(trigger, _make_merchant(), _make_category())
    assert spec.action_type == "generic_nudge"


def test_same_inputs_always_produce_same_output(engine):
    trigger = _make_trigger("perf_dip")
    merchant = _make_merchant()
    category = _make_category()
    spec1 = engine.decide(trigger, merchant, category)
    spec2 = engine.decide(trigger, merchant, category)
    assert spec1 == spec2


def test_customer_scope_forces_merchant_on_behalf(engine):
    trigger = _make_trigger("perf_dip", scope="customer")
    customer = {"identity": {"name": "Ravi"}}
    spec = engine.decide(trigger, _make_merchant(), _make_category(), customer)
    assert spec.send_as == "merchant_on_behalf"


def test_build_rationale_returns_string(engine):
    trigger = _make_trigger("perf_dip")
    trigger["payload"] = {"metric": "calls"}
    spec = engine.decide(trigger, _make_merchant(), _make_category())
    rationale = engine.build_rationale(spec, trigger, _make_merchant(), _make_category())
    assert isinstance(rationale, str)
    assert len(rationale) > 10
