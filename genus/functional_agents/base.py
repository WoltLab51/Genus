"""Functional Agent Base — GENUS-2.0

Abstract base class for all functional agents (Home, Family, Knowledge, …).

Each functional agent handles a specific domain and can be invoked via
the ``/v1/agents/{agent_id}/invoke`` API endpoint or over WebSocket.

Design:
- ``FunctionalAgent`` is a pure-Python ABC; it does *not* extend any agent
  from ``genus.core`` so it can be used without the full DevLoop stack.
- Agents are registered in ``FunctionalAgentRegistry`` at startup.
- ``AgentContext`` carries request-level metadata (user, session, actor).
- ``AgentResponse`` is a structured response returned by ``handle()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional, Sequence, Tuple


@dataclass
class AgentContext:
    """Context passed to a functional agent when handling a request.

    Args:
        user_id:    The authenticated user making the request.
        session_id: Current session identifier.
        actor_id:   API actor identifier (from auth middleware).
        metadata:   Additional key-value pairs from the request body.
    """

    user_id: str
    session_id: str = "default"
    actor_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Response returned by a functional agent.

    Args:
        agent_id: The agent that produced this response.
        text:     Human-readable response text shown to the user.
        success:  Whether the request was handled successfully.
        data:     Optional structured data payload (for machine consumers).
        metadata: Additional response metadata.
    """

    agent_id: str
    text: str
    success: bool = True
    data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "agent_id": self.agent_id,
            "text": self.text,
            "success": self.success,
            "data": self.data,
            "metadata": self.metadata,
        }


class FunctionalAgent(ABC):
    """Abstract base class for GENUS-2.0 functional agents.

    Subclasses **must** define the following class attributes:

    - ``agent_id``   — unique string identifier (e.g. ``"home"``)
    - ``role``       — short role label (e.g. ``"smart_home"``)
    - ``description``— one-line human-readable description

    Subclasses **may** override:

    - ``allowed_tools``  — whitelist of tool names the agent may use (immutable class-level tuple)
    - ``required_scope`` — minimum scope needed to invoke the agent
    - ``can_handle()``   — intent-based filtering
    """

    agent_id: str
    role: str
    description: str
    allowed_tools: ClassVar[Tuple[str, ...]] = ()
    required_scope: str = "system"

    @abstractmethod
    async def handle(self, intent: str, context: AgentContext) -> AgentResponse:
        """Handle an intent and return a response.

        Args:
            intent:  Natural-language description of what the user wants.
            context: Request context (user, session, metadata).

        Returns:
            :class:`AgentResponse` with ``text`` and optional structured ``data``.
        """

    async def can_handle(self, intent: str) -> bool:
        """Return True if this agent is appropriate for *intent*.

        The default implementation always returns ``True``. Override to
        add keyword-based or ML-based intent filtering.

        Args:
            intent: Natural-language intent string.

        Returns:
            True when the agent should handle this intent.
        """
        return True

    def status(self) -> Dict[str, Any]:
        """Return a status dict describing this agent.

        Returns:
            Dict with ``agent_id``, ``role``, ``description``,
            ``allowed_tools``, ``required_scope``, and ``ready`` flag.
        """
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "description": self.description,
            "allowed_tools": list(self.allowed_tools),
            "required_scope": self.required_scope,
            "ready": True,
        }
