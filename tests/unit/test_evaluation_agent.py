"""
Unit tests for EvaluationAgent

Tests the meta-layer agent that evaluates runs and publishes evaluation events.

Covers:
- Subscription to dev.loop.completed and dev.loop.failed events
- Loading run data from RunJournal
- Saving evaluation artifacts
- Publishing meta.evaluation.completed events
- Handling edge cases (missing run_id, non-existent runs)
- Error logging when evaluation fails
"""

import tempfile
from pathlib import Path

import pytest

from genus.communication.message_bus import MessageBus
from genus.dev import events as dev_events
from genus.dev import topics as dev_topics
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.meta.agents.evaluation_agent import EvaluationAgent
from genus.meta import topics as meta_topics


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_store():
    """Create a temporary JsonlRunStore for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonlRunStore(base_dir=tmpdir)
        yield store


@pytest.fixture
def message_bus():
    """Create a MessageBus for testing."""
    return MessageBus()


@pytest.fixture
def evaluation_agent(message_bus, temp_store):
    """Create an EvaluationAgent for testing."""
    agent = EvaluationAgent(message_bus, "test-evaluator", temp_store)
    agent.start()
    yield agent
    agent.stop()


# ---------------------------------------------------------------------------
# Test Agent Subscription
# ---------------------------------------------------------------------------


class TestEvaluationAgentSubscription:
    """Test that EvaluationAgent subscribes to correct topics."""

    def test_agent_subscribes_to_completed_event(self, evaluation_agent):
        """Agent should subscribe to dev.loop.completed."""
        # Agent is already started via fixture
        assert evaluation_agent._started

    def test_agent_can_be_stopped(self, evaluation_agent):
        """Agent should be stoppable without errors."""
        evaluation_agent.stop()
        assert not evaluation_agent._started


# ---------------------------------------------------------------------------
# Test Evaluation on Completed Run
# ---------------------------------------------------------------------------


class TestEvaluationOnCompleted:
    """Test evaluation when dev.loop.completed is published."""

    @pytest.mark.asyncio
    async def test_evaluation_on_completed_run(self, message_bus, temp_store):
        """Should evaluate and save artifact on dev.loop.completed."""
        run_id = "test-run-1"

        # Create a run journal with test data
        journal = RunJournal(run_id, temp_store)
        journal.initialize(goal="Test goal")

        # Add a test report artifact
        journal.save_artifact(
            phase="test",
            artifact_type="test_report",
            payload={
                "exit_code": 0,
                "timed_out": False,
                "duration_s": 5.0,
                "stdout_summary": "All tests passed",
                "stderr_summary": "",
            },
        )

        # Create and start evaluation agent
        agent = EvaluationAgent(message_bus, "test-evaluator", temp_store)
        agent.start()

        # Track published messages
        published_messages = []

        async def capture_meta_event(msg):
            published_messages.append(msg)

        message_bus.subscribe(
            meta_topics.META_EVALUATION_COMPLETED,
            "test-listener",
            capture_meta_event,
        )

        # Publish dev.loop.completed event
        await message_bus.publish(
            dev_events.dev_loop_completed_message(
                run_id=run_id,
                sender_id="test-orchestrator",
                summary="Run completed successfully",
            )
        )

        # Check that evaluation artifact was saved
        eval_artifacts = journal.list_artifacts(artifact_type="evaluation")
        assert len(eval_artifacts) == 1

        # Load and verify artifact
        artifact_record = journal.load_artifact(eval_artifacts[0])
        assert artifact_record is not None
        assert artifact_record.artifact_type == "evaluation"
        assert artifact_record.payload["run_id"] == run_id
        assert artifact_record.payload["final_status"] == "completed"
        assert artifact_record.payload["score"] >= 0
        assert artifact_record.payload["score"] <= 100

        # Check that meta.evaluation.completed event was published
        assert len(published_messages) == 1
        assert published_messages[0].topic == meta_topics.META_EVALUATION_COMPLETED
        assert published_messages[0].payload["score"] >= 0

        agent.stop()


# ---------------------------------------------------------------------------
# Test Evaluation on Failed Run
# ---------------------------------------------------------------------------


class TestEvaluationOnFailed:
    """Test evaluation when dev.loop.failed is published."""

    @pytest.mark.asyncio
    async def test_evaluation_on_failed_run(self, message_bus, temp_store):
        """Should evaluate and save artifact on dev.loop.failed."""
        run_id = "test-run-2"

        # Create a run journal with test data
        journal = RunJournal(run_id, temp_store)
        journal.initialize(goal="Test goal")

        # Add a failing test report artifact
        journal.save_artifact(
            phase="test",
            artifact_type="test_report",
            payload={
                "exit_code": 1,
                "timed_out": False,
                "duration_s": 5.0,
                "stdout_summary": "",
                "stderr_summary": "AssertionError: test failed",
            },
        )

        # Create and start evaluation agent
        agent = EvaluationAgent(message_bus, "test-evaluator", temp_store)
        agent.start()

        # Publish dev.loop.failed event
        await message_bus.publish(
            dev_events.dev_loop_failed_message(
                run_id=run_id,
                sender_id="test-orchestrator",
                error="Tests failed",
            )
        )

        # Check that evaluation artifact was saved
        eval_artifacts = journal.list_artifacts(artifact_type="evaluation")
        assert len(eval_artifacts) == 1

        # Load and verify artifact
        artifact_record = journal.load_artifact(eval_artifacts[0])
        assert artifact_record is not None
        assert artifact_record.payload["final_status"] == "failed"
        assert artifact_record.payload["failure_class"] is not None
        assert artifact_record.payload["score"] < 100  # Failed runs have lower scores

        agent.stop()


# ---------------------------------------------------------------------------
# Test Iteration Counting
# ---------------------------------------------------------------------------


class TestIterationCounting:
    """Test that agent correctly counts iterations from journal."""

    @pytest.mark.asyncio
    async def test_counts_fix_iterations(self, message_bus, temp_store):
        """Should count fix iterations from journal events."""
        run_id = "test-run-3"

        # Create a run journal with multiple fix iterations
        journal = RunJournal(run_id, temp_store)
        journal.initialize(goal="Test goal")

        # Log multiple fix phase starts
        journal.log_phase_start("fix", phase_id="fix-1")
        journal.log_phase_start("fix", phase_id="fix-2")
        journal.log_phase_start("fix", phase_id="fix-3")

        # Add a test report
        journal.save_artifact(
            phase="test",
            artifact_type="test_report",
            payload={
                "exit_code": 0,
                "timed_out": False,
                "duration_s": 5.0,
            },
        )

        # Create and start evaluation agent
        agent = EvaluationAgent(message_bus, "test-evaluator", temp_store)
        agent.start()

        # Publish dev.loop.completed event
        await message_bus.publish(
            dev_events.dev_loop_completed_message(
                run_id=run_id,
                sender_id="test-orchestrator",
            )
        )

        # Load evaluation artifact
        eval_artifacts = journal.list_artifacts(artifact_type="evaluation")
        artifact_record = journal.load_artifact(eval_artifacts[0])

        # Should have detected 3 iterations
        # Score penalty: 100 - (3 * 10) = 70
        assert artifact_record.payload["score"] == 70

        agent.stop()


# ---------------------------------------------------------------------------
# Test Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_ignores_message_without_run_id(self, message_bus, temp_store):
        """Should ignore messages without run_id in metadata."""
        agent = EvaluationAgent(message_bus, "test-evaluator", temp_store)
        agent.start()

        # Publish event without run_id
        from genus.communication.message_bus import Message
        msg = Message(
            topic=dev_topics.DEV_LOOP_COMPLETED,
            payload={"summary": "Done"},
            sender_id="test",
            metadata={},  # No run_id
        )
        await message_bus.publish(msg)

        # Should not crash, just ignore
        agent.stop()

    @pytest.mark.asyncio
    async def test_ignores_nonexistent_run(self, message_bus, temp_store):
        """Should ignore messages for non-existent runs."""
        agent = EvaluationAgent(message_bus, "test-evaluator", temp_store)
        agent.start()

        # Publish event for non-existent run
        await message_bus.publish(
            dev_events.dev_loop_completed_message(
                run_id="nonexistent-run",
                sender_id="test-orchestrator",
            )
        )

        # Should not crash, just ignore
        agent.stop()

    @pytest.mark.asyncio
    async def test_handles_run_without_test_reports(self, message_bus, temp_store):
        """Should handle runs without test reports gracefully."""
        run_id = "test-run-4"

        # Create a minimal run journal without test reports
        journal = RunJournal(run_id, temp_store)
        journal.initialize(goal="Test goal")

        agent = EvaluationAgent(message_bus, "test-evaluator", temp_store)
        agent.start()

        # Publish dev.loop.completed event
        await message_bus.publish(
            dev_events.dev_loop_completed_message(
                run_id=run_id,
                sender_id="test-orchestrator",
            )
        )

        # Should still create evaluation artifact
        eval_artifacts = journal.list_artifacts(artifact_type="evaluation")
        assert len(eval_artifacts) == 1

        agent.stop()


# ---------------------------------------------------------------------------
# Test Journal Event Logging
# ---------------------------------------------------------------------------


class TestJournalEventLogging:
    """Test that agent logs evaluation events to journal."""

    @pytest.mark.asyncio
    async def test_logs_evaluation_completed_event(self, message_bus, temp_store):
        """Should log evaluation_completed event to journal."""
        run_id = "test-run-5"

        journal = RunJournal(run_id, temp_store)
        journal.initialize(goal="Test goal")

        journal.save_artifact(
            phase="test",
            artifact_type="test_report",
            payload={"exit_code": 0, "timed_out": False},
        )

        agent = EvaluationAgent(message_bus, "test-evaluator", temp_store)
        agent.start()

        await message_bus.publish(
            dev_events.dev_loop_completed_message(
                run_id=run_id,
                sender_id="test-orchestrator",
            )
        )

        # Check for evaluation_completed event in journal
        events = journal.get_events(
            phase="meta",
            event_type="evaluation_completed",
        )
        assert len(events) == 1
        assert events[0].summary.startswith("Evaluation completed")
        assert "score" in events[0].data

        agent.stop()

    @pytest.mark.asyncio
    async def test_logs_evaluation_failed_event(self, message_bus, temp_store):
        """Should log evaluation_failed event when evaluation raises exception."""
        from genus.meta.evaluator import RunEvaluator

        run_id = "test-run-6"

        journal = RunJournal(run_id, temp_store)
        journal.initialize(goal="Test goal")

        # Create a mock evaluator that always raises an exception
        class FailingEvaluator(RunEvaluator):
            def evaluate(self, inp):
                raise ValueError("Test error for logging")

        agent = EvaluationAgent(
            message_bus,
            "test-evaluator",
            temp_store,
            evaluator=FailingEvaluator(),
        )
        agent.start()

        await message_bus.publish(
            dev_events.dev_loop_completed_message(
                run_id=run_id,
                sender_id="test-orchestrator",
            )
        )

        # Check for evaluation_failed event in journal
        events = journal.get_events(
            phase="meta",
            event_type="evaluation_failed",
        )
        assert len(events) == 1
        assert "ValueError" in events[0].summary
        assert "error" in events[0].data
        assert "Test error for logging" in events[0].data["error"]

        agent.stop()
