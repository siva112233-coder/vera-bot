"""Thread-safe suppression registry — prevents duplicate message sends."""
from __future__ import annotations

import threading
from datetime import datetime, timezone


class SuppressionRegistry:
    """
    Tracks suppression_keys that have already been sent.

    A suppression_key is considered consumed once `mark_sent` is called.
    The same key can be re-sent in a *different* conversation only if you
    explicitly release it (used for test teardown).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # suppression_key -> {sent_at, conversation_id}
        self._sent: dict[str, dict[str, str]] = {}

    def is_suppressed(self, suppression_key: str) -> bool:
        """Return True if this key has already been sent."""
        with self._lock:
            return suppression_key in self._sent

    def mark_sent(self, suppression_key: str, conversation_id: str) -> None:
        """Record that this suppression_key was sent in conversation_id."""
        with self._lock:
            if suppression_key not in self._sent:
                self._sent[suppression_key] = {
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "conversation_id": conversation_id,
                }

    def release(self, suppression_key: str) -> None:
        """Remove a key (for test teardown or explicit reset)."""
        with self._lock:
            self._sent.pop(suppression_key, None)

    def all_sent(self) -> dict[str, dict[str, str]]:
        with self._lock:
            return dict(self._sent)

    def clear(self) -> None:
        with self._lock:
            self._sent.clear()


# Module-level singleton
_registry: SuppressionRegistry | None = None


def get_suppression_registry() -> SuppressionRegistry:
    global _registry
    if _registry is None:
        _registry = SuppressionRegistry()
    return _registry
