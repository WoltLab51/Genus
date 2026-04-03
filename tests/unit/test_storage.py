"""Unit tests for storage classes."""

import pytest

from genus.storage.memory_store import MemoryStore
from genus.storage.decision_store import DecisionStore
from genus.storage.feedback_store import FeedbackStore


# MemoryStore tests
async def test_memory_store_store():
    """Test storing memories."""
    store = MemoryStore()

    memory_id = await store.store({"data": "test"})

    assert memory_id == "0"
    assert store.count() == 1


async def test_memory_store_retrieve():
    """Test retrieving memories."""
    store = MemoryStore()

    memory_id = await store.store({"data": "test", "type": "observation"})
    memory = await store.retrieve(memory_id)

    assert memory is not None
    assert memory["data"] == "test"
    assert memory["type"] == "observation"
    assert "timestamp" in memory


async def test_memory_store_query():
    """Test querying memories."""
    store = MemoryStore()

    await store.store({"data": "test1", "type": "observation"})
    await store.store({"data": "test2", "type": "analysis"})
    await store.store({"data": "test3", "type": "observation"})

    results = await store.query({"type": "observation"})

    assert len(results) == 2
    assert results[0]["type"] == "observation"
    assert results[1]["type"] == "observation"


async def test_memory_store_clear():
    """Test clearing memories."""
    store = MemoryStore()

    await store.store({"data": "test"})
    await store.clear()

    assert store.count() == 0


# DecisionStore tests
async def test_decision_store_store():
    """Test storing decisions."""
    store = DecisionStore()

    decision_id = await store.store_decision(
        agent="TestAgent",
        decision="Test decision",
        context={"data": "context"},
        reasoning="Test reasoning"
    )

    assert decision_id == "0"
    assert store.count() == 1


async def test_decision_store_get():
    """Test getting decisions."""
    store = DecisionStore()

    decision_id = await store.store_decision(
        agent="TestAgent",
        decision="Test decision",
        context={"data": "context"}
    )

    decision = await store.get_decision(decision_id)

    assert decision is not None
    assert decision["agent"] == "TestAgent"
    assert decision["decision"] == "Test decision"
    assert "timestamp" in decision


async def test_decision_store_update_outcome():
    """Test updating decision outcomes."""
    store = DecisionStore()

    decision_id = await store.store_decision(
        agent="TestAgent",
        decision="Test decision",
        context={}
    )

    result = await store.update_outcome(decision_id, {"success": True})

    assert result is True

    decision = await store.get_decision(decision_id)
    assert decision["outcome"] == {"success": True}


async def test_decision_store_query():
    """Test querying decisions."""
    store = DecisionStore()

    await store.store_decision("Agent1", "Decision 1", {})
    await store.store_decision("Agent2", "Decision 2", {})
    await store.store_decision("Agent1", "Decision 3", {})

    results = await store.query_decisions(agent="Agent1")

    assert len(results) == 2
    assert results[0]["agent"] == "Agent1"
    assert results[1]["agent"] == "Agent1"


# FeedbackStore tests
async def test_feedback_store_store():
    """Test storing feedback."""
    store = FeedbackStore()

    feedback_id = await store.store_feedback(
        target="Agent1",
        feedback_type="positive",
        content={"rating": 5},
        source="user"
    )

    assert feedback_id == "0"
    assert store.count() == 1


async def test_feedback_store_get():
    """Test getting feedback."""
    store = FeedbackStore()

    feedback_id = await store.store_feedback(
        target="Agent1",
        feedback_type="positive",
        content={"rating": 5}
    )

    feedback = await store.get_feedback(feedback_id)

    assert feedback is not None
    assert feedback["target"] == "Agent1"
    assert feedback["type"] == "positive"
    assert "timestamp" in feedback


async def test_feedback_store_query():
    """Test querying feedback."""
    store = FeedbackStore()

    await store.store_feedback("Agent1", "positive", {})
    await store.store_feedback("Agent2", "negative", {})
    await store.store_feedback("Agent1", "positive", {})

    results = await store.query_feedback(target="Agent1", feedback_type="positive")

    assert len(results) == 2
    assert results[0]["target"] == "Agent1"
    assert results[0]["type"] == "positive"
