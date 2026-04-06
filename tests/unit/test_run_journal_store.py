"""
Unit tests for the Run Journal Store v1.

Covers:
- RunHeader, JournalEvent, and ArtifactRecord data models
- JsonlRunStore: save/load header, append/iter events, save/load artifacts
- RunJournal: high-level convenience API
- Filesystem sanitization and safety
- Storage layout verification
- Error handling for malformed data
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from genus.memory.models import ArtifactRecord, JournalEvent, RunHeader
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore, sanitize_run_id


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RUN_ID = "2026-04-06T15-00-00Z__test-task__abc123"
SAFE_RUN_ID = RUN_ID  # Already safe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_header(run_id: str = RUN_ID, **kwargs) -> RunHeader:
    """Create a test RunHeader."""
    defaults = {
        "run_id": run_id,
        "created_at": "2026-04-06T15:00:00+00:00",
        "goal": "Test goal",
        "repo_id": "WoltLab51/Genus",
        "workspace_root": "/tmp/workspace",
        "meta": {"test": True},
    }
    defaults.update(kwargs)
    return RunHeader(**defaults)


def _make_event(run_id: str = RUN_ID, **kwargs) -> JournalEvent:
    """Create a test JournalEvent."""
    defaults = {
        "ts": "2026-04-06T15:00:00+00:00",
        "run_id": run_id,
        "phase": "plan",
        "event_type": "started",
        "summary": "Phase started",
        "phase_id": "phase_001",
        "data": {"test": True},
        "evidence": [],
    }
    defaults.update(kwargs)
    return JournalEvent(**defaults)


def _make_artifact(run_id: str = RUN_ID, **kwargs) -> ArtifactRecord:
    """Create a test ArtifactRecord."""
    defaults = {
        "run_id": run_id,
        "phase": "plan",
        "artifact_type": "plan",
        "payload": {"content": "test plan"},
        "saved_at": "2026-04-06T15:00:00+00:00",
        "phase_id": "phase_001",
        "evidence": [],
    }
    defaults.update(kwargs)
    return ArtifactRecord(**defaults)


# ===========================================================================
# Test sanitize_run_id
# ===========================================================================


class TestSanitizeRunId:
    def test_normal_run_id_unchanged(self):
        assert sanitize_run_id(RUN_ID) == RUN_ID

    def test_replaces_colons(self):
        result = sanitize_run_id("2026:04:06")
        assert ":" not in result
        assert result == "2026_04_06"

    def test_replaces_spaces(self):
        result = sanitize_run_id("my run id")
        assert " " not in result
        assert result == "my_run_id"

    def test_traversal_raises(self):
        with pytest.raises(ValueError, match="path-traversal"):
            sanitize_run_id("../etc/passwd")

    def test_traversal_in_middle_raises(self):
        with pytest.raises(ValueError, match="path-traversal"):
            sanitize_run_id("run/../secret")

    def test_allows_dots_hyphens_underscores(self):
        safe = sanitize_run_id("run-2026_04_06.test")
        assert safe == "run-2026_04_06.test"

    def test_empty_string_becomes_unknown(self):
        result = sanitize_run_id("")
        assert result == "unknown"


# ===========================================================================
# Test JsonlRunStore - Header operations
# ===========================================================================


class TestJsonlRunStoreHeader:
    def test_save_and_load_header(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        header = _make_header()

        store.save_header(header)
        loaded = store.load_header(RUN_ID)

        assert loaded is not None
        assert loaded.run_id == header.run_id
        assert loaded.created_at == header.created_at
        assert loaded.goal == header.goal
        assert loaded.repo_id == header.repo_id
        assert loaded.workspace_root == header.workspace_root
        assert loaded.meta == header.meta

    def test_load_nonexistent_header_returns_none(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        loaded = store.load_header("nonexistent")
        assert loaded is None

    def test_header_creates_directory(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        header = _make_header()

        store.save_header(header)

        run_dir = tmp_path / SAFE_RUN_ID
        assert run_dir.exists()
        assert run_dir.is_dir()

    def test_header_file_is_valid_json(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        header = _make_header()

        store.save_header(header)

        header_path = tmp_path / SAFE_RUN_ID / "header.json"
        with open(header_path, "r") as f:
            data = json.load(f)

        assert data["run_id"] == RUN_ID
        assert data["goal"] == "Test goal"

    def test_update_header_overwrites(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        header1 = _make_header(goal="First goal")
        header2 = _make_header(goal="Second goal")

        store.save_header(header1)
        store.save_header(header2)

        loaded = store.load_header(RUN_ID)
        assert loaded.goal == "Second goal"


# ===========================================================================
# Test JsonlRunStore - Journal operations
# ===========================================================================


class TestJsonlRunStoreJournal:
    def test_append_and_iter_events(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        event1 = _make_event(summary="First event")
        event2 = _make_event(summary="Second event")

        store.append_event(event1)
        store.append_event(event2)

        events = list(store.iter_events(RUN_ID))
        assert len(events) == 2
        assert events[0].summary == "First event"
        assert events[1].summary == "Second event"

    def test_list_events_convenience(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        event = _make_event()

        store.append_event(event)
        events = store.list_events(RUN_ID)

        assert len(events) == 1
        assert events[0].summary == event.summary

    def test_iter_nonexistent_run_yields_nothing(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        events = list(store.iter_events("nonexistent"))
        assert events == []

    def test_journal_preserves_event_fields(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        event = _make_event(
            phase="implement",
            event_type="tool_used",
            summary="Used grep",
            phase_id="impl_001",
            data={"tool": "grep", "args": {"pattern": "test"}},
            evidence=[{"file": "test.py", "line": 42}],
        )

        store.append_event(event)
        loaded = store.list_events(RUN_ID)[0]

        assert loaded.phase == "implement"
        assert loaded.event_type == "tool_used"
        assert loaded.summary == "Used grep"
        assert loaded.phase_id == "impl_001"
        assert loaded.data == {"tool": "grep", "args": {"pattern": "test"}}
        assert loaded.evidence == [{"file": "test.py", "line": 42}]

    def test_malformed_journal_line_skipped(self, tmp_path, caplog):
        store = JsonlRunStore(base_dir=str(tmp_path))
        event = _make_event()
        store.append_event(event)

        # Manually corrupt the journal file
        journal_path = tmp_path / SAFE_RUN_ID / "journal.jsonl"
        with open(journal_path, "a") as f:
            f.write("THIS IS NOT JSON\n")

        # Should skip the malformed line and still return the valid event
        events = store.list_events(RUN_ID)
        assert len(events) == 1
        assert events[0].summary == event.summary

        # Should log a warning
        assert "malformed journal line" in caplog.text.lower()

    def test_empty_journal_lines_skipped(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        event = _make_event()
        store.append_event(event)

        # Add empty lines
        journal_path = tmp_path / SAFE_RUN_ID / "journal.jsonl"
        with open(journal_path, "a") as f:
            f.write("\n\n\n")

        # Should still return only the valid event
        events = store.list_events(RUN_ID)
        assert len(events) == 1


# ===========================================================================
# Test JsonlRunStore - Artifact operations
# ===========================================================================


class TestJsonlRunStoreArtifacts:
    def test_save_and_load_artifact(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        artifact = _make_artifact()

        artifact_id = store.save_artifact(artifact)
        loaded = store.load_artifact(RUN_ID, artifact_id)

        assert loaded is not None
        assert loaded.run_id == artifact.run_id
        assert loaded.phase == artifact.phase
        assert loaded.artifact_type == artifact.artifact_type
        assert loaded.payload == artifact.payload
        assert loaded.saved_at == artifact.saved_at
        assert loaded.phase_id == artifact.phase_id
        assert loaded.evidence == artifact.evidence

    def test_save_artifact_returns_id(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        artifact = _make_artifact()

        artifact_id = store.save_artifact(artifact)

        assert artifact_id is not None
        assert isinstance(artifact_id, str)
        assert len(artifact_id) > 0

    def test_load_nonexistent_artifact_returns_none(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        loaded = store.load_artifact(RUN_ID, "nonexistent")
        assert loaded is None

    def test_list_artifacts(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        artifact1 = _make_artifact(artifact_type="plan")
        artifact2 = _make_artifact(artifact_type="test_report")

        id1 = store.save_artifact(artifact1)
        id2 = store.save_artifact(artifact2)

        artifact_ids = store.list_artifacts(RUN_ID)
        assert len(artifact_ids) == 2
        assert id1 in artifact_ids
        assert id2 in artifact_ids

    def test_list_artifacts_filtered_by_type(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        artifact1 = _make_artifact(artifact_type="plan")
        artifact2 = _make_artifact(artifact_type="test_report")

        store.save_artifact(artifact1)
        store.save_artifact(artifact2)

        plan_ids = store.list_artifacts(RUN_ID, artifact_type="plan")
        assert len(plan_ids) == 1

        report_ids = store.list_artifacts(RUN_ID, artifact_type="test_report")
        assert len(report_ids) == 1

    def test_list_artifacts_nonexistent_run_returns_empty(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        artifact_ids = store.list_artifacts("nonexistent")
        assert artifact_ids == []

    def test_artifact_directory_created(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        artifact = _make_artifact()

        store.save_artifact(artifact)

        artifacts_dir = tmp_path / SAFE_RUN_ID / "artifacts"
        assert artifacts_dir.exists()
        assert artifacts_dir.is_dir()


# ===========================================================================
# Test JsonlRunStore - Utility methods
# ===========================================================================


class TestJsonlRunStoreUtility:
    def test_run_exists_returns_true(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        header = _make_header()
        store.save_header(header)

        assert store.run_exists(RUN_ID) is True

    def test_run_exists_returns_false(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        assert store.run_exists("nonexistent") is False

    def test_list_runs(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        header1 = _make_header(run_id="run1")
        header2 = _make_header(run_id="run2")

        store.save_header(header1)
        store.save_header(header2)

        runs = store.list_runs()
        assert len(runs) == 2
        assert "run1" in runs
        assert "run2" in runs

    def test_list_runs_empty(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        runs = store.list_runs()
        assert runs == []

    def test_base_dir_property(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        assert store.base_dir == tmp_path


# ===========================================================================
# Test RunJournal - High-level API
# ===========================================================================


class TestRunJournal:
    def test_initialize(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        header = journal.initialize(
            goal="Test task",
            repo_id="WoltLab51/Genus",
            workspace_root="/tmp/ws",
            custom_field="value",
        )

        assert header.run_id == RUN_ID
        assert header.goal == "Test task"
        assert header.repo_id == "WoltLab51/Genus"
        assert header.workspace_root == "/tmp/ws"
        assert header.meta["custom_field"] == "value"

        loaded = journal.get_header()
        assert loaded is not None
        assert loaded.goal == "Test task"

    def test_log_event(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        event = journal.log_event(
            phase="plan",
            event_type="decision",
            summary="Decided to use pattern X",
            phase_id="plan_001",
            data={"pattern": "X"},
            evidence=[{"file": "test.py"}],
        )

        assert event.phase == "plan"
        assert event.event_type == "decision"
        assert event.summary == "Decided to use pattern X"

        events = journal.get_events()
        assert len(events) == 1
        assert events[0].summary == event.summary

    def test_log_phase_start(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        event = journal.log_phase_start("implement", phase_id="impl_001")

        assert event.phase == "implement"
        assert event.event_type == "started"
        assert "implement" in event.summary.lower()

    def test_log_decision(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        event = journal.log_decision(
            phase="plan",
            decision="Use approach A",
            evidence=[{"reason": "faster"}],
        )

        assert event.event_type == "decision"
        assert event.summary == "Use approach A"
        assert event.evidence == [{"reason": "faster"}]

    def test_log_tool_use(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        event = journal.log_tool_use(
            phase="implement",
            tool_name="grep",
            args={"pattern": "test"},
        )

        assert event.event_type == "tool_used"
        assert "grep" in event.summary
        assert event.data["tool_name"] == "grep"
        assert event.data["args"] == {"pattern": "test"}

    def test_log_error(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        event = journal.log_error(
            phase="test",
            error="Test failed",
            exception_type="AssertionError",
        )

        assert event.event_type == "error"
        assert event.summary == "Test failed"
        assert event.data["exception_type"] == "AssertionError"

    def test_get_events_filtered_by_phase(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        journal.log_event("plan", "started", "Plan started")
        journal.log_event("implement", "started", "Implement started")

        plan_events = journal.get_events(phase="plan")
        assert len(plan_events) == 1
        assert plan_events[0].phase == "plan"

    def test_get_events_filtered_by_type(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        journal.log_event("plan", "started", "Started")
        journal.log_event("plan", "decision", "Decided")

        decision_events = journal.get_events(event_type="decision")
        assert len(decision_events) == 1
        assert decision_events[0].event_type == "decision"

    def test_save_artifact(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        artifact_id = journal.save_artifact(
            phase="plan",
            artifact_type="plan",
            payload={"content": "Plan content"},
            phase_id="plan_001",
        )

        assert artifact_id is not None

        loaded = journal.load_artifact(artifact_id)
        assert loaded is not None
        assert loaded.artifact_type == "plan"
        assert loaded.payload == {"content": "Plan content"}

        # Should also log an event
        events = journal.get_events(event_type="artifact_saved")
        assert len(events) == 1
        assert events[0].data["artifact_id"] == artifact_id

    def test_list_artifacts(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        id1 = journal.save_artifact("plan", "plan", {"content": "plan"})
        id2 = journal.save_artifact("test", "test_report", {"results": []})

        all_artifacts = journal.list_artifacts()
        assert len(all_artifacts) == 2

        plans = journal.list_artifacts(artifact_type="plan")
        assert len(plans) == 1
        assert id1 in plans

    def test_exists(self, tmp_path):
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        assert journal.exists() is False

        journal.initialize(goal="Test")

        assert journal.exists() is True


# ===========================================================================
# Test storage layout
# ===========================================================================


class TestStorageLayout:
    def test_complete_storage_layout(self, tmp_path):
        """Verify the complete storage layout for a run."""
        store = JsonlRunStore(base_dir=str(tmp_path))
        journal = RunJournal(RUN_ID, store)

        # Initialize run
        journal.initialize(goal="Complete test")

        # Log some events
        journal.log_phase_start("plan")
        journal.log_decision("plan", "Use pattern X")

        # Save an artifact
        journal.save_artifact("plan", "plan", {"content": "plan"})

        # Verify directory structure
        run_dir = tmp_path / SAFE_RUN_ID
        assert run_dir.exists()
        assert (run_dir / "header.json").exists()
        assert (run_dir / "journal.jsonl").exists()
        assert (run_dir / "artifacts").exists()
        assert (run_dir / "artifacts").is_dir()

        # Verify at least one artifact file exists
        artifact_files = list((run_dir / "artifacts").glob("*.json"))
        assert len(artifact_files) >= 1


# ===========================================================================
# Test environment variable override
# ===========================================================================


class TestEnvironmentOverride:
    def test_env_var_overrides_default(self, tmp_path, monkeypatch):
        custom_dir = tmp_path / "custom_runs"
        monkeypatch.setenv("GENUS_RUNSTORE_DIR", str(custom_dir))

        store = JsonlRunStore()
        assert store.base_dir == custom_dir

    def test_explicit_arg_overrides_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GENUS_RUNSTORE_DIR", "/should/not/use/this")
        explicit_dir = tmp_path / "explicit"

        store = JsonlRunStore(base_dir=str(explicit_dir))
        assert store.base_dir == explicit_dir
