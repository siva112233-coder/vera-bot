"""Thread-safe in-memory context store with versioned, idempotent writes."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any


class ContextStore:
    """
    Stores all 4 context types: category, merchant, customer, trigger.

    Keyed by (scope, context_id). Version is monotonically increasing;
    a lower-or-equal version for an existing key is a no-op (idempotent).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # (scope, context_id) -> {version, payload, stored_at}
        self._store: dict[tuple[str, str], dict[str, Any]] = {}
        self._start_time = time.monotonic()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def put(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict[str, Any],
    ) -> tuple[bool, str | None, int | None]:
        """
        Store a context entry.

        Returns:
            (accepted, reason, current_version)
            - accepted=True  → stored successfully
            - accepted=False → stale version; current_version holds the stored one
        """
        key = (scope, context_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            existing = self._store.get(key)
            if existing is not None and existing["version"] >= version:
                return False, "stale_version", existing["version"]

            self._store[key] = {
                "version": version,
                "payload": payload,
                "stored_at": now_iso,
            }
            return True, None, None

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, scope: str, context_id: str) -> dict[str, Any] | None:
        """Return the raw payload dict for the given (scope, context_id), or None."""
        with self._lock:
            entry = self._store.get((scope, context_id))
            return entry["payload"] if entry else None

    def get_version(self, scope: str, context_id: str) -> int | None:
        """Return the stored version number, or None if not found."""
        with self._lock:
            entry = self._store.get((scope, context_id))
            return entry["version"] if entry else None

    def get_stored_at(self, scope: str, context_id: str) -> str | None:
        with self._lock:
            entry = self._store.get((scope, context_id))
            return entry["stored_at"] if entry else None

    # ------------------------------------------------------------------
    # Typed accessors
    # ------------------------------------------------------------------

    def get_category(self, slug: str) -> dict[str, Any] | None:
        return self.get("category", slug)

    def get_merchant(self, merchant_id: str) -> dict[str, Any] | None:
        return self.get("merchant", merchant_id)

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        return self.get("customer", customer_id)

    def get_trigger(self, trigger_id: str) -> dict[str, Any] | None:
        return self.get("trigger", trigger_id)

    # ------------------------------------------------------------------
    # Counts / listing
    # ------------------------------------------------------------------

    def counts(self) -> dict[str, int]:
        """Return count of stored contexts per scope."""
        result: dict[str, int] = {
            "category": 0,
            "merchant": 0,
            "customer": 0,
            "trigger": 0,
        }
        with self._lock:
            for scope, _ in self._store:
                if scope in result:
                    result[scope] += 1
        return result

    def list_ids(self, scope: str) -> list[str]:
        """Return all context_ids for a given scope."""
        with self._lock:
            return [cid for (s, cid) in self._store if s == scope]

    # ------------------------------------------------------------------
    # Uptime
    # ------------------------------------------------------------------

    def uptime_seconds(self) -> int:
        return int(time.monotonic() - self._start_time)

    # ------------------------------------------------------------------
    # Teardown (for /v1/teardown or test cleanup)
    # ------------------------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Module-level singleton shared across the application
_store: ContextStore | None = None


def get_store() -> ContextStore:
    global _store
    if _store is None:
        _store = ContextStore()
    return _store
