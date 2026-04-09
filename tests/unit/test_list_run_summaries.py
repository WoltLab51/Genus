"""Tests for JsonlRunStore.list_run_summaries()."""
import pytest
from genus.memory.store_jsonl import JsonlRunStore
from genus.memory.models import RunHeader


@pytest.fixture
def store(tmp_path):
    return JsonlRunStore(base_dir=str(tmp_path / "runs"))


def test_list_run_summaries_empty(store):
    assert store.list_run_summaries() == []


def test_list_run_summaries_returns_headers(store):
    h = RunHeader(run_id="run-001", created_at="2024-01-01T00:00:00Z", goal="Test")
    store.save_header(h)
    result = store.list_run_summaries()
    assert len(result) == 1
    assert isinstance(result[0], RunHeader)
    assert result[0].goal == "Test"


def test_list_run_summaries_most_recent_first(store):
    for i in ["run-a", "run-b", "run-c"]:
        store.save_header(RunHeader(run_id=i, created_at="2024-01-01T00:00:00Z", goal=i))
    result = store.list_run_summaries()
    names = [r.run_id for r in result]
    assert names == sorted(names, reverse=True)


def test_list_run_summaries_limit(store):
    for i in range(5):
        store.save_header(RunHeader(run_id=f"run-{i:03d}", created_at="2024-01-01T00:00:00Z", goal=f"goal-{i}"))
    result = store.list_run_summaries(limit=2)
    assert len(result) == 2


def test_list_run_summaries_skips_no_header(store, tmp_path):
    # Create a run dir without header.json
    (tmp_path / "runs" / "orphan-run").mkdir(parents=True)
    store.save_header(RunHeader(run_id="real-run", created_at="2024-01-01T00:00:00Z", goal="real"))
    result = store.list_run_summaries()
    # orphan-run has no header, should be skipped
    assert len(result) == 1
    assert result[0].run_id == "real-run"
