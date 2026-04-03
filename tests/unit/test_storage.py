"""Unit tests for storage (MemoryStore and FeedbackStore)."""
import pytest
from genus.storage import MemoryStore, FeedbackStore


@pytest.fixture
async def memory_store():
    """Create a memory store for testing."""
    store = MemoryStore("sqlite+aiosqlite:///:memory:")
    await store.init_db()
    yield store
    await store.close()


@pytest.fixture
async def feedback_store():
    """Create a feedback store for testing."""
    store = FeedbackStore("sqlite+aiosqlite:///:memory:")
    await store.init_db()
    yield store
    await store.close()


async def test_store_decision(memory_store):
    """Test storing a decision."""
    decision_id = await memory_store.store_decision(
        agent_id="test-agent",
        decision_type="test_decision",
        input_data={"input": "test"},
        output_data={"output": "result"}
    )

    assert decision_id is not None
    assert isinstance(decision_id, str)


async def test_get_decision(memory_store):
    """Test retrieving a decision."""
    decision_id = await memory_store.store_decision(
        agent_id="test-agent",
        decision_type="test_decision",
        input_data={"input": "test"}
    )

    decision = await memory_store.get_decision(decision_id)

    assert decision is not None
    assert decision.id == decision_id
    assert decision.agent_id == "test-agent"
    assert decision.decision_type == "test_decision"


async def test_get_decisions_with_filters(memory_store):
    """Test retrieving decisions with filters."""
    await memory_store.store_decision(
        agent_id="agent-1",
        decision_type="type-a"
    )
    await memory_store.store_decision(
        agent_id="agent-2",
        decision_type="type-b"
    )
    await memory_store.store_decision(
        agent_id="agent-1",
        decision_type="type-b"
    )

    # Filter by agent
    agent1_decisions = await memory_store.get_decisions(agent_id="agent-1")
    assert len(agent1_decisions) == 2

    # Filter by type
    typeb_decisions = await memory_store.get_decisions(decision_type="type-b")
    assert len(typeb_decisions) == 2

    # Filter by both
    specific_decisions = await memory_store.get_decisions(
        agent_id="agent-1",
        decision_type="type-b"
    )
    assert len(specific_decisions) == 1


async def test_store_feedback(memory_store, feedback_store):
    """Test storing feedback."""
    # First create a decision
    decision_id = await memory_store.store_decision(
        agent_id="test-agent",
        decision_type="test_decision"
    )

    # Store feedback
    feedback_id = await feedback_store.store_feedback(
        decision_id=decision_id,
        score=1.0,
        label="success",
        notes="Great job!"
    )

    assert feedback_id is not None
    assert isinstance(feedback_id, str)


async def test_get_feedback(memory_store, feedback_store):
    """Test retrieving feedback."""
    decision_id = await memory_store.store_decision(
        agent_id="test-agent",
        decision_type="test_decision"
    )

    feedback_id = await feedback_store.store_feedback(
        decision_id=decision_id,
        score=0.5,
        label="neutral",
        notes="Could be better"
    )

    feedback = await feedback_store.get_feedback(feedback_id)

    assert feedback is not None
    assert feedback.id == feedback_id
    assert feedback.decision_id == decision_id
    assert feedback.score == 0.5
    assert feedback.label == "neutral"
    assert feedback.notes == "Could be better"


async def test_get_feedback_for_decision(memory_store, feedback_store):
    """Test retrieving all feedback for a decision."""
    decision_id = await memory_store.store_decision(
        agent_id="test-agent",
        decision_type="test_decision"
    )

    # Add multiple feedback entries
    await feedback_store.store_feedback(
        decision_id=decision_id,
        score=1.0,
        label="success"
    )
    await feedback_store.store_feedback(
        decision_id=decision_id,
        score=0.5,
        label="neutral"
    )

    feedbacks = await feedback_store.get_feedback_for_decision(decision_id)

    assert len(feedbacks) == 2


async def test_feedback_score_validation(memory_store, feedback_store):
    """Test feedback score validation."""
    decision_id = await memory_store.store_decision(
        agent_id="test-agent",
        decision_type="test_decision"
    )

    # Invalid score (too high)
    with pytest.raises(ValueError):
        await feedback_store.store_feedback(
            decision_id=decision_id,
            score=1.5,
            label="success"
        )

    # Invalid score (too low)
    with pytest.raises(ValueError):
        await feedback_store.store_feedback(
            decision_id=decision_id,
            score=-1.5,
            label="failure"
        )


async def test_feedback_label_validation(memory_store, feedback_store):
    """Test feedback label validation."""
    decision_id = await memory_store.store_decision(
        agent_id="test-agent",
        decision_type="test_decision"
    )

    # Invalid label
    with pytest.raises(ValueError):
        await feedback_store.store_feedback(
            decision_id=decision_id,
            score=0.5,
            label="invalid_label"
        )
