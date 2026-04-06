"""
Unit tests for CLI report generator.
"""

import pytest
from pathlib import Path
from genus.cli.report import generate_report, _determine_status
from genus.memory.store_jsonl import JsonlRunStore
from genus.memory.models import RunHeader, JournalEvent, ArtifactRecord


@pytest.fixture
def temp_store(tmp_path):
    """Create a temporary run store."""
    return JsonlRunStore(base_dir=str(tmp_path))


@pytest.fixture
def sample_run(temp_store):
    """Create a sample run with events and artifacts."""
    run_id = "2026-04-06T12-00-00Z__test-run__abc123"

    # Create header
    header = RunHeader(
        run_id=run_id,
        created_at="2026-04-06T12:00:00Z",
        goal="Test goal for sample run",
        repo_id="WoltLab51/Genus",
        workspace_root="/tmp/workspace",
        meta={"test": True},
    )
    temp_store.save_header(header)

    # Add some events
    events = [
        JournalEvent(
            ts="2026-04-06T12:00:01Z",
            run_id=run_id,
            phase="orchestrator",
            event_type="started",
            summary="Dev loop started",
        ),
        JournalEvent(
            ts="2026-04-06T12:00:02Z",
            run_id=run_id,
            phase="plan",
            event_type="started",
            summary="Planning phase started",
        ),
        JournalEvent(
            ts="2026-04-06T12:00:10Z",
            run_id=run_id,
            phase="plan",
            event_type="completed",
            summary="Planning completed",
        ),
        JournalEvent(
            ts="2026-04-06T12:00:15Z",
            run_id=run_id,
            phase="implement",
            event_type="completed",
            summary="Implementation completed",
            data={"iteration": 0, "commit_sha": "abc123"},
        ),
        JournalEvent(
            ts="2026-04-06T12:00:20Z",
            run_id=run_id,
            phase="test",
            event_type="completed",
            summary="Tests completed",
        ),
        JournalEvent(
            ts="2026-04-06T12:00:30Z",
            run_id=run_id,
            phase="orchestrator",
            event_type="completed",
            summary="Dev loop completed successfully",
        ),
    ]

    for event in events:
        temp_store.append_event(event)

    # Add test report artifact
    test_report = ArtifactRecord(
        run_id=run_id,
        phase="test",
        artifact_type="test_report",
        payload={
            "exit_code": 0,
            "duration": 5.2,
            "timed_out": False,
            "stdout": "All tests passed",
            "stderr": "",
        },
        saved_at="2026-04-06T12:00:20Z",
    )
    temp_store.save_artifact(test_report)

    # Add evaluation artifact
    evaluation = ArtifactRecord(
        run_id=run_id,
        phase="evaluation",
        artifact_type="evaluation",
        payload={
            "score": 0.95,
            "failure_class": None,
            "root_cause_hint": None,
            "recommendations": ["Great job!", "Consider adding more tests"],
        },
        saved_at="2026-04-06T12:00:35Z",
    )
    temp_store.save_artifact(evaluation)

    # Add strategy decision artifact
    strategy = ArtifactRecord(
        run_id=run_id,
        phase="plan",
        artifact_type="strategy_decision",
        payload={
            "selected_playbook": "standard_tdd",
            "reason": "Simple feature with clear requirements",
            "candidates": ["standard_tdd", "exploratory", "refactor_first"],
        },
        saved_at="2026-04-06T12:00:05Z",
    )
    temp_store.save_artifact(strategy)

    return run_id, temp_store


def test_generate_report_text_format(sample_run):
    """Test report generation in text format."""
    run_id, store = sample_run

    report = generate_report(run_id, store, format="text")

    # Verify key sections are present
    assert "GENUS Run Report" in report
    assert run_id in report
    assert "Test goal for sample run" in report
    assert "WoltLab51/Genus" in report
    assert "completed" in report.lower()
    assert "Timeline" in report
    assert "Iterations" in report
    assert "Test Results" in report
    assert "Evaluation" in report
    assert "Strategy Decisions" in report


def test_generate_report_markdown_format(sample_run):
    """Test report generation in markdown format."""
    run_id, store = sample_run

    report = generate_report(run_id, store, format="md")

    # Verify markdown structure
    assert "# GENUS Run Report" in report
    assert "## Overview" in report
    assert "## Timeline" in report
    assert "## Iterations" in report
    assert "## Test Results" in report
    assert "## Evaluation" in report
    assert "## Strategy Decisions" in report
    assert run_id in report
    assert "Test goal for sample run" in report


def test_generate_report_nonexistent_run(temp_store):
    """Test report generation for a nonexistent run."""
    report = generate_report("nonexistent-run", temp_store, format="text")

    assert "Error" in report
    assert "not found" in report


def test_determine_status_completed():
    """Test status determination for completed runs."""
    events = [
        JournalEvent(
            ts="2026-04-06T12:00:00Z",
            run_id="test",
            phase="orchestrator",
            event_type="completed",
            summary="Completed",
        ),
    ]

    status = _determine_status(events)
    assert status == "completed"


def test_determine_status_failed():
    """Test status determination for failed runs."""
    events = [
        JournalEvent(
            ts="2026-04-06T12:00:00Z",
            run_id="test",
            phase="orchestrator",
            event_type="failed",
            summary="Failed",
        ),
    ]

    status = _determine_status(events)
    assert status == "failed"


def test_determine_status_in_progress():
    """Test status determination for in-progress runs."""
    events = [
        JournalEvent(
            ts="2026-04-06T12:00:00Z",
            run_id="test",
            phase="plan",
            event_type="started",
            summary="Planning",
        ),
    ]

    status = _determine_status(events)
    assert status == "in_progress"


def test_determine_status_empty():
    """Test status determination with no events."""
    status = _determine_status([])
    assert status == "unknown"


def test_report_includes_test_results(sample_run):
    """Test that report includes test results."""
    run_id, store = sample_run

    report = generate_report(run_id, store, format="text")

    assert "Test Results" in report
    assert "Exit Code: 0" in report
    assert "Duration:" in report


def test_report_includes_evaluation(sample_run):
    """Test that report includes evaluation."""
    run_id, store = sample_run

    report = generate_report(run_id, store, format="text")

    assert "Evaluation" in report
    assert "Score:" in report
    assert "0.95" in report
    assert "Great job!" in report


def test_report_includes_strategy(sample_run):
    """Test that report includes strategy decisions."""
    run_id, store = sample_run

    report = generate_report(run_id, store, format="text")

    assert "Strategy Decisions" in report
    assert "standard_tdd" in report
    assert "Simple feature with clear requirements" in report


def test_report_includes_iterations(sample_run):
    """Test that report includes iteration information."""
    run_id, store = sample_run

    report = generate_report(run_id, store, format="text")

    assert "Iterations" in report
    assert "Iteration 0" in report
    assert "abc123" in report
