"""Tests for EvaluationAgent tool_context integration."""
from unittest.mock import MagicMock

import pytest

from genus.meta.agents.evaluation_agent import EvaluationAgent
from genus.memory.tool_memory import ToolMemoryIndex, ToolUsageStat


def _make_agent(tool_memory_index=None):
    bus = MagicMock()
    store = MagicMock()
    evaluator = MagicMock()
    evaluator.evaluate.return_value = MagicMock(
        run_id="run-001",
        created_at="2026-01-01T00:00:00+00:00",
        score=80,
        final_status="completed",
        failure_class=None,
        root_cause_hint=None,
        highlights=[],
        issues=[],
        recommendations=[],
        strategy_recommendations=[],
        evidence=[],
    )
    return EvaluationAgent(
        bus=bus,
        agent_id="test-eval",
        store=store,
        evaluator=evaluator,
        tool_memory_index=tool_memory_index,
    )


def _make_journal():
    journal = MagicMock()
    journal.run_id = "run-001"
    journal.get_header.return_value = MagicMock(goal="test", run_id="run-001")
    journal.list_artifacts.return_value = []
    journal.get_events.return_value = []
    return journal


def _make_msg():
    from genus.dev import topics as dev_topics

    msg = MagicMock()
    msg.topic = dev_topics.DEV_LOOP_COMPLETED
    return msg


def test_tool_context_none_when_no_index():
    agent = _make_agent(tool_memory_index=None)
    result = agent._build_evaluation_input(_make_journal(), _make_msg())
    assert result.tool_context is None


def test_tool_context_none_when_index_not_built():
    index = MagicMock(spec=ToolMemoryIndex)
    index.is_built = False
    agent = _make_agent(tool_memory_index=index)
    result = agent._build_evaluation_input(_make_journal(), _make_msg())
    assert result.tool_context is None


def test_tool_context_populated_when_index_built():
    stat = ToolUsageStat(tool_name="sandbox_run")
    stat.record_call(phase="fix", run_id="run-001")
    stat.record_call(phase="fix", run_id="run-002")

    index = MagicMock(spec=ToolMemoryIndex)
    index.is_built = True
    index.indexed_run_count = 5
    index.top_tools.return_value = [stat]

    agent = _make_agent(tool_memory_index=index)
    result = agent._build_evaluation_input(_make_journal(), _make_msg())

    assert result.tool_context is not None
    assert result.tool_context["indexed_run_count"] == 5
    assert len(result.tool_context["top_tools_fix"]) == 1
    assert result.tool_context["top_tools_fix"][0]["tool_name"] == "sandbox_run"
    assert result.tool_context["top_tools_fix"][0]["calls_in_phase"] == 2
    assert result.tool_context["top_tools_fix"][0]["total_calls"] == 2
    index.top_tools.assert_called_once_with(phase="fix", n=5)


def test_tool_context_none_on_exception():
    index = MagicMock(spec=ToolMemoryIndex)
    index.is_built = True
    index.top_tools.side_effect = RuntimeError("boom")

    agent = _make_agent(tool_memory_index=index)
    result = agent._build_evaluation_input(_make_journal(), _make_msg())
    assert result.tool_context is None  # graceful fallback
