"""
MemoryAgent — Phase 14b

Listens for memory-related events on the message bus and coordinates
episodic compression and semantic fact storage.

Topics consumed:
    memory.compress.requested  — Compress a session into an Episode
    memory.fact.upsert         — Store or update a SemanticFact

Topics published:
    memory.compress.completed  — Episode was created successfully
    memory.compress.failed     — Compression failed (payload has reason)
    memory.fact.stored         — Fact was stored without conflict
    memory.fact.conflict       — Fact conflicts with an existing value
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.memory.conversation_compressor import compress_session
from genus.memory.episode_store import EpisodeStore
from genus.memory.fact_store import ConflictDetectedError, SemanticFact, SemanticFactStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Topic constants
# ---------------------------------------------------------------------------

TOPIC_COMPRESS_REQUESTED = "memory.compress.requested"
TOPIC_COMPRESS_COMPLETED = "memory.compress.completed"
TOPIC_COMPRESS_FAILED = "memory.compress.failed"
TOPIC_FACT_UPSERT = "memory.fact.upsert"
TOPIC_FACT_STORED = "memory.fact.stored"
TOPIC_FACT_CONFLICT = "memory.fact.conflict"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class MemoryAgent(Agent):
    """Coordinates episodic compression and semantic fact storage.

    Args:
        message_bus:    The shared :class:`~genus.communication.message_bus.MessageBus`.
        episode_store:  Optional :class:`~genus.memory.episode_store.EpisodeStore`.
                        A default instance is created when not provided.
        fact_store:     Optional :class:`~genus.memory.fact_store.SemanticFactStore`.
                        A default instance is created when not provided.
        llm_router:     Optional :class:`~genus.llm.router.LLMRouter` for LLM-based
                        compression. Falls back to rule-based when absent.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        *,
        episode_store: Optional[EpisodeStore] = None,
        fact_store: Optional[SemanticFactStore] = None,
        llm_router: Optional[Any] = None,
    ) -> None:
        super().__init__(agent_id="MemoryAgent", name="MemoryAgent")
        self._bus = message_bus
        self._episodes = episode_store or EpisodeStore()
        self._facts = fact_store or SemanticFactStore()
        self._llm_router = llm_router
        self._subscriptions: list = []

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        for topic, callback in [
            (TOPIC_COMPRESS_REQUESTED, self._handle_compress_requested),
            (TOPIC_FACT_UPSERT, self._handle_fact_upsert),
        ]:
            subscriber_id = f"{self.id}:{topic}"
            self._bus.subscribe(topic, subscriber_id, callback)
            self._subscriptions.append((topic, subscriber_id))
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        for topic, subscriber_id in self._subscriptions:
            self._bus.unsubscribe(topic, subscriber_id)
        self._subscriptions.clear()
        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Any) -> None:
        """Not used directly — messages arrive via topic subscriptions."""

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_compress_requested(self, message: Message) -> None:
        """Handle ``memory.compress.requested`` — compress a session into an Episode."""
        payload = message.payload or {}
        session_id = payload.get("session_id")
        user_id = payload.get("user_id")
        messages = payload.get("messages", [])

        if not session_id or not user_id:
            logger.warning(
                "MemoryAgent: compress.requested missing session_id or user_id — skipping"
            )
            return

        try:
            episode = await compress_session(
                session_id=session_id,
                user_id=user_id,
                messages=messages,
                llm_router=self._llm_router,
            )
            self._episodes.append(episode)

            await self._bus.publish(Message(
                topic=TOPIC_COMPRESS_COMPLETED,
                payload={
                    "session_id": session_id,
                    "user_id": user_id,
                    "episode_id": episode.episode_id,
                    "source": episode.source,
                    "message_count": episode.message_count,
                },
                sender_id=self.id,
            ))

        except Exception as exc:  # noqa: BLE001
            logger.exception("MemoryAgent: compression failed for session %s", session_id)
            await self._bus.publish(Message(
                topic=TOPIC_COMPRESS_FAILED,
                payload={
                    "session_id": session_id,
                    "user_id": user_id,
                    "reason": str(exc),
                },
                sender_id=self.id,
            ))

    async def _handle_fact_upsert(self, message: Message) -> None:
        """Handle ``memory.fact.upsert`` — store or update a SemanticFact."""
        payload = message.payload or {}
        user_id = payload.get("user_id", "")
        key = payload.get("key", "")
        value = payload.get("value", "")
        source = payload.get("source", "")
        notes = payload.get("notes")

        if not user_id or not key:
            logger.warning("MemoryAgent: fact.upsert missing user_id or key — skipping")
            return

        fact = SemanticFact.create(
            user_id=user_id,
            key=key,
            value=value,
            source=source,
            notes=notes,
        )

        try:
            stored = self._facts.upsert(fact)
            await self._bus.publish(Message(
                topic=TOPIC_FACT_STORED,
                payload={
                    "user_id": user_id,
                    "key": stored.key,
                    "value": stored.value,
                    "fact_id": stored.fact_id,
                },
                sender_id=self.id,
            ))

        except ConflictDetectedError as exc:
            await self._bus.publish(Message(
                topic=TOPIC_FACT_CONFLICT,
                payload={
                    "user_id": user_id,
                    "key": exc.key,
                    "existing_value": exc.existing_value,
                    "new_value": exc.new_value,
                    "message": (
                        f"Du hattest '{exc.key}' bereits als '{exc.existing_value}' gespeichert — "
                        f"möchtest du das auf '{exc.new_value}' ändern?"
                    ),
                },
                sender_id=self.id,
            ))
