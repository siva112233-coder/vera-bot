"""Conversation state machine with auto-reply, intent, and hostile detection."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ConversationState(str, Enum):
    QUALIFYING = "qualifying"
    ACTIONING = "actioning"
    WAITING = "waiting"
    ENDED = "ended"


@dataclass
class Turn:
    from_role: str  # "vera" | "merchant" | "customer"
    body: str
    received_at: str
    turn_number: int


@dataclass
class Conversation:
    conversation_id: str
    merchant_id: str
    customer_id: str | None
    trigger_id: str
    state: ConversationState = ConversationState.QUALIFYING
    turns: list[Turn] = field(default_factory=list)
    auto_reply_count: int = 0
    intent_accepted: bool = False
    hostile: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pattern matchers (compiled once at module load)
# ---------------------------------------------------------------------------

_INTENT_PATTERNS = re.compile(
    r"\b("
    r"yes|ok|okay|sure|proceed|go ahead|lets do it|let's do it|"
    r"do it|haan|theek hai|chalega|chalo|bilkul|zaroor|"
    r"perfect|great|sounds good|please do|go for it|"
    r"send me|send it|please send|share it|share that|"
    r"start|begin|confirm|approve|agreed"
    r")\b",
    re.IGNORECASE,
)

_HOSTILE_PATTERNS = re.compile(
    r"\b("
    r"stop|spam|remove|block|unsubscribe|opt.?out|"
    r"not interested|nahi chahiye|mat bhejo|band karo|"
    r"don'?t (message|contact|send|call)|no more|"
    r"leave me alone|stop messaging|stop contacting|"
    r"useless|waste|annoying"
    r")\b",
    re.IGNORECASE,
)

# Known auto-reply phrases (partial match)
_AUTO_REPLY_FRAGMENTS = [
    "thank you for contacting",
    "our team will respond",
    "automated (message|reply|assistant)",
    "i am an automated",
    "aapki jaankari ke liye bahut.?bahut shukriya",
    "main aapki.*baatein.*team tak pahuncha",
    "we will get back to you",
    "your message has been received",
]
_AUTO_REPLY_RE = re.compile(
    "|".join(_AUTO_REPLY_FRAGMENTS),
    re.IGNORECASE,
)

_QUESTION_RE = re.compile(r"\?")


def _classify_message(text: str) -> dict[str, bool]:
    """Classify an incoming merchant message into signal categories."""
    return {
        "is_auto_reply_pattern": bool(_AUTO_REPLY_RE.search(text)),
        "is_intent_accept": bool(_INTENT_PATTERNS.search(text)),
        "is_hostile": bool(_HOSTILE_PATTERNS.search(text)),
        "is_question": bool(_QUESTION_RE.search(text)),
    }


class ConversationManager:
    """
    Thread-safe store for all active conversations.

    Handles:
    - Turn recording
    - Auto-reply detection (same text 3+ consecutive turns OR known pattern)
    - Intent transition (accepted → ACTIONING)
    - Hostile exit (hostile signal → ENDED)
    """

    MAX_AUTO_REPLY_TOLERANCE = 2  # Try once after first auto-reply, then end

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._conversations: dict[str, Conversation] = {}

    # ------------------------------------------------------------------
    # Create / retrieve
    # ------------------------------------------------------------------

    def create(
        self,
        conversation_id: str,
        merchant_id: str,
        trigger_id: str,
        customer_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Conversation:
        with self._lock:
            conv = Conversation(
                conversation_id=conversation_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
                trigger_id=trigger_id,
                metadata=metadata or {},
            )
            self._conversations[conversation_id] = conv
            return conv

    def get(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            return self._conversations.get(conversation_id)

    def get_or_create(
        self,
        conversation_id: str,
        merchant_id: str,
        trigger_id: str = "unknown",
        customer_id: str | None = None,
    ) -> Conversation:
        with self._lock:
            if conversation_id not in self._conversations:
                return self.create(
                    conversation_id, merchant_id, trigger_id, customer_id
                )
            return self._conversations[conversation_id]

    # ------------------------------------------------------------------
    # Record Vera's outbound turn
    # ------------------------------------------------------------------

    def record_sent(
        self,
        conversation_id: str,
        body: str,
        turn_number: int = 1,
    ) -> None:
        with self._lock:
            conv = self._conversations.get(conversation_id)
            if conv is None:
                return
            conv.turns.append(
                Turn(
                    from_role="vera",
                    body=body,
                    received_at=datetime.now(timezone.utc).isoformat(),
                    turn_number=turn_number,
                )
            )

    # ------------------------------------------------------------------
    # Process an inbound reply
    # ------------------------------------------------------------------

    def process_reply(
        self,
        conversation_id: str,
        from_role: str,
        message: str,
        turn_number: int,
        merchant_id: str = "",
        trigger_id: str = "unknown",
    ) -> dict[str, Any]:
        """
        Record the inbound turn and return a signal dict describing the reply.

        Returns:
            {
                state: ConversationState,
                is_auto_reply: bool,
                is_intent_accept: bool,
                is_hostile: bool,
                is_question: bool,
                vera_turn_count: int,
                merchant_turn_count: int,
            }
        """
        with self._lock:
            if conversation_id not in self._conversations:
                self.create(conversation_id, merchant_id, trigger_id)
            conv = self._conversations[conversation_id]

            if conv.state == ConversationState.ENDED:
                return self._signal(conv, auto_reply=False, intent=False, hostile=conv.hostile, question=False)

            # Record turn
            turn = Turn(
                from_role=from_role,
                body=message,
                received_at=datetime.now(timezone.utc).isoformat(),
                turn_number=turn_number,
            )
            conv.turns.append(turn)

            # Classify
            signals = _classify_message(message)

            # Auto-reply detection: pattern match OR same verbatim text 3+ times
            is_auto_reply = signals["is_auto_reply_pattern"]
            if not is_auto_reply:
                merchant_msgs = [
                    t.body for t in conv.turns if t.from_role in ("merchant", "customer")
                ]
                if len(merchant_msgs) >= 3 and len(set(merchant_msgs[-3:])) == 1:
                    is_auto_reply = True

            if is_auto_reply:
                conv.auto_reply_count += 1
                if conv.auto_reply_count > self.MAX_AUTO_REPLY_TOLERANCE:
                    conv.state = ConversationState.ENDED

            # Hostile check
            if signals["is_hostile"]:
                conv.hostile = True
                conv.state = ConversationState.ENDED

            # Intent check
            if signals["is_intent_accept"] and not is_auto_reply and not signals["is_hostile"]:
                conv.intent_accepted = True
                conv.state = ConversationState.ACTIONING

            return self._signal(
                conv,
                auto_reply=is_auto_reply,
                intent=signals["is_intent_accept"],
                hostile=signals["is_hostile"],
                question=signals["is_question"],
            )

    def _signal(
        self,
        conv: Conversation,
        auto_reply: bool,
        intent: bool,
        hostile: bool,
        question: bool,
    ) -> dict[str, Any]:
        vera_turns = sum(1 for t in conv.turns if t.from_role == "vera")
        merchant_turns = sum(
            1 for t in conv.turns if t.from_role in ("merchant", "customer")
        )
        return {
            "state": conv.state,
            "is_auto_reply": auto_reply,
            "is_intent_accept": intent,
            "is_hostile": hostile,
            "is_question": question,
            "vera_turn_count": vera_turns,
            "merchant_turn_count": merchant_turns,
            "auto_reply_count": conv.auto_reply_count,
            "intent_accepted_overall": conv.intent_accepted,
        }

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def is_ended(self, conversation_id: str) -> bool:
        with self._lock:
            conv = self._conversations.get(conversation_id)
            return conv is not None and conv.state == ConversationState.ENDED

    def end(self, conversation_id: str) -> None:
        with self._lock:
            conv = self._conversations.get(conversation_id)
            if conv:
                conv.state = ConversationState.ENDED

    def last_vera_body(self, conversation_id: str) -> str | None:
        with self._lock:
            conv = self._conversations.get(conversation_id)
            if not conv:
                return None
            for turn in reversed(conv.turns):
                if turn.from_role == "vera":
                    return turn.body
            return None

    def clear(self) -> None:
        with self._lock:
            self._conversations.clear()


# Module-level singleton
_manager: ConversationManager | None = None


def get_conversation_manager() -> ConversationManager:
    global _manager
    if _manager is None:
        _manager = ConversationManager()
    return _manager
