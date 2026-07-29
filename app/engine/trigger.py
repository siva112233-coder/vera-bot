"""
Deterministic trigger prioritizer.

Given a list of available trigger IDs, resolves each against the context store,
applies expiry / suppression filters, and returns a sorted list ready for composition.
Sort order: urgency DESC, then trigger_id ASC (deterministic tiebreak).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.store.memory import ContextStore
from app.engine.suppression import SuppressionRegistry


def _parse_iso(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        # Handle both Z suffix and +offset
        s = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _is_expired(trigger: dict[str, Any], now: datetime) -> bool:
    expires_at = _parse_iso(trigger.get("expires_at"))
    if expires_at is None:
        return False  # no expiry = never expires
    return now >= expires_at


class TriggerPrioritizer:
    """
    Deterministic trigger selection for a single tick.

    Algorithm:
    1. Resolve each trigger_id from the context store
    2. Skip if trigger not found
    3. Skip if expired (now >= expires_at)
    4. Skip if suppression_key already consumed
    5. Sort by urgency DESC, then id ASC
    6. One trigger per (merchant_id) per tick (highest urgency wins)
    7. Return sorted, deduplicated list
    """

    def __init__(self, store: ContextStore, suppression: SuppressionRegistry) -> None:
        self.store = store
        self.suppression = suppression

    def select(
        self,
        available_trigger_ids: list[str],
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return a list of resolved trigger payloads, sorted and filtered.

        Each entry in the returned list is the raw payload dict from the store,
        augmented with the trigger's own context_id as `_trigger_id`.
        """
        now = now or datetime.now(timezone.utc)
        candidates: list[dict[str, Any]] = []

        for trigger_id in available_trigger_ids:
            trg = self.store.get_trigger(trigger_id)
            if trg is None:
                continue

            # Expiry check
            if _is_expired(trg, now):
                continue

            # Suppression check
            suppression_key = trg.get("suppression_key", "")
            if suppression_key and self.suppression.is_suppressed(suppression_key):
                continue

            # Augment with the trigger_id so downstream can reference it
            entry = dict(trg)
            entry["_trigger_id"] = trigger_id
            candidates.append(entry)

        # Sort: urgency DESC, then trigger_id ASC (fully deterministic)
        candidates.sort(key=lambda t: (-t.get("urgency", 1), t["_trigger_id"]))

        # Deduplicate: one trigger per merchant (highest urgency already first)
        seen_merchants: set[str] = set()
        deduplicated: list[dict[str, Any]] = []
        for trg in candidates:
            mid = trg.get("merchant_id") or ""
            if mid and mid in seen_merchants:
                continue
            if mid:
                seen_merchants.add(mid)
            deduplicated.append(trg)

        return deduplicated

    def resolve_contexts(
        self,
        trigger: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        """
        Given a resolved trigger payload, return (merchant, category, customer).
        Any of these may be None if the context isn't loaded yet.
        """
        merchant_id = trigger.get("merchant_id") or ""
        customer_id = trigger.get("customer_id") or ""

        merchant = self.store.get_merchant(merchant_id) if merchant_id else None
        customer = self.store.get_customer(customer_id) if customer_id else None

        category_slug = ""
        if merchant:
            category_slug = merchant.get("category_slug", "")

        category = self.store.get_category(category_slug) if category_slug else None

        return merchant, category, customer


# Module-level singleton
_prioritizer: TriggerPrioritizer | None = None


def get_trigger_prioritizer() -> TriggerPrioritizer:
    global _prioritizer
    if _prioritizer is None:
        from app.store.memory import get_store
        from app.engine.suppression import get_suppression_registry
        _prioritizer = TriggerPrioritizer(get_store(), get_suppression_registry())
    return _prioritizer
