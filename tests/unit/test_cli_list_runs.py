"""
Unit tests for CLI list-runs command.
"""

import pytest
from pathlib import Path
from io import StringIO
import sys

from genus.cli.commands import cmd_list_runs
from genus.cli.config import CliConfig
from genus.memory.store_jsonl import JsonlRunStore
from genus.memory.models import RunHeader, JournalEvent, ArtifactRecord


@pytest.fixture
def temp_store(tmp_path):
    """Create a temporary run store."""
    return JsonlRunStore(base_dir=str(tmp_path))


@pytest.fixture
def sample_runs(temp_store):
    """Create sample runs with different statuses."""
    runs = []

    # Run 1: Completed with high score
    run_id_1 = "2026-04-06T12-00-00Z__test-run-1__abc123"
    header_1 = RunHeader(
        run_id=run_id_1,
        created_at="2026-04-06T12:00:00Z",
        goal="Implement user authentication feature",
        repo_id="WoltLab51/Genus",
        workspace_root="/tmp/workspace1",
    )
    temp_store.save_header(header_1)

    # Add completed event
    temp_store.append_event(JournalEvent(
        ts="2026-04-06T12:10:00Z",
        run_id=run_id_1,
        phase="orchestrator",
        event_type="completed",
        summary="Run completed successfully",
    ))

    # Add evaluation artifact
    temp_store.save_artifact(ArtifactRecord(
        run_id=run_id_1,
        phase="evaluation",
        artifact_type="evaluation",
        payload={"score": 0.95},
        saved_at="2026-04-06T12:11:00Z",
    ))
    runs.append(run_id_1)

    # Run 2: In progress (no completion event)
    run_id_2 = "2026-04-06T13-00-00Z__test-run-2__def456"
    header_2 = RunHeader(
        run_id=run_id_2,
        created_at="2026-04-06T13:00:00Z",
        goal="Refactor database layer for better performance",
        repo_id="WoltLab51/Genus",
        workspace_root="/tmp/workspace2",
    )
    temp_store.save_header(header_2)

    temp_store.append_event(JournalEvent(
        ts="2026-04-06T13:05:00Z",
        run_id=run_id_2,
        phase="plan",
        event_type="started",
        summary="Planning started",
    ))
    runs.append(run_id_2)

    # Run 3: Failed
    run_id_3 = "2026-04-06T14-00-00Z__test-run-3__ghi789"
    header_3 = RunHeader(
        run_id=run_id_3,
        created_at="2026-04-06T14:00:00Z",
        goal="Fix critical bug in payment processing",
        repo_id="WoltLab51/Genus",
        workspace_root="/tmp/workspace3",
    )
    temp_store.save_header(header_3)

    temp_store.append_event(JournalEvent(
        ts="2026-04-06T14:10:00Z",
        run_id=run_id_3,
        phase="orchestrator",
        event_type="failed",
        summary="Run failed",
    ))

    # Add evaluation artifact with low score
    temp_store.save_artifact(ArtifactRecord(
        run_id=run_id_3,
        phase="evaluation",
        artifact_type="evaluation",
        payload={"score": 0.25},
        saved_at="2026-04-06T14:11:00Z",
    ))
    runs.append(run_id_3)

    return runs, temp_store


def test_cmd_list_runs_empty_store(tmp_path):
    """Test list-runs with an empty store."""
    config = CliConfig(runs_store_dir=tmp_path / "empty")

    # Capture stdout and stderr
    captured_output = StringIO()
    captured_error = StringIO()
    sys.stdout = captured_output
    sys.stderr = captured_error

    try:
        exit_code = cmd_list_runs(config, limit=20, format="text")
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    assert exit_code == 1
    error_output = captured_error.getvalue()
    assert "does not exist" in error_output.lower() or "not found" in error_output.lower()


def test_cmd_list_runs_text_format(sample_runs):
    """Test list-runs with text format."""
    run_ids, store = sample_runs
    config = CliConfig(runs_store_dir=store.base_dir)

    # Capture stdout
    captured_output = StringIO()
    sys.stdout = captured_output

    try:
        exit_code = cmd_list_runs(config, limit=20, format="text")
    finally:
        sys.stdout = sys.__stdout__

    assert exit_code == 0
    output = captured_output.getvalue()

    # Verify all run IDs appear
    assert run_ids[0] in output
    assert run_ids[1] in output
    assert run_ids[2] in output

    # Verify statuses appear
    assert "completed" in output
    assert "in_progress" in output
    assert "failed" in output

    # Verify goals appear (truncated or full)
    assert "authentication" in output.lower()
    assert "database" in output.lower()
    assert "payment" in output.lower()

    # Verify scores appear
    assert "0.95" in output
    assert "0.25" in output


