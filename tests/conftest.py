"""Shared pytest fixtures for Vera tests."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.store.memory import get_store
from app.engine.suppression import get_suppression_registry
from app.engine.conversation import get_conversation_manager


# ---------------------------------------------------------------------------
# Canonical test data (from seed JSON, representative)
# ---------------------------------------------------------------------------


@pytest.fixture
def category_dentist() -> dict:
    return {
        "slug": "dentists",
        "display_name": "Dentists",
        "voice": {
            "tone": "peer_clinical",
            "register": "respectful_collegial",
            "vocab_allowed": ["fluoride varnish", "scaling", "caries"],
            "vocab_taboo": ["guaranteed", "miracle"],
            "salutation_examples": ["Dr. {first_name}"],
        },
        "offer_catalog": [
            {"id": "den_001", "title": "Dental Cleaning @ ₹299", "value": "299", "audience": "new_user", "type": "service_at_price"},
            {"id": "den_002", "title": "Free Consultation", "value": "0", "audience": "new_user", "type": "free_service"},
        ],
        "peer_stats": {
            "avg_rating": 4.4, "avg_review_count": 62,
            "avg_views_30d": 1820, "avg_calls_30d": 12,
            "avg_directions_30d": 38, "avg_ctr": 0.030,
        },
        "digest": [
            {
                "id": "d_2026W17_jida_fluoride",
                "kind": "research",
                "title": "3-month fluoride varnish recall outperforms 6-month for high-risk adult caries",
                "source": "JIDA Oct 2026, p.14",
                "trial_n": 2100,
                "patient_segment": "high_risk_adults",
                "summary": "Multi-center Indian trial shows 38% lower caries recurrence.",
                "actionable": "Reassess recall interval for adults flagged high-risk in your charting",
            }
        ],
        "seasonal_beats": [{"month_range": "Nov-Feb", "note": "exam-stress bruxism spike"}],
        "trend_signals": [{"query": "clear aligners delhi", "delta_yoy": 0.62}],
    }


@pytest.fixture
def category_restaurant() -> dict:
    return {
        "slug": "restaurants",
        "display_name": "Restaurants & Cafes",
        "voice": {"tone": "warm_busy_practical", "register": "fellow_operator", "vocab_taboo": ["guaranteed packed house"]},
        "offer_catalog": [
            {"id": "res_001", "title": "Flat 30% OFF on total bill", "value": "30%", "audience": "new_user", "type": "percentage_discount"},
            {"id": "res_002", "title": "Buy 1 Pizza Get 1 Free (Tue-Thu)", "value": "BOGO", "audience": "new_user", "type": "bogo"},
        ],
        "peer_stats": {
            "avg_rating": 4.2, "avg_review_count": 142,
            "avg_views_30d": 4800, "avg_calls_30d": 38,
            "avg_ctr": 0.025,
        },
        "digest": [{"id": "d_ipl", "kind": "seasonal", "title": "IPL weeknight matches drive +18% covers", "source": "magicpin data Apr 2026", "summary": "...", "actionable": "Push match-night combos on Tue/Wed/Thu"}],
        "seasonal_beats": [{"month_range": "Mar-Apr", "note": "IPL season — match-night promos"}],
        "trend_signals": [],
    }


@pytest.fixture
def category_gym() -> dict:
    return {
        "slug": "gyms",
        "display_name": "Gyms & Fitness",
        "voice": {"tone": "energetic_disciplined", "register": "coach_to_member", "vocab_taboo": ["guaranteed weight loss"]},
        "offer_catalog": [
            {"id": "gym_001", "title": "3 FREE Trial Classes", "value": "0", "audience": "new_user", "type": "free_trial"},
            {"id": "gym_002", "title": "First Month @ ₹499", "value": "499", "audience": "new_user", "type": "service_at_price"},
        ],
        "peer_stats": {
            "avg_rating": 4.5, "avg_views_30d": 1100,
            "avg_calls_30d": 18, "avg_ctr": 0.045,
            "monthly_churn_pct": 0.08, "trial_to_paid_pct": 0.32,
        },
        "digest": [],
        "seasonal_beats": [{"month_range": "Apr-Jun", "note": "lowest acquisition window"}],
        "trend_signals": [],
    }


@pytest.fixture
def category_pharmacy() -> dict:
    return {
        "slug": "pharmacies",
        "display_name": "Pharmacies & Medical Stores",
        "voice": {"tone": "trustworthy_precise", "register": "neighbourhood_pharmacist", "vocab_taboo": ["miracle cure"]},
        "offer_catalog": [
            {"id": "phr_001", "title": "Flat 20% OFF on medicines", "value": "20%", "audience": "new_user", "type": "percentage_discount"},
            {"id": "phr_002", "title": "Free Home Delivery > ₹499", "value": "free_delivery", "audience": "new_user", "type": "free_addon"},
        ],
        "peer_stats": {
            "avg_rating": 4.6, "avg_views_30d": 1400,
            "avg_calls_30d": 22, "avg_ctr": 0.038,
            "repeat_customer_pct": 0.62,
        },
        "digest": [
            {
                "id": "d_2026W17_atorvastatin_recall",
                "kind": "alert",
                "title": "Voluntary recall: Specific atorvastatin batches",
                "source": "CDSCO alert Apr 2026",
                "summary": "Batches flagged for sub-potency.",
                "actionable": "Pull the batches; WhatsApp affected customers",
            }
        ],
        "seasonal_beats": [],
        "trend_signals": [],
    }


@pytest.fixture
def merchant_meera(category_dentist) -> dict:
    return {
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "category_slug": "dentists",
        "identity": {
            "name": "Dr. Meera's Dental Clinic",
            "city": "Delhi",
            "locality": "Lajpat Nagar",
            "verified": True,
            "languages": ["en", "hi"],
            "owner_first_name": "Meera",
            "established_year": 2018,
        },
        "subscription": {"status": "active", "plan": "Pro", "days_remaining": 82},
        "performance": {
            "window_days": 30,
            "views": 2410, "calls": 18, "directions": 45, "ctr": 0.021, "leads": 9,
            "delta_7d": {"views_pct": 0.18, "calls_pct": -0.05, "ctr_pct": 0.02},
        },
        "offers": [
            {"id": "o_meera_001", "title": "Dental Cleaning @ ₹299", "status": "active", "started": "2026-03-01"},
            {"id": "o_meera_002", "title": "Deep Cleaning @ ₹499", "status": "expired", "ended": "2026-02-28"},
        ],
        "customer_aggregate": {
            "total_unique_ytd": 540, "lapsed_180d_plus": 78,
            "retention_6mo_pct": 0.38, "high_risk_adult_count": 124,
        },
        "signals": ["stale_posts:22d", "ctr_below_peer_median", "high_risk_adult_cohort"],
        "review_themes": [
            {"theme": "doctor_manner", "sentiment": "pos", "occurrences_30d": 5},
        ],
        "conversation_history": [],
    }


@pytest.fixture
def merchant_pizza(category_restaurant) -> dict:
    return {
        "merchant_id": "m_005_pizzajunction_restaurant_delhi",
        "category_slug": "restaurants",
        "identity": {
            "name": "SK Pizza Junction",
            "city": "Delhi",
            "locality": "Sant Nagar",
            "verified": False,
            "languages": ["en", "hi"],
            "owner_first_name": "Suresh",
        },
        "subscription": {"status": "trial", "plan": "Trial", "days_remaining": 7},
        "performance": {
            "window_days": 30,
            "views": 2200, "calls": 12, "directions": 38, "ctr": 0.020, "leads": 4,
            "delta_7d": {"views_pct": 0.08, "calls_pct": 0.10},
        },
        "offers": [{"id": "o_skpz_001", "title": "Buy 1 Pizza Get 1 Free (Tue-Thu)", "status": "active", "started": "2026-04-15"}],
        "customer_aggregate": {"total_unique_ytd": 0, "delivery_orders_30d": 180, "dine_in_orders_30d": 95},
        "signals": ["new_merchant", "trial_ending_soon"],
        "review_themes": [
            {"theme": "delivery_late", "sentiment": "neg", "occurrences_30d": 4, "common_quote": "took 50 mins"},
        ],
        "conversation_history": [],
    }


@pytest.fixture
def merchant_powerhouse(category_gym) -> dict:
    return {
        "merchant_id": "m_007_powerhouse_gym_bangalore",
        "category_slug": "gyms",
        "identity": {
            "name": "PowerHouse Fitness",
            "city": "Bangalore",
            "locality": "HSR Layout",
            "verified": True,
            "languages": ["en"],
            "owner_first_name": "Karthik",
        },
        "subscription": {"status": "active", "plan": "Pro", "days_remaining": 95},
        "performance": {
            "window_days": 30,
            "views": 1480, "calls": 22, "directions": 48, "ctr": 0.052, "leads": 14,
            "delta_7d": {"views_pct": -0.30, "calls_pct": -0.35},
        },
        "offers": [{"id": "o_powerhouse_001", "title": "3 FREE Trial Classes", "status": "active"}],
        "customer_aggregate": {"total_active_members": 245, "monthly_churn_pct": 0.10, "trial_to_paid_pct": 0.28},
        "signals": ["seasonal_dip_apr_may"],
        "review_themes": [],
        "conversation_history": [],
    }


@pytest.fixture
def merchant_apollo(category_pharmacy) -> dict:
    return {
        "merchant_id": "m_009_apollo_pharmacy_jaipur",
        "category_slug": "pharmacies",
        "identity": {
            "name": "Apollo Health Plus Pharmacy",
            "city": "Jaipur",
            "locality": "Malviya Nagar",
            "verified": True,
            "languages": ["en", "hi"],
            "owner_first_name": "Ramesh",
        },
        "subscription": {"status": "active", "plan": "Pro", "days_remaining": 60},
        "performance": {
            "window_days": 30,
            "views": 1850, "calls": 38, "directions": 95, "ctr": 0.045, "leads": 24,
            "delta_7d": {"views_pct": 0.06, "calls_pct": 0.08},
        },
        "offers": [
            {"id": "o_apollo_001", "title": "Free Home Delivery > ₹499", "status": "active"},
            {"id": "o_apollo_002", "title": "Senior Citizen 15% OFF", "status": "active"},
        ],
        "customer_aggregate": {"total_unique_ytd": 1820, "repeat_customer_pct": 0.68, "chronic_rx_count": 240},
        "signals": ["above_peer_calls", "compliance_aware"],
        "review_themes": [],
        "conversation_history": [],
    }


@pytest.fixture
def trigger_research_dentist() -> dict:
    return {
        "id": "trg_001_research_digest_dentists",
        "_trigger_id": "trg_001_research_digest_dentists",
        "scope": "merchant",
        "kind": "research_digest",
        "source": "external",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "customer_id": None,
        "payload": {"category": "dentists", "top_item_id": "d_2026W17_jida_fluoride"},
        "urgency": 2,
        "suppression_key": "research:dentists:2026-W17",
        "expires_at": "2030-05-03T00:00:00Z",
    }


@pytest.fixture
def trigger_perf_dip_bharat() -> dict:
    return {
        "id": "trg_004_perf_dip_bharat",
        "_trigger_id": "trg_004_perf_dip_bharat",
        "scope": "merchant",
        "kind": "perf_dip",
        "source": "internal",
        "merchant_id": "m_002_bharat_dentist_mumbai",
        "customer_id": None,
        "payload": {"metric": "calls", "delta_pct": -0.50, "window": "7d", "vs_baseline": 12},
        "urgency": 4,
        "suppression_key": "perf_dip:m_002:calls:2026-W17",
        "expires_at": "2030-05-10T00:00:00Z",
    }


@pytest.fixture
def trigger_ipl_pizza() -> dict:
    return {
        "id": "trg_010_ipl_match_delhi",
        "_trigger_id": "trg_010_ipl_match_delhi",
        "scope": "merchant",
        "kind": "ipl_match_today",
        "source": "external",
        "merchant_id": "m_005_pizzajunction_restaurant_delhi",
        "customer_id": None,
        "payload": {
            "match": "DC vs MI", "venue": "Arun Jaitley Stadium",
            "city": "Delhi", "match_time_iso": "2026-04-26T19:30:00+05:30",
            "is_weeknight": False,
        },
        "urgency": 3,
        "suppression_key": "ipl:m_005:2026-04-26",
        "expires_at": "2030-04-26T23:59:59+05:30",
    }


@pytest.fixture
def trigger_seasonal_gym() -> dict:
    return {
        "id": "trg_014_seasonal_dip_powerhouse",
        "_trigger_id": "trg_014_seasonal_dip_powerhouse",
        "scope": "merchant",
        "kind": "seasonal_perf_dip",
        "source": "internal",
        "merchant_id": "m_007_powerhouse_gym_bangalore",
        "customer_id": None,
        "payload": {
            "metric": "views", "delta_pct": -0.30,
            "window": "7d", "is_expected_seasonal": True,
            "season_note": "post_resolution_window_apr_jun",
        },
        "urgency": 1,
        "suppression_key": "seasonal_dip:m_007:2026-Q2",
        "expires_at": "2030-06-30T00:00:00Z",
    }


@pytest.fixture
def trigger_supply_apollo() -> dict:
    return {
        "id": "trg_018_supply_atorvastatin_recall",
        "_trigger_id": "trg_018_supply_atorvastatin_recall",
        "scope": "merchant",
        "kind": "supply_alert",
        "source": "external",
        "merchant_id": "m_009_apollo_pharmacy_jaipur",
        "customer_id": None,
        "payload": {
            "alert_id": "d_2026W17_atorvastatin_recall",
            "molecule": "atorvastatin",
            "affected_batches": ["AT2024-1102", "AT2024-1108"],
            "manufacturer": "MfrZ",
        },
        "urgency": 5,
        "suppression_key": "alert:atorvastatin:2026-04",
        "expires_at": "2030-05-30T00:00:00Z",
    }


@pytest.fixture
def customer_priya() -> dict:
    return {
        "customer_id": "c_001_priya_for_m001",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "identity": {"name": "Priya", "phone_redacted": "<phone>", "language_pref": "hi-en mix", "age_band": "25-35"},
        "relationship": {
            "first_visit": "2025-11-04", "last_visit": "2026-05-12",
            "visits_total": 4,
            "services_received": ["cleaning", "cleaning", "whitening", "cleaning"],
            "lifetime_value": 1696,
        },
        "state": "lapsed_soft",
        "preferences": {"preferred_slots": "weekday_evening", "channel": "whatsapp", "reminder_opt_in": True},
        "consent": {"opted_in_at": "2025-11-04", "scope": ["recall_reminders", "appointment_reminders"]},
    }


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for API tests."""
    # Reset singletons between tests
    get_store().clear()
    get_suppression_registry().clear()
    get_conversation_manager().clear()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    get_store().clear()
    get_suppression_registry().clear()
    get_conversation_manager().clear()
