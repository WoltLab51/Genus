"""Tests for ToolMemoryIndex."""
import pytest
from genus.memory.store_jsonl import JsonlRunStore
from genus.memory.run_journal import RunJournal
from genus.memory.tool_memory import ToolMemoryIndex, ToolUsageStat


@pytest.fixture
def store_with_tool_events(tmp_path):
    store = JsonlRunStore(base_dir=str(tmp_path / "runs"))

    # Run 1: implement phase
    j1 = RunJournal("run-001", store)
    j1.initialize(goal="Run 1")
    j1.log_tool_use("implement", "git_create_branch", branch_name="feature/x")
    j1.log_tool_use("implement", "write_text_file", rel_path="foo.py")
    j1.log_tool_use("test", "sandbox_run", argv=["python", "-m", "pytest"])

    # Run 2: fix phase
    j2 = RunJournal("run-002", store)
    j2.initialize(goal="Run 2")
    j2.log_tool_use("fix", "write_text_file", rel_path="bar.py", iteration=1)
    j2.log_tool_use("implement", "git_create_branch", branch_name="feature/y")

    return store


def test_build_indexes_all_runs(store_with_tool_events):
    index = ToolMemoryIndex(store_with_tool_events)
    index.build()
    assert index.indexed_run_count == 2
    assert index.is_built


def test_get_stats_known_tool(store_with_tool_events):
    index = ToolMemoryIndex(store_with_tool_events)
    index.build()
    stats = index.get_stats("git_create_branch")
    assert stats is not None
    assert stats.total_calls == 2
    assert stats.run_count == 2


def test_get_stats_unknown_tool(store_with_tool_events):
    index = ToolMemoryIndex(store_with_tool_events)
    index.build()
    assert index.get_stats("nonexistent_tool") is None


def test_all_stats_sorted_by_total_calls(store_with_tool_events):
    index = ToolMemoryIndex(store_with_tool_events)
    index.build()
    stats = index.all_stats()
    calls = [s.total_calls for s in stats]
    assert calls == sorted(calls, reverse=True)


def test_top_tools_no_phase(store_with_tool_events):
    index = ToolMemoryIndex(store_with_tool_events)
    index.build()
    top = index.top_tools(n=2)
    assert len(top) <= 2


def test_top_tools_by_phase(store_with_tool_events):
    index = ToolMemoryIndex(store_with_tool_events)
    index.build()
    top = index.top_tools(phase="implement")
    tool_names = [s.tool_name for s in top]
    assert "git_create_branch" in tool_names
    assert "write_text_file" in tool_names
    # sandbox_run only in 'test' phase, should NOT appear
    assert "sandbox_run" not in tool_names


def test_calls_by_phase(store_with_tool_events):
    index = ToolMemoryIndex(store_with_tool_events)
    index.build()
    stats = index.get_stats("write_text_file")
    assert stats is not None
    assert stats.calls_by_phase.get("implement", 0) == 1
    assert stats.calls_by_phase.get("fix", 0) == 1


def test_build_with_explicit_run_ids(store_with_tool_events):
    index = ToolMemoryIndex(store_with_tool_events)
    index.build(run_ids=["run-001"])
    assert index.indexed_run_count == 1
    stats = index.get_stats("sandbox_run")
    assert stats is not None
    assert stats.run_count == 1


def test_build_skips_nonexistent_run(store_with_tool_events):
    index = ToolMemoryIndex(store_with_tool_events)
    index.build(run_ids=["run-001", "nonexistent-run"])
    assert index.indexed_run_count == 1


def test_empty_store(tmp_path):
    store = JsonlRunStore(base_dir=str(tmp_path / "runs"))
    index = ToolMemoryIndex(store)
    index.build()
    assert index.indexed_run_count == 0
    assert index.all_stats() == []
