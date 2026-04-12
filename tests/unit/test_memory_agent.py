"""
Tests for genus.memory.memory_agent — Phase 14b
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from genus.communication.message_bus import Message, MessageBus
from genus.memory.episode_store import Episode, EpisodeStore
from genus.memory.fact_store import ConflictDetectedError, SemanticFact, SemanticFactStore
from genus.memory.memory_agent import (
    MemoryAgent,
    TOPIC_COMPRESS_COMPLETED,
    TOPIC_COMPRESS_FAILED,
    TOPIC_COMPRESS_REQUESTED,
    TOPIC_FACT_CONFLICT,
    TOPIC_FACT_STORED,
    TOPIC_FACT_UPSERT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(bus: MessageBus, episode_store=None, fact_store=None, llm_router=None):
    return MemoryAgent(
        bus,
        episode_store=episode_store,
        fact_store=fact_store,
        llm_router=llm_router,
    )


def _compress_msg(session_id: str, user_id: str, messages=None) -> Message:
    return Message(
        topic=TOPIC_COMPRESS_REQUESTED,
        payload={
            "session_id": session_id,
            "user_id": user_id,
            "messages": messages or [{"role": "user", "content": "Hallo"}],
        },
        sender_id="NightScheduler",
    )


def _fact_msg(user_id: str, key: str, value: str, source: str = "", notes=None) -> Message:
    return Message(
        topic=TOPIC_FACT_UPSERT,
        payload={
            "user_id": user_id,
            "key": key,
            "value": value,
            "source": source,
            "notes": notes,
        },
        sender_id="ConversationAgent",
    )


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

class TestMemoryAgentSubscriptions:
    async def test_subscribed_to_compress_requested_after_start(self):
        bus = MessageBus()
        agent = _make_agent(bus)
        await agent.start()
        # Verify subscription exists by checking that a message gets delivered
        published = []
        bus.subscribe(TOPIC_COMPRESS_COMPLETED, "test-spy", lambda m: published.append(m))
        bus.subscribe(TOPIC_COMPRESS_FAILED, "test-spy-fail", lambda m: published.append(m))

        msg = _compress_msg("s1", "alice")
        await bus.publish(msg)
        await asyncio.sleep(0.05)
        assert len(published) >= 1
        await agent.stop()

    async def test_subscribed_to_fact_upsert_after_start(self):
        bus = MessageBus()
        agent = _make_agent(bus)
        await agent.start()

        published = []
        bus.subscribe(TOPIC_FACT_STORED, "spy", lambda m: published.append(m))

        await bus.publish(_fact_msg("alice", "sprache", "deutsch"))
        await asyncio.sleep(0.05)
        assert len(published) == 1
        await agent.stop()


# ---------------------------------------------------------------------------
# compress.requested → compress.completed
# ---------------------------------------------------------------------------

class TestCompressRequested:
    async def test_compress_completed_published(self):
        bus = MessageBus()
        agent = _make_agent(bus)
        await agent.start()

        completed = []
        bus.subscribe(TOPIC_COMPRESS_COMPLETED, "spy", lambda m: completed.append(m))

        await bus.publish(_compress_msg("sess-1", "alice"))
        await asyncio.sleep(0.05)

        assert len(completed) == 1
        payload = completed[0].payload
        assert payload["session_id"] == "sess-1"
        assert payload["user_id"] == "alice"
        assert "episode_id" in payload
        await agent.stop()

    async def test_compress_requested_without_session_id_no_event(self):
        bus = MessageBus()
        agent = _make_agent(bus)
        await agent.start()

        published = []
        bus.subscribe(TOPIC_COMPRESS_COMPLETED, "spy", lambda m: published.append(m))
        bus.subscribe(TOPIC_COMPRESS_FAILED, "spy2", lambda m: published.append(m))

        # Missing session_id
        await bus.publish(Message(
            topic=TOPIC_COMPRESS_REQUESTED,
            payload={"user_id": "alice", "messages": []},
            sender_id="test",
        ))
        await asyncio.sleep(0.05)
        assert published == []
        await agent.stop()

    async def test_compress_requested_without_user_id_no_event(self):
        bus = MessageBus()
        agent = _make_agent(bus)
        await agent.start()

        published = []
        bus.subscribe(TOPIC_COMPRESS_COMPLETED, "spy", lambda m: published.append(m))
        bus.subscribe(TOPIC_COMPRESS_FAILED, "spy2", lambda m: published.append(m))

        await bus.publish(Message(
            topic=TOPIC_COMPRESS_REQUESTED,
            payload={"session_id": "s1", "messages": []},
            sender_id="test",
        ))
        await asyncio.sleep(0.05)
        assert published == []
        await agent.stop()


# ---------------------------------------------------------------------------
# fact.upsert → fact.stored
# ---------------------------------------------------------------------------

class TestFactUpsert:
    async def test_fact_stored_published(self):
        bus = MessageBus()
        agent = _make_agent(bus)
        await agent.start()

        stored = []
        bus.subscribe(TOPIC_FACT_STORED, "spy", lambda m: stored.append(m))

        await bus.publish(_fact_msg("alice", "sprache", "deutsch"))
        await asyncio.sleep(0.05)

        assert len(stored) == 1
        assert stored[0].payload["key"] == "sprache"
        assert stored[0].payload["value"] == "deutsch"
        await agent.stop()

    async def test_fact_conflict_published_on_different_value(self):
        bus = MessageBus()
        agent = _make_agent(bus)
        await agent.start()

        # Store initial fact
        await bus.publish(_fact_msg("alice", "redis", "nein"))
        await asyncio.sleep(0.05)

        conflicts = []
        bus.subscribe(TOPIC_FACT_CONFLICT, "spy", lambda m: conflicts.append(m))

        # Try to store different value
        await bus.publish(_fact_msg("alice", "redis", "ja"))
        await asyncio.sleep(0.05)

        assert len(conflicts) == 1
        payload = conflicts[0].payload
        assert payload["existing_value"] == "nein"
        assert payload["new_value"] == "ja"
        assert "message" in payload
        assert payload["message"]  # non-empty German question
        await agent.stop()

    async def test_fact_conflict_payload_has_required_fields(self):
        bus = MessageBus()
        agent = _make_agent(bus)
        await agent.start()

        await bus.publish(_fact_msg("bob", "color", "blue"))
        await asyncio.sleep(0.05)

        conflicts = []
        bus.subscribe(TOPIC_FACT_CONFLICT, "spy", lambda m: conflicts.append(m))
        await bus.publish(_fact_msg("bob", "color", "red"))
        await asyncio.sleep(0.05)

        assert len(conflicts) == 1
        payload = conflicts[0].payload
        assert "existing_value" in payload
        assert "new_value" in payload
        assert "message" in payload
        await agent.stop()


# ---------------------------------------------------------------------------
# After stop() — no events
# ---------------------------------------------------------------------------

class TestAfterStop:
    async def test_no_events_after_stop(self):
        bus = MessageBus()
        agent = _make_agent(bus)
        await agent.start()
        await agent.stop()

        published = []
        bus.subscribe(TOPIC_COMPRESS_COMPLETED, "spy", lambda m: published.append(m))

        await bus.publish(_compress_msg("sess-1", "alice"))
        await asyncio.sleep(0.05)
        # Agent is stopped — should not publish
        assert published == []
