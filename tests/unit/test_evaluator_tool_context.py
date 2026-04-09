"""Tests for RunEvaluator tool_context analysis (G3)."""
import pytest
from genus.meta.evaluator import RunEvaluator
from genus.meta.evaluation_models import EvaluationInput
from genus.meta.taxonomy import StrategyRecommendation


def _make_input(tool_context=None, final_status="completed", iterations_used=0):
    return EvaluationInput(
        run_id="run-g3",
        final_status=final_status,
        iterations_used=iterations_used,
        tool_context=tool_context,
    )


def test_no_tool_context_no_extra_recommendations():
    evaluator = RunEvaluator()
    inp = _make_input(tool_context=None)
    artifact = evaluator.evaluate(inp)
    assert StrategyRecommendation.VERIFY_SANDBOX_TOOL_USAGE not in artifact.strategy_recommendations
    assert StrategyRecommendation.REVIEW_TOOL_SELECTION not in artifact.strategy_recommendations


def test_empty_top_tools_fix_with_enough_history():
    evaluator = RunEvaluator()
    inp = _make_input(tool_context={"top_tools_fix": [], "indexed_run_count": 5})
    artifact = evaluator.evaluate(inp)
    assert StrategyRecommendation.REVIEW_TOOL_SELECTION in artifact.strategy_recommendations
    assert any("No tools were recorded" in r for r in artifact.recommendations)


def test_sandbox_run_absent_triggers_verify():
    evaluator = RunEvaluator()
    ctx = {
        "top_tools_fix": [
            {"tool_name": "apply_patch", "total_calls": 6, "calls_in_phase": 6}
        ],
        "indexed_run_count": 5,
    }
    inp = _make_input(tool_context=ctx)
    artifact = evaluator.evaluate(inp)
    assert StrategyRecommendation.VERIFY_SANDBOX_TOOL_USAGE in artifact.strategy_recommendations
    assert any("sandbox_run was not used" in r for r in artifact.recommendations)


def test_sandbox_run_low_usage_rate_triggers_verify():
    evaluator = RunEvaluator()
    ctx = {
        "top_tools_fix": [
            {"tool_name": "sandbox_run", "total_calls": 2, "calls_in_phase": 2}
        ],
        "indexed_run_count": 10,  # rate = 0.2 < 0.5
    }
    inp = _make_input(tool_context=ctx)
    artifact = evaluator.evaluate(inp)
    assert StrategyRecommendation.VERIFY_SANDBOX_TOOL_USAGE in artifact.strategy_recommendations
    assert any("usage rate" in r for r in artifact.recommendations)


def test_sandbox_run_good_usage_no_verify():
    evaluator = RunEvaluator()
    ctx = {
        "top_tools_fix": [
            {"tool_name": "sandbox_run", "total_calls": 8, "calls_in_phase": 8}
        ],
        "indexed_run_count": 10,  # rate = 0.8 >= 0.5
    }
    inp = _make_input(tool_context=ctx)
    artifact = evaluator.evaluate(inp)
    assert StrategyRecommendation.VERIFY_SANDBOX_TOOL_USAGE not in artifact.strategy_recommendations


def test_not_enough_history_skips_heuristics():
    evaluator = RunEvaluator()
    ctx = {
        "top_tools_fix": [],  # would normally trigger REVIEW_TOOL_SELECTION
        "indexed_run_count": 2,  # but too few runs
    }
    inp = _make_input(tool_context=ctx)
    artifact = evaluator.evaluate(inp)
    assert StrategyRecommendation.REVIEW_TOOL_SELECTION not in artifact.strategy_recommendations


def test_analyze_tool_context_returns_empty_dict_on_low_count():
    evaluator = RunEvaluator()
    result = evaluator._analyze_tool_context({"top_tools_fix": [], "indexed_run_count": 1})
    assert result["recommendations"] == []
    assert result["strategy_recommendations"] == []


def test_tool_context_does_not_interfere_with_existing_scoring():
    """tool_context should not change score or failure_class."""
    evaluator = RunEvaluator()
    ctx = {"top_tools_fix": [], "indexed_run_count": 10}
    inp_with = _make_input(tool_context=ctx, final_status="completed", iterations_used=0)
    inp_without = _make_input(tool_context=None, final_status="completed", iterations_used=0)
    art_with = evaluator.evaluate(inp_with)
    art_without = evaluator.evaluate(inp_without)
    assert art_with.score == art_without.score
    assert art_with.failure_class == art_without.failure_class
