"""Tests for EvaluationInput tool_context field."""
from genus.meta.evaluation_models import EvaluationInput


def test_evaluation_input_tool_context_default_none():
    inp = EvaluationInput(run_id="r", final_status="completed", iterations_used=0)
    assert inp.tool_context is None


def test_evaluation_input_tool_context_can_be_set():
    ctx = {"top_tools_fix": [], "indexed_run_count": 3}
    inp = EvaluationInput(
        run_id="r",
        final_status="completed",
        iterations_used=0,
        tool_context=ctx,
    )
    assert inp.tool_context == ctx
