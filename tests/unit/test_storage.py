"""Unit tests for storage modules."""

import pytest
from genus.storage.memory_store import MemoryStore
from genus.storage.decision_store import DecisionStore
from genus.storage.feedback_store import FeedbackStore


class TestMemoryStore:
    """Test MemoryStore functionality."""

    async def test_store_and_retrieve(self):
        """Test storing and retrieving values."""
        store = MemoryStore()
        await store.store("key1", "value1")
        value = await store.retrieve("key1")
        assert value == "value1"

    async def test_retrieve_nonexistent(self):
        """Test retrieving non-existent key returns None."""
        store = MemoryStore()
        value = await store.retrieve("nonexistent")
        assert value is None

    async def test_delete(self):
        """Test deleting values."""
        store = MemoryStore()
        await store.store("key1", "value1")
        assert await store.delete("key1") is True
        assert await store.retrieve("key1") is None

    async def test_delete_nonexistent(self):
        """Test deleting non-existent key returns False."""
        store = MemoryStore()
        assert await store.delete("nonexistent") is False

    async def test_list_keys(self):
        """Test listing all keys."""
        store = MemoryStore()
        await store.store("key1", "value1")
        await store.store("key2", "value2")
        keys = await store.list_keys()
        assert "key1" in keys
        assert "key2" in keys

    async def test_list_keys_with_prefix(self):
        """Test listing keys with prefix filter."""
        store = MemoryStore()
        await store.store("user:1", "data1")
        await store.store("user:2", "data2")
        await store.store("post:1", "data3")

        keys = await store.list_keys(prefix="user:")
        assert len(keys) == 2
        assert all(k.startswith("user:") for k in keys)


class TestDecisionStore:
    """Test DecisionStore functionality."""

    async def test_record_and_get_decision(self):
        """Test recording and retrieving decisions."""
        store = DecisionStore()
        await store.record_decision("dec1", "agent1", "approval", {"action": "approve"})

        decision = await store.get_decision("dec1")
        assert decision is not None
        assert decision["decision_id"] == "dec1"
        assert decision["agent"] == "agent1"

    async def test_update_outcome(self):
        """Test updating decision outcome."""
        store = DecisionStore()
        await store.record_decision("dec1", "agent1", "approval", {"action": "approve"})
        await store.update_outcome("dec1", "success")

        decision = await store.get_decision("dec1")
        assert decision["outcome"] == "success"

    async def test_list_decisions(self):
        """Test listing decisions."""
        store = DecisionStore()
        await store.record_decision("dec1", "agent1", "approval", {})
        await store.record_decision("dec2", "agent2", "review", {})

        decisions = await store.list_decisions()
        assert len(decisions) == 2

    async def test_list_decisions_by_agent(self):
        """Test filtering decisions by agent."""
        store = DecisionStore()
        await store.record_decision("dec1", "agent1", "approval", {})
        await store.record_decision("dec2", "agent2", "review", {})

        decisions = await store.list_decisions(agent="agent1")
        assert len(decisions) == 1
        assert decisions[0]["agent"] == "agent1"


class TestFeedbackStore:
    """Test FeedbackStore functionality."""

    async def test_record_and_get_feedback(self):
        """Test recording and retrieving feedback."""
        store = FeedbackStore()
        await store.record_feedback("fb1", "dec1", 5, "Great!")

        feedback = await store.get_feedback("fb1")
        assert feedback is not None
        assert feedback["rating"] == 5
        assert feedback["comment"] == "Great!"

    async def test_invalid_rating(self):
        """Test that invalid ratings raise ValueError."""
        store = FeedbackStore()
        with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
            await store.record_feedback("fb1", "dec1", 6)

    async def test_list_feedback(self):
        """Test listing feedback."""
        store = FeedbackStore()
        await store.record_feedback("fb1", "dec1", 5)
        await store.record_feedback("fb2", "dec2", 3)

        feedback_list = await store.list_feedback()
        assert len(feedback_list) == 2

    async def test_list_feedback_by_decision(self):
        """Test filtering feedback by decision."""
        store = FeedbackStore()
        await store.record_feedback("fb1", "dec1", 5)
        await store.record_feedback("fb2", "dec1", 4)
        await store.record_feedback("fb3", "dec2", 3)

        feedback_list = await store.list_feedback(decision_id="dec1")
        assert len(feedback_list) == 2

    async def test_get_average_rating(self):
        """Test calculating average rating."""
        store = FeedbackStore()
        await store.record_feedback("fb1", "dec1", 5)
        await store.record_feedback("fb2", "dec1", 3)

        avg = await store.get_average_rating(decision_id="dec1")
        assert avg == 4.0

    async def test_get_average_rating_no_feedback(self):
        """Test average rating with no feedback returns None."""
        store = FeedbackStore()
        avg = await store.get_average_rating()
        assert avg is None
