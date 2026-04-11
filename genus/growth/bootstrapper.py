"""
Agent Bootstrapper

Handles the integration of newly built agents into the running GENUS system.
The AgentBootstrapper receives ``dev.loop.completed`` events and:

1. Loads the generated agent class via ``importlib`` (Phase 9).
2. Instantiates, initialises, and starts the agent.
3. Registers the new agent's topics in the ``TopicRegistry``.
4. Publishes ``agent.bootstrapped`` to signal successful integration.
5. Publishes ``agent.deprecated`` whenever a previously registered agent with
   the same name is being replaced (and stops the old instance).

In the GENUS growth flow the AgentBootstrapper sits at the very end of the
build pipeline:

    GrowthOrchestrator → DevLoopOrchestrator → … → AgentBootstrapper

Topics subscribed:
    - ``dev.loop.completed``

Topics published:
    - ``agent.bootstrapped``     — emitted after a successful bootstrap.
    - ``agent.deprecated``       — emitted before bootstrapping when an agent
                                   with the same name already exists and is
                                   being replaced.
    - ``agent.bootstrap_failed`` — emitted when the generated module cannot be
                                   imported (import-time exception).
    - ``agent.start.failed``     — emitted when ``initialize()`` or ``start()``
                                   raises an exception.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.communication.topic_registry import TopicEntry, TopicRegistry
from genus.core.agent import Agent, AgentState
from genus.dev.agents.agent_code_template import class_name_to_filename

logger = logging.getLogger(__name__)

# Topic constants
_TOPIC_DEV_LOOP_COMPLETED = "dev.loop.completed"
_TOPIC_AGENT_BOOTSTRAPPED = "agent.bootstrapped"
_TOPIC_AGENT_DEPRECATED = "agent.deprecated"
_TOPIC_AGENT_BOOTSTRAP_FAILED = "agent.bootstrap_failed"
_TOPIC_AGENT_START_FAILED = "agent.start.failed"

# Default path for generated agent modules (relative to this file's package root)
_DEFAULT_GENERATED_PATH = Path(__file__).parent.parent / "agents" / "generated"


def _utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AgentBootstrapper(Agent):
    """Integrates newly built agents into the GENUS runtime signal fabric.

    The bootstrapper maintains an ``_active_agents`` dict mapping agent name to
    a record ``{"instance": Optional[Agent], "agent_id": str, "domain": str}``.

    When a ``dev.loop.completed`` event is received the bootstrapper:

    1. If an agent with the same name already exists: stops its instance (if
       running) and publishes ``agent.deprecated``.
    2. Attempts to load the generated agent class via ``importlib``.  Falls
       back to loading directly from the known file path when the module is not
       yet on ``sys.path``.
    3. Instantiates, initialises, and starts the agent.
    4. Registers the new agent's topics in the ``TopicRegistry``.
    5. Records the new agent in ``_active_agents``.
    6. Publishes ``agent.bootstrapped``.

    On errors:

    - Import-time exception (broken generated code) →  ``agent.bootstrap_failed``
      is published; no crash.
    - ``initialize()`` / ``start()`` exception → ``agent.start.failed`` is
      published; no crash.
    - When no generated class is found at all (the file simply does not exist
      yet) the bootstrap still completes and ``agent.bootstrapped`` is
      published, but ``_active_agents[name]["instance"]`` will be ``None``.

    Args:
        message_bus:           The MessageBus to subscribe to and publish on.
        topic_registry:        The :class:`~genus.communication.topic_registry.TopicRegistry`
                               in which newly registered topics will be
                               recorded.
        agent_id:              Optional custom agent ID.  Auto-generated if not
                               provided.
        name:                  Optional human-readable agent name.  Defaults to
                               ``"AgentBootstrapper"``.
        generated_agents_path: Optional override for the directory that
                               contains generated agent ``.py`` files.
                               Defaults to ``genus/agents/generated/`` inside
                               the installed package.  Useful for tests that
                               write generated files to a temporary directory.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        topic_registry: TopicRegistry,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        generated_agents_path: Optional[Path] = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "AgentBootstrapper")
        self._bus = message_bus
        self._topic_registry = topic_registry
        self._generated_agents_path: Path = (
            generated_agents_path
            if generated_agents_path is not None
            else _DEFAULT_GENERATED_PATH
        )
        # agent_name → {"instance": Optional[Agent], "agent_id": str, "domain": str}
        self._active_agents: Dict[str, dict] = {}

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
    # Agent loading
    # ------------------------------------------------------------------

    def _load_agent_class(self, agent_name: str) -> Optional[type]:
        """Load the agent class *agent_name* from ``genus.agents.generated``.

        Tries ``importlib.import_module`` first.  If the module is not on
        ``sys.path`` (``ImportError``) it falls back to loading the ``.py``
        file directly from ``self._generated_agents_path``.

        Any exception *other* than a plain ``ImportError`` (e.g.
        ``SyntaxError`` in the generated file) is **not** caught here — it
        bubbles up to ``process_message``, which catches it, logs it, and
        publishes ``agent.bootstrap_failed``.

        Args:
            agent_name: CamelCase class name, e.g. ``"FamilyCalendarAgent"``.

        Returns:
            The agent class, or ``None`` when no module / file is found.
        """
        # SECURITY-TODO: generated code runs without sandbox
        module_name = class_name_to_filename(agent_name)
        try:
            module = importlib.import_module(f"genus.agents.generated.{module_name}")
            return getattr(module, agent_name, None)
        except ImportError:
            return self._load_agent_from_file(agent_name, module_name)

    def _load_agent_from_file(self, agent_name: str, module_name: str) -> Optional[type]:
        """Fallback: load the agent class directly from a ``.py`` file.

        Used when ``importlib.import_module`` fails because the generated
        directory is not (yet) on ``sys.path``.

        Any exception raised while executing the module (e.g. ``SyntaxError``,
        ``ImportError`` of a missing dependency) is **not** caught here; it
        bubbles up to the caller (``_load_agent_class``), which in turn lets it
        propagate to ``process_message`` for error-event publishing.

        Args:
            agent_name:  CamelCase class name.
            module_name: snake_case module filename (without ``.py``).

        Returns:
            The agent class, or ``None`` when the file does not exist.
        """
        path = self._generated_agents_path / f"{module_name}.py"
        if not path.exists():
            return None

        spec = importlib.util.spec_from_file_location(
            f"genus.agents.generated.{module_name}", path
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return getattr(module, agent_name, None)

    async def _start_agent(
        self, agent_class: type, agent_id: str, agent_name: str
    ) -> Optional[Agent]:
        """Instantiate, initialise, and start a generated agent.

        Args:
            agent_class: The agent class to instantiate.
            agent_id:    Unique identifier for the new instance.
            agent_name:  Human-readable name passed to the constructor.

        Returns:
            The running :class:`~genus.core.agent.Agent` instance, or ``None``
            if an exception was raised during construction / lifecycle.
        """
        try:
            instance = agent_class(
                message_bus=self._bus, agent_id=agent_id, name=agent_name
            )
            await instance.initialize()
            await instance.start()
            return instance
        except Exception as exc:
            logger.error(
                "AgentBootstrapper: failed to start %s: %s", agent_name, exc
            )
            return None

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
            previous_entry = self._active_agents[agent_name]
            previous_id = previous_entry["agent_id"]
            previous_instance: Optional[Agent] = previous_entry.get("instance")
            if previous_instance is not None:
                try:
                    await previous_instance.stop()
                except Exception as exc:
                    logger.warning(
                        "AgentBootstrapper: error stopping previous %s: %s",
                        agent_name,
                        exc,
                    )
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

        # 2) Load the generated agent class
        try:
            agent_class = self._load_agent_class(agent_name)
        except Exception as exc:
            logger.error(
                "AgentBootstrapper: failed to import %s: %s", agent_name, exc
            )
            await self._bus.publish(
                Message(
                    topic=_TOPIC_AGENT_BOOTSTRAP_FAILED,
                    payload={
                        "agent_name": agent_name,
                        "agent_id": new_agent_id,
                        "domain": domain,
                        "reason": str(exc),
                        "failed_at": now,
                    },
                    sender_id=self.id,
                )
            )
            return

        # 3) Instantiate and start the agent (only if a class was found)
        instance: Optional[Agent] = None
        if agent_class is not None:
            instance = await self._start_agent(agent_class, new_agent_id, agent_name)
            if instance is None:
                await self._bus.publish(
                    Message(
                        topic=_TOPIC_AGENT_START_FAILED,
                        payload={
                            "agent_name": agent_name,
                            "agent_id": new_agent_id,
                            "domain": domain,
                            "failed_at": now,
                        },
                        sender_id=self.id,
                    )
                )
                return

        # 4) Register the new agent's topics in the TopicRegistry
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

        # 5) Record the new agent
        self._active_agents[agent_name] = {
            "instance": instance,
            "agent_id": new_agent_id,
            "domain": domain,
        }

        # 6) Publish agent.bootstrapped
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
