"""Unit tests for SystemStateTracker."""

import pytest
from datetime import datetime, timedelta
from genus.core.system_state import SystemState, SystemStateTracker


class TestSystemStateTracker:
    """Test system state tracking and health monitoring."""

    def test_initial_state_is_healthy(self):
        """Test initial system state is healthy."""
        tracker = SystemStateTracker()
        assert tracker.get_system_state() == SystemState.HEALTHY

    def test_record_agent_error(self):
        """Test recording agent errors."""
        tracker = SystemStateTracker()
        tracker.record_agent_error("test_agent", "Test error")
        report = tracker.get_health_report()
        assert "test_agent" in report["recent_errors"]["agents"]

    def test_record_pipeline_failure(self):
        """Test recording pipeline failures."""
        tracker = SystemStateTracker()
        tracker.record_pipeline_failure("test_pipeline", "Pipeline failed")
        report = tracker.get_health_report()
        assert len(report["recent_errors"]["pipelines"]) == 1

    def test_record_message_bus_error(self):
        """Test recording message bus errors."""
        tracker = SystemStateTracker()
        tracker.record_message_bus_error("test_topic", "Bus error")
        report = tracker.get_health_report()
        assert len(report["recent_errors"]["message_bus"]) == 1

    def test_update_agent_state(self):
        """Test updating agent state."""
        tracker = SystemStateTracker()
        now = datetime.utcnow()
        tracker.update_agent_state("test_agent", "running", now)
        assert tracker.agent_states["test_agent"] == "running"
        assert tracker.last_event_time["test_agent"] == now

    def test_failed_agent_causes_failing_state(self):
        """Test that failed agent causes system to be failing."""
        tracker = SystemStateTracker()
        tracker.update_agent_state("test_agent", "failed")
        assert tracker.get_system_state() == SystemState.FAILING

    def test_many_recent_errors_cause_failing_state(self):
        """Test that many recent errors cause failing state."""
        tracker = SystemStateTracker()
        # Record 10+ recent errors
        for i in range(10):
            tracker.record_agent_error("test_agent", f"Error {i}")
        assert tracker.get_system_state() == SystemState.FAILING

    def test_few_recent_errors_cause_degraded_state(self):
        """Test that few recent errors cause degraded state."""
        tracker = SystemStateTracker()
        # Record 3-9 recent errors
        for i in range(5):
            tracker.record_agent_error("test_agent", f"Error {i}")
        assert tracker.get_system_state() == SystemState.DEGRADED

    def test_health_report_structure(self):
        """Test health report contains all required fields."""
        tracker = SystemStateTracker()
        tracker.update_agent_state("agent1", "running", datetime.utcnow())
        tracker.record_agent_error("agent1", "Test error")

        report = tracker.get_health_report()

        assert "system_state" in report
        assert "timestamp" in report
        assert "agent_states" in report
        assert "recent_errors" in report
        assert "last_successful_run" in report
        assert "error_counts" in report

    def test_error_count_limits(self):
        """Test that error counts are limited to prevent memory issues."""
        tracker = SystemStateTracker()

        # Record 150 errors (should keep only last 100)
        for i in range(150):
            tracker.record_agent_error("test_agent", f"Error {i}")

        assert len(tracker.agent_errors["test_agent"]) == 100
