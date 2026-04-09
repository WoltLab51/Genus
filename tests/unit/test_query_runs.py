"""Tests for query_runs() cross-run filter function."""
import pytest
from genus.memory.store_jsonl import JsonlRunStore
from genus.memory.models import RunHeader
from genus.memory.query import query_runs


@pytest.fixture
def store_with_runs(tmp_path):
    store = JsonlRunStore(base_dir=str(tmp_path / "runs"))
    headers = [
        RunHeader(run_id="run-001", created_at="2024-01-01T00:00:00+00:00",
                  goal="Fix sandbox bug", repo_id="owner/repo"),
        RunHeader(run_id="run-002", created_at="2024-01-02T00:00:00+00:00",
                  goal="Add new feature", repo_id="owner/repo"),
        RunHeader(run_id="run-003", created_at="2024-01-03T00:00:00+00:00",
                  goal="Fix memory leak", repo_id="other/repo"),
        RunHeader(run_id="run-004", created_at="2024-01-04T00:00:00+00:00",
                  goal="Refactor sandbox", repo_id="owner/repo"),
    ]
    for h in headers:
        store.save_header(h)
    return store


def test_query_runs_no_filter(store_with_runs):
    result = query_runs(store_with_runs)
    assert len(result) == 4


def test_query_runs_repo_id(store_with_runs):
    result = query_runs(store_with_runs, repo_id="owner/repo")
    assert len(result) == 3
    assert all(r.repo_id == "owner/repo" for r in result)


def test_query_runs_goal_contains(store_with_runs):
    result = query_runs(store_with_runs, goal_contains="sandbox")
    assert len(result) == 2
    assert all("sandbox" in r.goal.lower() for r in result)


def test_query_runs_goal_contains_case_insensitive(store_with_runs):
    result = query_runs(store_with_runs, goal_contains="SANDBOX")
    assert len(result) == 2


def test_query_runs_since(store_with_runs):
    result = query_runs(store_with_runs, since="2024-01-03T00:00:00+00:00")
    assert len(result) == 2
    assert all(r.created_at >= "2024-01-03T00:00:00+00:00" for r in result)


def test_query_runs_until(store_with_runs):
    result = query_runs(store_with_runs, until="2024-01-02T00:00:00+00:00")
    assert len(result) == 2


def test_query_runs_limit(store_with_runs):
    result = query_runs(store_with_runs, limit=2)
    assert len(result) == 2


def test_query_runs_combined_filters(store_with_runs):
    result = query_runs(
        store_with_runs,
        repo_id="owner/repo",
        goal_contains="fix",
        limit=1,
    )
    assert len(result) == 1
    assert result[0].repo_id == "owner/repo"
    assert "fix" in result[0].goal.lower()


def test_query_runs_empty_store(tmp_path):
    store = JsonlRunStore(base_dir=str(tmp_path / "runs"))
    assert query_runs(store) == []


def test_query_runs_no_match(store_with_runs):
    result = query_runs(store_with_runs, repo_id="nonexistent/repo")
    assert result == []
