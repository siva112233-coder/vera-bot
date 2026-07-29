"""Unit tests for the compose() function and message templates."""
from __future__ import annotations

import pytest

from app.engine.composer import compose


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _quick_category(slug: str) -> dict:
    return {
        "slug": slug,
        "display_name": slug.title(),
        "voice": {"tone": "test", "vocab_taboo": []},
        "offer_catalog": [{"id": "o1", "title": f"{slug.title()} Offer @ ₹299", "status": "active", "type": "service_at_price"}],
        "peer_stats": {"avg_ctr": 0.030, "avg_calls_30d": 12, "avg_views_30d": 1800},
        "digest": [
            {
                "id": "d_001",
                "title": "Test digest title",
                "source": "Test Journal",
                "trial_n": 1000,
                "patient_segment": "high_risk_adults",
                "actionable": "Review recall interval",
            }
        ],
        "seasonal_beats": [],
    }


def _quick_merchant(category_slug: str, merchant_id: str = "m_001") -> dict:
    return {
        "merchant_id": merchant_id,
        "category_slug": category_slug,
        "identity": {
            "name": "Test Clinic",
            "owner_first_name": "Ravi",
            "locality": "Test Nagar",
            "city": "Delhi",
            "verified": True,
            "languages": ["en"],
        },
        "subscription": {"status": "active", "plan": "Pro", "days_remaining": 60},
        "performance": {"views": 2000, "calls": 18, "directions": 40, "ctr": 0.028, "leads": 8, "delta_7d": {}},
        "offers": [{"id": "o1", "title": "Test Offer @ ₹299", "status": "active"}],
        "customer_aggregate": {
            "total_unique_ytd": 400, "lapsed_180d_plus": 50,
            "high_risk_adult_count": 100, "chronic_rx_count": 200,
            "total_active_members": 150, "monthly_churn_pct": 0.10,
            "trial_to_paid_pct": 0.28,
        },
        "signals": [],
        "review_themes": [],
        "conversation_history": [],
    }


