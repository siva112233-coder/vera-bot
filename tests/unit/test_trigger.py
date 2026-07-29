"""Unit tests for TriggerPrioritizer."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from app.store.memory import ContextStore
from app.engine.suppression import SuppressionRegistry
from app.engine.trigger import TriggerPrioritizer


def _now():
    return datetime.now(timezone.utc)


def _future(days=365):
    return (_now() + timedelta(days=days)).isoformat()


def _past(days=1):
    return (_now() - timedelta(days=days)).isoformat()


@pytest.fixture
def store():
    return ContextStore()


@pytest.fixture
def suppression():
    return SuppressionRegistry()


@pytest.fixture
def prioritizer(store, suppression):
    return TriggerPrioritizer(store, suppression)


def _push_trigger(store, trigger_id, merchant_id, kind, urgency, suppression_key, expires_at=None):
    store.put("trigger", trigger_id, 1, {
        "id": trigger_id,
        "kind": kind,
        "scope": "merchant",
        "merchant_id": merchant_id,
        "customer_id": None,
        "urgency": urgency,
        "suppression_key": suppression_key,
        "expires_at": expires_at or _future(),
        "payload": {},
    })


def test_selects_available_triggers(store, suppression, prioritizer):
    _push_trigger(store, "t_001", "m_001", "perf_dip", 4, "key_001")
    selected = prioritizer.select(["t_001"])
    assert len(selected) == 1
    assert selected[0]["_trigger_id"] == "t_001"


def test_skips_missing_trigger(store, suppression, prioritizer):
    selected = prioritizer.select(["nonexistent_trigger"])
    assert selected == []


def test_skips_expired_trigger(store, suppression, prioritizer):
    _push_trigger(store, "t_expired", "m_001", "perf_dip", 4, "key_001", expires_at=_past())
    selected = prioritizer.select(["t_expired"])
    assert selected == []


def test_skips_suppressed_trigger(store, suppression, prioritizer):
    _push_trigger(store, "t_sup", "m_001", "perf_dip", 4, "dup_key")
    suppression.mark_sent("dup_key", "conv_001")
    selected = prioritizer.select(["t_sup"])
    assert selected == []


def test_sorts_by_urgency_desc(store, suppression, prioritizer):
    _push_trigger(store, "t_low", "m_001", "research_digest", 2, "k_low")
    _push_trigger(store, "t_high", "m_002", "supply_alert", 5, "k_high")
    _push_trigger(store, "t_med", "m_003", "perf_dip", 4, "k_med")
    selected = prioritizer.select(["t_low", "t_high", "t_med"])
    urgencies = [t.get("urgency") for t in selected]
    assert urgencies == sorted(urgencies, reverse=True)


def test_deterministic_tiebreak_by_id(store, suppression, prioritizer):
    _push_trigger(store, "t_zzz", "m_001", "perf_dip", 4, "k_zzz")
    _push_trigger(store, "t_aaa", "m_002", "perf_dip", 4, "k_aaa")
    selected = prioritizer.select(["t_zzz", "t_aaa"])
    ids = [t["_trigger_id"] for t in selected]
    assert ids == sorted(ids)  # asc sort wins


def test_one_trigger_per_merchant(store, suppression, prioritizer):
    _push_trigger(store, "t_u4", "m_001", "perf_dip", 4, "k_u4")
    _push_trigger(store, "t_u2", "m_001", "research_digest", 2, "k_u2")
    selected = prioritizer.select(["t_u4", "t_u2"])
    assert len(selected) == 1
    assert selected[0]["urgency"] == 4  # highest wins


def test_no_expiry_field_never_expires(store, suppression, prioritizer):
    store.put("trigger", "t_noexp", 1, {
        "id": "t_noexp", "kind": "perf_dip", "scope": "merchant",
        "merchant_id": "m_001", "customer_id": None,
        "urgency": 3, "suppression_key": "k_noexp",
        "payload": {},
        # No expires_at field
    })
    selected = prioritizer.select(["t_noexp"])
    assert len(selected) == 1
