"""
Unit tests for storage and learning mechanism.
"""
import pytest
from genus.storage.stores import MemoryStore, DecisionStore, FeedbackStore
from genus.storage.learning import LearningEngine


@pytest.fixture
async def memory_store():
    """Create a test memory store."""
    store = MemoryStore("sqlite+aiosqlite:///:memory:")
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
async def decision_store():
    """Create a test decision store."""
    store = DecisionStore("sqlite+aiosqlite:///:memory:")
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
async def feedback_store():
    """Create a test feedback store."""
    store = FeedbackStore("sqlite+aiosqlite:///:memory:")
    await store.initialize()
    yield store
    await store.close()


async def test_memory_store_operations(memory_store):
    """Test basic memory store operations."""
    # Set and get
    await memory_store.set("key1", "value1")
    value = await memory_store.get("key1")
    assert value == "value1"

    # Update
    await memory_store.set("key1", "value2")
    value = await memory_store.get("key1")
    assert value == "value2"

    # Get non-existent
    value = await memory_store.get("nonexistent")
    assert value is None

    # Delete
    await memory_store.delete("key1")
    value = await memory_store.get("key1")
    assert value is None


async def test_decision_store_operations(decision_store):
    """Test decision store operations."""
    # Store decision
    await decision_store.store_decision(
        decision_id="d1",
        context="test context",
        recommendation="test recommendation",
        confidence=0.8,
        reasoning="test reasoning",
    )

    # Get decision
    decision = await decision_store.get_decision("d1")
    assert decision is not None
    assert decision["decision_id"] == "d1"
    assert decision["context"] == "test context"
    assert decision["confidence"] == 0.8

    # Get all decisions
    decisions = await decision_store.get_all_decisions()
    assert len(decisions) == 1


async def test_feedback_store_operations(feedback_store):
    """Test feedback store operations."""
    # Store feedback
    await feedback_store.store_feedback(
        feedback_id="f1",
        decision_id="d1",
        score=0.9,
        label="success",
        comment="Great decision",
    )

    # Get feedback
    feedback = await feedback_store.get_feedback("f1")
    assert feedback is not None
    assert feedback["feedback_id"] == "f1"
    assert feedback["score"] == 0.9
    assert feedback["label"] == "success"

    # Get feedback for decision
    feedbacks = await feedback_store.get_feedback_for_decision("d1")
    assert len(feedbacks) == 1


async def test_learning_engine_no_feedback(decision_store, feedback_store):
    """Test learning engine with no feedback data."""
    learning_engine = LearningEngine(feedback_store, decision_store)

    # Analyze with no feedback
    analysis = await learning_engine.analyze_feedback()
    assert analysis["total_feedback"] == 0
    assert analysis["success_count"] == 0
    assert analysis["failure_count"] == 0

    # Adjust decision with no learning data
    rec, conf, info = await learning_engine.adjust_decision(
        "test context", "test recommendation", 0.8
    )
    assert rec == "test recommendation"
    assert conf == 0.8
    assert not info["learning_applied"]


async def test_learning_engine_with_feedback(decision_store, feedback_store):
    """Test learning engine with feedback data."""
    learning_engine = LearningEngine(feedback_store, decision_store)

    # Create a decision
    await decision_store.store_decision(
        decision_id="d1",
        context="deploy application to production",
        recommendation="proceed with deployment",
        confidence=0.7,
    )

    # Add successful feedback
    await feedback_store.store_feedback(
        feedback_id="f1", decision_id="d1", score=0.9, label="success"
    )

    # Analyze feedback
    analysis = await learning_engine.analyze_feedback()
    assert analysis["total_feedback"] == 1
    assert analysis["success_count"] == 1
    assert analysis["failure_count"] == 0
    assert len(analysis["patterns"]) > 0

    # Make similar decision - should have higher confidence
    rec, conf, info = await learning_engine.adjust_decision(
        "deploy application to production", "proceed with deployment", 0.7
    )
    assert info["learning_applied"]
    assert conf > 0.7  # Confidence should increase based on past success


async def test_learning_engine_pattern_weight_increase(decision_store, feedback_store):
    """Test that successful patterns increase weight."""
    learning_engine = LearningEngine(feedback_store, decision_store)

    # Create multiple successful decisions with same pattern
    for i in range(5):
        decision_id = f"d{i}"
        await decision_store.store_decision(
            decision_id=decision_id,
            context="review code changes",
            recommendation="approve changes",
            confidence=0.75,
        )
        await feedback_store.store_feedback(
            feedback_id=f"f{i}",
            decision_id=decision_id,
            score=0.95,
            label="success",
        )

    # Adjust decision with same pattern
    rec, conf, info = await learning_engine.adjust_decision(
        "review code changes", "approve changes", 0.75
    )

    assert info["learning_applied"]
    assert info["pattern_success_rate"] > 0.9
    assert conf > 0.75  # Confidence should increase


async def test_learning_engine_pattern_weight_decrease(decision_store, feedback_store):
    """Test that failed patterns decrease weight."""
    learning_engine = LearningEngine(feedback_store, decision_store)

    # Create multiple failed decisions with same pattern
    for i in range(5):
        decision_id = f"d{i}"
        await decision_store.store_decision(
            decision_id=decision_id,
            context="deploy without testing",
            recommendation="proceed immediately",
            confidence=0.8,
        )
        await feedback_store.store_feedback(
            feedback_id=f"f{i}",
            decision_id=decision_id,
            score=0.2,
            label="failure",
        )

    # Adjust decision with same pattern
    rec, conf, info = await learning_engine.adjust_decision(
        "deploy without testing", "proceed immediately", 0.8
    )

    assert info["learning_applied"]
    assert info["pattern_success_rate"] < 0.5
    assert conf < 0.8  # Confidence should decrease


async def test_learning_engine_cache_invalidation(decision_store, feedback_store):
    """Test that cache invalidation works correctly."""
    learning_engine = LearningEngine(feedback_store, decision_store)

    # Initial analysis
    analysis1 = await learning_engine.analyze_feedback()
    assert analysis1["total_feedback"] == 0

    # Add feedback
    await decision_store.store_decision(
        decision_id="d1",
        context="test",
        recommendation="test",
        confidence=0.5,
    )
    await feedback_store.store_feedback(
        feedback_id="f1", decision_id="d1", score=0.8, label="success"
    )

    # Invalidate cache
    learning_engine.invalidate_cache()

    # Re-analyze should show new feedback
    analysis2 = await learning_engine.analyze_feedback()
    assert analysis2["total_feedback"] == 1
