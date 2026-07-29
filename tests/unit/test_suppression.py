"""Unit tests for SuppressionRegistry."""
from __future__ import annotations

import pytest

from app.engine.suppression import SuppressionRegistry


@pytest.fixture
def registry():
    return SuppressionRegistry()


def test_not_suppressed_by_default(registry):
    assert registry.is_suppressed("some:key") is False


def test_mark_and_check(registry):
    registry.mark_sent("key:abc", "conv_001")
    assert registry.is_suppressed("key:abc") is True


def test_mark_is_idempotent(registry):
    registry.mark_sent("key:abc", "conv_001")
    registry.mark_sent("key:abc", "conv_002")  # second call ignored
    # Still suppressed
    assert registry.is_suppressed("key:abc") is True
    # Original conversation preserved
    assert registry.all_sent()["key:abc"]["conversation_id"] == "conv_001"


def test_release(registry):
    registry.mark_sent("key:xyz", "conv_001")
    registry.release("key:xyz")
    assert registry.is_suppressed("key:xyz") is False


def test_clear(registry):
    registry.mark_sent("k1", "c1")
    registry.mark_sent("k2", "c2")
    registry.clear()
    assert not registry.all_sent()


def test_different_keys_independent(registry):
    registry.mark_sent("key:a", "conv_a")
    assert registry.is_suppressed("key:b") is False
