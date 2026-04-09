"""Tests for EpisodicContextBuilder functions."""
import pytest
from genus.memory.store_jsonl import JsonlRunStore
from genus.memory.run_journal import RunJournal
from genus.memory.models import RunHeader
from genus.memory.context_builder import (
    build_run_summary,
    build_episodic_context,
    format_context_as_text,
)


@pytest.fixture
def store(tmp_path):
    return JsonlRunStore(base_dir=str(tmp_path / "runs"))


def test_build_run_summary_no_header(store):
    result = build_run_summary("nonexistent-run", store)
    assert result is None


def test_build_run_summary_minimal(store):
    j = RunJournal("run-001", store)
    j.initialize(goal="Fix bug", repo_id="owner/repo")
    result = build_run_summary("run-001", store)
    assert result is not None
    assert result["goal"] == "Fix bug"
    assert result["repo_id"] == "owner/repo"
    assert result["evaluation"] is None
    assert result["feedback"] is None
    assert result["strategy"] is None


def test_build_run_summary_with_evaluation(store):
    j = RunJournal("run-002", store)
    j.initialize(goal="Run 2")
    j.save_artifact(
        phase="meta",
        artifact_type="evaluation",
        payload={
            "score": 75,
            "failure_class": "test_failure",
            "strategy_recommendations": ["minimize_changeset"],
        },
    )
    result = build_run_summary("run-002", store)
    assert result["evaluation"]["score"] == 75
    assert result["evaluation"]["failure_class"] == "test_failure"
    assert "minimize_changeset" in result["evaluation"]["strategy_recommendations"]


def test_build_run_summary_with_feedback(store):
    j = RunJournal("run-003", store)
    j.initialize(goal="Run 3")
    j.save_artifact(
        phase="feedback",
        artifact_type="feedback_record",
        payload={"outcome": "good", "score_delta": 3.0},
    )
    result = build_run_summary("run-003", store)
    assert result["feedback"]["outcome"] == "good"
    assert result["feedback"]["score_delta"] == 3.0


def test_build_run_summary_with_strategy(store):
    j = RunJournal("run-004", store)
    j.initialize(goal="Run 4")
    j.save_artifact(
        phase="strategy",
        artifact_type="strategy_decision",
        payload={"selected_playbook": "fix_tests", "reason": "test failure"},
    )
    result = build_run_summary("run-004", store)
    assert result["strategy"]["selected_playbook"] == "fix_tests"


def test_build_episodic_context_empty(store):
    result = build_episodic_context(store, run_ids=[])
    assert result == []


def test_build_episodic_context_skips_no_header(store, tmp_path):
    # Create orphan dir without header
    (tmp_path / "runs" / "orphan").mkdir(parents=True)
    result = build_episodic_context(store, run_ids=["orphan"])
    assert result == []


def test_build_episodic_context_max_runs(store):
    for i in range(5):
        j = RunJournal(f"run-{i:03d}", store)
        j.initialize(goal=f"Goal {i}")
    result = build_episodic_context(
        store,
        run_ids=[f"run-{i:03d}" for i in range(5)],
        max_runs=3,
    )
    assert len(result) == 3


def test_format_context_as_text_empty():
    text = format_context_as_text([])
    assert "0 runs" in text
    assert "No historical runs available" in text


def test_format_context_as_text_with_runs(store):
    j = RunJournal("run-001", store)
    j.initialize(goal="Fix bug", repo_id="owner/repo")
    j.save_artifact(
        phase="meta",
        artifact_type="evaluation",
        payload={"score": 90, "failure_class": None, "strategy_recommendations": []},
    )
    summary = build_run_summary("run-001", store)
    text = format_context_as_text([summary])
    assert "Fix bug" in text
    assert "score=90" in text
    assert "owner/repo" in text
    assert "[Run 1]" in text
