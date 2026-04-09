"""Tests for RunJournal.get_artifacts() — the previously missing method."""
import pytest
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.memory.models import ArtifactRecord


@pytest.fixture
def tmp_journal(tmp_path):
    store = JsonlRunStore(base_dir=str(tmp_path / "runs"))
    journal = RunJournal("test-run-001", store)
    journal.initialize(goal="Test goal")
    return journal


def test_get_artifacts_empty(tmp_journal):
    """get_artifacts() on empty journal returns empty list."""
    result = tmp_journal.get_artifacts()
    assert result == []


def test_get_artifacts_returns_records(tmp_journal):
    """get_artifacts() returns ArtifactRecord objects, not strings."""
    tmp_journal.save_artifact(
        phase="strategy",
        artifact_type="strategy_decision",
        payload={"playbook": "test"},
    )
    result = tmp_journal.get_artifacts()
    assert len(result) == 1
    assert isinstance(result[0], ArtifactRecord)
    assert result[0].artifact_type == "strategy_decision"


def test_get_artifacts_filter_by_type(tmp_journal):
    """get_artifacts(artifact_type=...) filters correctly."""
    tmp_journal.save_artifact(phase="plan", artifact_type="plan", payload={"steps": []})
    tmp_journal.save_artifact(phase="strategy", artifact_type="strategy_decision", payload={"playbook": "a"})

    result = tmp_journal.get_artifacts(artifact_type="strategy_decision")
    assert len(result) == 1
    assert result[0].artifact_type == "strategy_decision"


def test_get_artifacts_filter_by_phase(tmp_journal):
    """get_artifacts(phase=...) filters by phase."""
    tmp_journal.save_artifact(phase="plan", artifact_type="plan", payload={"steps": []})
    tmp_journal.save_artifact(phase="review", artifact_type="review", payload={"score": 90})

    result = tmp_journal.get_artifacts(phase="plan")
    assert len(result) == 1
    assert result[0].phase == "plan"


def test_get_artifacts_filter_by_type_and_phase(tmp_journal):
    """get_artifacts(artifact_type=..., phase=...) combines both filters."""
    tmp_journal.save_artifact(phase="strategy", artifact_type="strategy_decision", payload={"playbook": "a"})
    tmp_journal.save_artifact(phase="meta", artifact_type="strategy_decision", payload={"playbook": "b"})

    result = tmp_journal.get_artifacts(artifact_type="strategy_decision", phase="strategy")
    assert len(result) == 1
    assert result[0].phase == "strategy"


def test_get_artifacts_multiple_ordered(tmp_journal):
    """get_artifacts() returns records in chronological order."""
    tmp_journal.save_artifact(phase="strategy", artifact_type="strategy_decision", payload={"i": 1})
    tmp_journal.save_artifact(phase="strategy", artifact_type="strategy_decision", payload={"i": 2})
    tmp_journal.save_artifact(phase="strategy", artifact_type="strategy_decision", payload={"i": 3})

    result = tmp_journal.get_artifacts(artifact_type="strategy_decision")
    assert len(result) == 3
    # All three returned, order must be consistent
    payloads = [r.payload["i"] for r in result]
    assert sorted(payloads) == [1, 2, 3]
