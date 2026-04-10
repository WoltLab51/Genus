"""
Agent Bootstrapper

Handles the integration of newly built agents into the running GENUS system.
The AgentBootstrapper receives ``dev.loop.completed`` events and registers the
new agent's topics in the ``TopicRegistry``, publishes ``agent.bootstrapped``
to signal successful integration, and publishes ``agent.deprecated`` whenever a
previously registered agent with the same name is being replaced.

In the GENUS growth flow the AgentBootstrapper sits at the very end of the
build pipeline:

    GrowthOrchestrator → DevLoopOrchestrator → … → AgentBootstrapper

Phase 5 covers signal management only; actual runtime code-loading is deferred
to Phase 6.

Topics subscribed:
    - ``dev.loop.completed``

Topics published:
    - ``agent.bootstrapped`` — emitted after a successful bootstrap.
    - ``agent.deprecated``   — emitted before bootstrapping when an agent with
      the same name already exists and is being replaced.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.communication.topic_registry import TopicEntry, TopicRegistry
from genus.core.agent import Agent, AgentState

# Topic constants
_TOPIC_DEV_LOOP_COMPLETED = "dev.loop.completed"
_TOPIC_AGENT_BOOTSTRAPPED = "agent.bootstrapped"
_TOPIC_AGENT_DEPRECATED = "agent.deprecated"


def _utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AgentBootstrapper(Agent):
    """Integrates newly built agents into the GENUS runtime signal fabric.

    The bootstrapper maintains an ``_active_agents`` dict mapping agent name to
    agent ID.  When a ``dev.loop.completed`` event is received the bootstrapper:

    1. Checks whether an agent with the same name already exists.  If so, a
       ``agent.deprecated`` event is published for the previous agent.
    2. Registers the new agent's topics in the ``TopicRegistry``.
    3. Records the new agent in ``_active_agents``.
    4. Publishes ``agent.bootstrapped``.

    Args:
        message_bus: The MessageBus to subscribe to and publish on.
        topic_registry: The :class:`~genus.communication.topic_registry.TopicRegistry`
            in which newly registered topics will be recorded.
        agent_id: Optional custom agent ID.  Auto-generated if not provided.
        name: Optional human-readable agent name.  Defaults to
            ``"AgentBootstrapper"``.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        topic_registry: TopicRegistry,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "AgentBootstrapper")
        self._bus = message_bus
        self._topic_registry = topic_registry
        # agent_name → agent_id of the currently active instance
        self._active_agents: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to ``dev.loop.completed``."""
        self._bus.subscribe(_TOPIC_DEV_LOOP_COMPLETED, self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Transition to RUNNING state."""
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        """Unsubscribe from all topics and transition to STOPPED state."""
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def process_message(self, message: Message) -> None:
        """Handle a ``dev.loop.completed`` event.

        Extracts ``agent_name``, ``agent_id``, ``domain``, and optional
        ``topics`` from the payload, then performs the full bootstrap sequence.

        Args:
            message: The incoming MessageBus message.
        """
        if message.topic != _TOPIC_DEV_LOOP_COMPLETED:
            return

        payload = message.payload if isinstance(message.payload, dict) else {}
        agent_name: str = payload.get("agent_name", "")
        new_agent_id: str = payload.get("agent_id", "")
        domain: str = payload.get("domain", "")
        topics: List[str] = list(payload.get("topics", []))

        if not agent_name or not new_agent_id:
            return

        now = _utc_now()

        # 1) Deprecate the previous agent if it exists
        if agent_name in self._active_agents:
            previous_id = self._active_agents[agent_name]
            await self._bus.publish(
                Message(
                    topic=_TOPIC_AGENT_DEPRECATED,
                    payload={
                        "agent_name": agent_name,
                        "previous_agent_id": previous_id,
                        "replaced_by": new_agent_id,
                        "deprecated_at": now,
                    },
                    sender_id=self.id,
                )
            )

        # 2) Register the new agent's topics in the TopicRegistry
        registered_topics: List[str] = []
        for topic in topics:
            if not self._topic_registry.is_registered(topic):
                self._topic_registry.register(
                    TopicEntry(
                        topic=topic,
                        owner=agent_name,
                        direction="publish",
                        domain=domain or "growth",
                        description=f"Registered by AgentBootstrapper for {agent_name}.",
                    )
                )
            registered_topics.append(topic)

        # 3) Record the new agent
        self._active_agents[agent_name] = new_agent_id

        # 4) Publish agent.bootstrapped
        await self._bus.publish(
            Message(
                topic=_TOPIC_AGENT_BOOTSTRAPPED,
                payload={
                    "agent_name": agent_name,
                    "agent_id": new_agent_id,
                    "domain": domain,
                    "bootstrapped_at": now,
                    "topics_registered": registered_topics,
                },
                sender_id=self.id,
            )
        )