def _quick_trigger(kind: str, merchant_id: str = "m_001", scope: str = "merchant", payload: dict | None = None) -> dict:
    return {
        "id": f"t_{kind}",
        "_trigger_id": f"t_{kind}",
        "scope": scope,
        "kind": kind,
        "source": "internal",
        "merchant_id": merchant_id,
        "customer_id": None,
        "urgency": 3,
        "suppression_key": f"sup:{kind}:2026-W17",
        "expires_at": "2030-01-01T00:00:00Z",
        "payload": payload or {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_compose_returns_required_keys():
    result = compose(
        _quick_category("dentists"),
        _quick_merchant("dentists"),
        _quick_trigger("research_digest"),
    )
    for key in ("message", "cta", "send_as", "suppression_key", "rationale"):
        assert key in result, f"Missing key: {key}"


def test_compose_message_is_non_empty_string():
    result = compose(
        _quick_category("restaurants"),
        _quick_merchant("restaurants"),
        _quick_trigger("perf_dip", payload={"metric": "calls", "delta_pct": -0.25}),
    )
    assert isinstance(result["message"], str)
    assert len(result["message"]) > 30


def test_compose_is_deterministic():
    """Same input → same output every single time."""
    cat = _quick_category("gyms")
    mer = _quick_merchant("gyms")
    trg = _quick_trigger("seasonal_perf_dip", payload={"delta_pct": -0.30, "season_note": "apr_jun"})
    results = [compose(cat, mer, trg) for _ in range(5)]
    messages = [r["message"] for r in results]
    assert len(set(messages)) == 1, "compose() is not deterministic!"


def test_compose_research_dentist_contains_merchant_name(category_dentist, merchant_meera, trigger_research_dentist):
    result = compose(category_dentist, merchant_meera, trigger_research_dentist)
    assert "Meera" in result["message"]


def test_compose_research_dentist_contains_journal_source(category_dentist, merchant_meera, trigger_research_dentist):
    result = compose(category_dentist, merchant_meera, trigger_research_dentist)
    assert "JIDA" in result["message"]


def test_compose_perf_dip_restaurant_contains_metric(category_restaurant, merchant_pizza, trigger_ipl_pizza):
    trg = _quick_trigger("perf_dip", merchant_id="m_005_pizzajunction_restaurant_delhi", payload={"metric": "calls", "delta_pct": -0.30})
    result = compose(category_restaurant, merchant_pizza, trg)
    assert "call" in result["message"].lower() or "%" in result["message"]


def test_compose_ipl_event_restaurant(category_restaurant, merchant_pizza, trigger_ipl_pizza):
    result = compose(category_restaurant, merchant_pizza, trigger_ipl_pizza)
    assert "match" in result["message"].lower() or "ipl" in result["message"].lower() or "DC vs MI" in result["message"]
    assert result["cta"] == "binary_yes_stop"
    assert result["send_as"] == "vera"


def test_compose_supply_alert_pharmacy(category_pharmacy, merchant_apollo, trigger_supply_apollo):
    result = compose(category_pharmacy, merchant_apollo, trigger_supply_apollo)
    assert "atorvastatin" in result["message"].lower()
    assert result["send_as"] == "vera"


def test_compose_seasonal_dip_gym(category_gym, merchant_powerhouse, trigger_seasonal_gym):
    result = compose(category_gym, merchant_powerhouse, trigger_seasonal_gym)
    assert "member" in result["message"].lower() or "245" in result["message"]
    assert result["cta"] == "open_ended"


def test_compose_recall_customer_is_merchant_on_behalf(category_dentist, merchant_meera, customer_priya):
    trg = _quick_trigger("recall_due", merchant_id="m_001_drmeera_dentist_delhi", scope="customer", payload={"service_due": "6_month_cleaning", "available_slots": [{"label": "Mon 10 AM"}, {"label": "Wed 6 PM"}]})
    trg["customer_id"] = "c_001_priya_for_m001"
    result = compose(category_dentist, merchant_meera, trg, customer_priya)
    assert result["send_as"] == "merchant_on_behalf"
    assert "Priya" in result["message"]
    assert result["cta"] == "slot_choice"


def test_compose_renewal_nudge_shows_days(category_dentist, merchant_meera):
    trg = _quick_trigger("renewal_due", payload={"days_remaining": 7, "plan": "Pro"})
    result = compose(category_dentist, merchant_meera, trg)
    assert "7" in result["message"]
    assert result["cta"] == "binary_yes_stop"


def test_compose_suppression_key_propagated(category_dentist, merchant_meera, trigger_research_dentist):
    result = compose(category_dentist, merchant_meera, trigger_research_dentist)
    assert result["suppression_key"] == trigger_research_dentist["suppression_key"]


def test_compose_with_no_customer_ok(category_restaurant, merchant_pizza):
    trg = _quick_trigger("festival_upcoming", payload={"festival": "Diwali", "days_until": 10})
    result = compose(category_restaurant, merchant_pizza, trg, customer=None)
    assert "Diwali" in result["message"]


def test_compose_unknown_trigger_kind_returns_generic(category_dentist, merchant_meera):
    trg = _quick_trigger("completely_new_unknown_kind_xyz")
    result = compose(category_dentist, merchant_meera, trg)
    assert result["message"]
    assert result["cta"]


def test_compose_all_5_categories_without_error():
    for slug in ("dentists", "restaurants", "salons", "gyms", "pharmacies"):
        cat = _quick_category(slug)
        mer = _quick_merchant(slug)
        trg = _quick_trigger("perf_dip", payload={"metric": "calls", "delta_pct": -0.20})
        result = compose(cat, mer, trg)
        assert result["message"], f"Empty message for category {slug}"


def test_compose_hindi_mix_merchant():
    cat = _quick_category("dentists")
    mer = _quick_merchant("dentists")
    mer["identity"]["languages"] = ["en", "hi"]
    trg = _quick_trigger("renewal_due", payload={"days_remaining": 5, "plan": "Pro"})
    result = compose(cat, mer, trg)
    # Should still produce a message (no crash with hindi flag)
    assert result["message"]
