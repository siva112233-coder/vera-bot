"""Unit tests for the context store."""
from __future__ import annotations

import pytest

from app.store.memory import ContextStore


@pytest.fixture
def store():
    s = ContextStore()
    return s


def test_put_and_get_roundtrip(store):
    ok, reason, _ = store.put("merchant", "m_001", 1, {"name": "Clinic A"})
    assert ok is True
    assert reason is None
    assert store.get("merchant", "m_001") == {"name": "Clinic A"}


def test_stale_version_rejected(store):
    store.put("merchant", "m_001", 5, {"v": 5})
    ok, reason, current = store.put("merchant", "m_001", 3, {"v": 3})
    assert ok is False
    assert reason == "stale_version"
    assert current == 5
    # Original payload preserved
    assert store.get("merchant", "m_001")["v"] == 5


def test_same_version_idempotent(store):
    store.put("merchant", "m_001", 2, {"v": 2})
    ok, reason, current = store.put("merchant", "m_001", 2, {"v": 99})
    assert ok is False
    assert current == 2


def test_higher_version_overwrites(store):
    store.put("merchant", "m_001", 1, {"v": 1})
    ok, _, _ = store.put("merchant", "m_001", 2, {"v": 2})
    assert ok is True
    assert store.get("merchant", "m_001")["v"] == 2


def test_counts_by_scope(store):
    store.put("merchant", "m_001", 1, {})
    store.put("merchant", "m_002", 1, {})
    store.put("category", "dentists", 1, {})
    store.put("trigger", "t_001", 1, {})
    counts = store.counts()
    assert counts["merchant"] == 2
    assert counts["category"] == 1
    assert counts["trigger"] == 1
    assert counts["customer"] == 0


def test_typed_accessors(store):
    store.put("category", "gyms", 1, {"slug": "gyms"})
    store.put("merchant", "m_007", 1, {"merchant_id": "m_007"})
    store.put("customer", "c_001", 1, {"customer_id": "c_001"})
    store.put("trigger", "t_001", 1, {"kind": "perf_dip"})
    assert store.get_category("gyms") == {"slug": "gyms"}
    assert store.get_merchant("m_007") == {"merchant_id": "m_007"}
    assert store.get_customer("c_001") == {"customer_id": "c_001"}
    assert store.get_trigger("t_001") == {"kind": "perf_dip"}


def test_get_missing_returns_none(store):
    assert store.get("merchant", "nonexistent") is None


def test_clear(store):
    store.put("merchant", "m_001", 1, {})
    store.clear()
    assert store.get("merchant", "m_001") is None
    assert store.counts()["merchant"] == 0


def test_list_ids(store):
    store.put("merchant", "m_001", 1, {})
    store.put("merchant", "m_002", 1, {})
    store.put("category", "gyms", 1, {})
    ids = store.list_ids("merchant")
    assert set(ids) == {"m_001", "m_002"}