def test_cmd_list_runs_markdown_format(sample_runs):
    """Test list-runs with markdown format."""
    run_ids, store = sample_runs
    config = CliConfig(runs_store_dir=store.base_dir)

    # Capture stdout
    captured_output = StringIO()
    sys.stdout = captured_output

    try:
        exit_code = cmd_list_runs(config, limit=20, format="md")
    finally:
        sys.stdout = sys.__stdout__

    assert exit_code == 0
    output = captured_output.getvalue()

    # Verify markdown structure
    assert "# Recent GENUS Runs" in output
    assert "| Created At |" in output
    assert "|------------|" in output

    # Verify run IDs appear
    assert run_ids[0] in output
    assert run_ids[1] in output
    assert run_ids[2] in output


def test_cmd_list_runs_sort_order(sample_runs):
    """Test that runs are sorted by creation time (newest first)."""
    run_ids, store = sample_runs
    config = CliConfig(runs_store_dir=store.base_dir)

    # Capture stdout
    captured_output = StringIO()
    sys.stdout = captured_output

    try:
        exit_code = cmd_list_runs(config, limit=20, format="text")
    finally:
        sys.stdout = sys.__stdout__

    assert exit_code == 0
    output = captured_output.getvalue()

    # Find positions of run IDs in output
    pos_1 = output.find(run_ids[0])
    pos_2 = output.find(run_ids[1])
    pos_3 = output.find(run_ids[2])

    # Newest (run 3) should appear first, then run 2, then run 1
    assert pos_3 < pos_2 < pos_1


def test_cmd_list_runs_limit(sample_runs):
    """Test that limit parameter works correctly."""
    run_ids, store = sample_runs
    config = CliConfig(runs_store_dir=store.base_dir)

    # Capture stdout
    captured_output = StringIO()
    sys.stdout = captured_output

    try:
        exit_code = cmd_list_runs(config, limit=2, format="text")
    finally:
        sys.stdout = sys.__stdout__

    assert exit_code == 0
    output = captured_output.getvalue()

    # Count how many run IDs appear (should be exactly 2)
    count = sum(1 for run_id in run_ids if run_id in output)
    assert count == 2

    # The oldest run (run 1) should not appear
    assert run_ids[0] not in output


def test_cmd_list_runs_with_run_without_header(temp_store):
    """Test list-runs handles runs without headers gracefully."""
    config = CliConfig(runs_store_dir=temp_store.base_dir)

    # Create a run directory without header
    run_id = "2026-04-06T15-00-00Z__no-header__xyz"
    run_dir = temp_store._run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Capture stdout
    captured_output = StringIO()
    sys.stdout = captured_output

    try:
        exit_code = cmd_list_runs(config, limit=20, format="text")
    finally:
        sys.stdout = sys.__stdout__

    assert exit_code == 0
    output = captured_output.getvalue()

    # Run should appear with placeholder info
    assert run_id in output
    assert "(no header)" in output


def test_cmd_list_runs_with_scores(sample_runs):
    """Test that scores are displayed when available."""
    run_ids, store = sample_runs
    config = CliConfig(runs_store_dir=store.base_dir)

    # Capture stdout
    captured_output = StringIO()
    sys.stdout = captured_output

    try:
        exit_code = cmd_list_runs(config, limit=20, format="text")
    finally:
        sys.stdout = sys.__stdout__

    assert exit_code == 0
    output = captured_output.getvalue()

    # Scores should be displayed
    assert "0.95" in output  # Run 1's score
    assert "0.25" in output  # Run 3's score

    # Run 2 should show "-" for no score
    lines = output.split("\n")
    run_2_line = [line for line in lines if run_ids[1] in line]
    assert len(run_2_line) == 1
    # Check that there's a dash for missing score (format: "Status Score Goal")
    assert "-" in run_2_line[0]
