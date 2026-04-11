"""
ConnectionManager — Phase 12

Manages active WebSocket connections and ConversationAgent sessions.

Each ``session_id`` maps to exactly one :class:`ConversationSession`.
Sessions are reused across WebSocket reconnects.
Inactive sessions are cleaned up after ``GENUS_SESSION_TIMEOUT_MINUTES``
(default 30) minutes of inactivity.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from genus.communication.message_bus import MessageBus
from genus.conversation.conversation_agent import ConversationAgent

logger = logging.getLogger(__name__)


class ConversationSession:
    """Wraps a :class:`ConversationAgent` for a single session."""

    def __init__(self, session_id: str, agent: ConversationAgent) -> None:
        self.session_id = session_id
        self.agent = agent
        self._last_active: datetime = datetime.now(timezone.utc)

    def touch(self) -> None:
        """Update the last-active timestamp."""
        self._last_active = datetime.now(timezone.utc)

    @property
    def last_active(self) -> datetime:
        return self._last_active

    def idle_minutes(self) -> float:
        delta = datetime.now(timezone.utc) - self._last_active
        return delta.total_seconds() / 60.0


class ConnectionManager:
    """Manages per-session :class:`ConversationAgent` instances.

    A single :class:`ConversationAgent` is shared for the lifetime of a
    session.  When a client reconnects with the same ``session_id`` it
    resumes the same conversation history.

    Args:
        default_llm_router:     Default LLMRouter injected into new sessions.
                                Can be overridden per-session via
                                ``get_or_create_session``.
        default_bus:            Default MessageBus injected into new sessions.
        conversations_dir:      Where to persist per-session JSONL files.
        max_history:            Maximum messages in the LLM context window.
    """

    def __init__(
        self,
        *,
        default_llm_router: Optional[Any] = None,
        default_bus: Optional[MessageBus] = None,
        conversations_dir: Optional[Path] = None,
        max_history: int = 20,
    ) -> None:
        self._sessions: Dict[str, ConversationSession] = {}
        self._default_llm_router = default_llm_router
        self._default_bus = default_bus
        self._max_history = max_history
        self._conversations_dir: Path = conversations_dir or Path(
            os.environ.get("GENUS_CONVERSATIONS_DIR", "var/conversations")
        )

    def get_or_create_session(
        self,
        session_id: str,
        llm_router: Optional[Any] = None,
        bus: Optional[MessageBus] = None,
    ) -> ConversationSession:
        """Return an existing session or create a new one.

        Args:
            session_id:  Unique session identifier.
            llm_router:  Override the default LLMRouter for this session.
                         Falls back to the manager's default when ``None``.
            bus:         Override the default MessageBus for this session.
                         Falls back to the manager's default when ``None``.
        """
        if session_id in self._sessions:
            return self._sessions[session_id]

        effective_router = llm_router if llm_router is not None else self._default_llm_router
        effective_bus = bus if bus is not None else self._default_bus

        if effective_bus is None:
            # Fallback: create a minimal MessageBus for the agent
            from genus.communication.message_bus import MessageBus as _MB
            effective_bus = _MB()

        agent = ConversationAgent(
            message_bus=effective_bus,
            llm_router=effective_router,
            max_history=self._max_history,
            conversations_dir=self._conversations_dir,
        )
        session = ConversationSession(session_id=session_id, agent=agent)
        self._sessions[session_id] = session
        logger.debug("Created ConversationSession: %s", session_id)
        return session

    def cleanup_inactive_sessions(self, max_age_minutes: int = 30) -> int:
        """Remove sessions that have been inactive for *max_age_minutes*.

        Returns:
            Number of sessions removed.
        """
        to_remove = [
            sid
            for sid, session in self._sessions.items()
            if session.idle_minutes() > max_age_minutes
        ]
        for sid in to_remove:
            del self._sessions[sid]
            logger.debug("Removed inactive ConversationSession: %s", sid)
        return len(to_remove)

    @property
    def active_sessions(self) -> int:
        """Return the number of currently active sessions."""
        return len(self._sessions)
