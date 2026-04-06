"""
Unit tests for RunEvaluator

Tests the heuristic-based evaluation logic, including:
- Score calculation based on iterations and status
- Failure classification from test reports
- Root cause detection from stderr/stdout patterns
- Strategy recommendation generation
"""

import pytest

from genus.meta.evaluation_models import EvaluationInput
from genus.meta.evaluator import RunEvaluator
from genus.meta.taxonomy import (
    FailureClass,
    RootCauseHint,
    StrategyRecommendation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_test_report(exit_code=0, timed_out=False, stderr="", stdout=""):
    """Create a test report dict for testing."""
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_s": 5.0,
        "stderr_summary": stderr,
        "stdout_summary": stdout,
    }


# ---------------------------------------------------------------------------
# Test RunEvaluator - Completed Runs
# ---------------------------------------------------------------------------


class TestRunEvaluatorCompleted:
    """Test evaluation of successfully completed runs."""

    def test_completed_run_no_iterations_high_score(self):
        """Completed run with 0 iterations should have high score."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-1",
            final_status="completed",
            iterations_used=0,
            test_reports=[make_test_report(exit_code=0)],
        )

        artifact = evaluator.evaluate(eval_input)

        assert artifact.score == 100
        assert artifact.final_status == "completed"
        assert artifact.failure_class is None
        assert artifact.root_cause_hint is None
        assert len(artifact.highlights) > 0
        assert "without fix iterations" in str(artifact.highlights)

    def test_completed_run_with_iterations_lower_score(self):
        """Completed run with iterations should have lower score."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-2",
            final_status="completed",
            iterations_used=3,
            test_reports=[make_test_report(exit_code=0)],
        )

        artifact = evaluator.evaluate(eval_input)

        # Base 100 - (3 * 10) = 70
        assert artifact.score == 70
        assert artifact.final_status == "completed"
        assert "3 iteration" in str(artifact.issues)

    def test_completed_run_many_iterations_capped_penalty(self):
        """Many iterations should be capped at 50 point penalty."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-3",
            final_status="completed",
            iterations_used=10,
            test_reports=[make_test_report(exit_code=0)],
        )

        artifact = evaluator.evaluate(eval_input)

        # Base 100 - 50 (capped) = 50
        assert artifact.score == 50
        assert artifact.final_status == "completed"


# ---------------------------------------------------------------------------
# Test RunEvaluator - Failed Runs
# ---------------------------------------------------------------------------


class TestRunEvaluatorFailed:
    """Test evaluation of failed runs."""

    def test_failed_run_lowers_score(self):
        """Failed run should have significantly lower score."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-4",
            final_status="failed",
            iterations_used=0,
            test_reports=[make_test_report(exit_code=1)],
        )

        artifact = evaluator.evaluate(eval_input)

        # Base 100 - 40 (failure) - 20 (test failure) = 40
        assert artifact.score == 40
        assert artifact.final_status == "failed"
        assert artifact.failure_class == FailureClass.TEST_FAILURE

    def test_timeout_failure_detected(self):
        """Timeout should be detected and penalized."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-5",
            final_status="failed",
            iterations_used=0,
            test_reports=[make_test_report(timed_out=True)],
        )

        artifact = evaluator.evaluate(eval_input)

        # Base 100 - 40 (failure) - 25 (timeout) = 35
        assert artifact.score == 35
        assert artifact.failure_class == FailureClass.TIMEOUT
        assert "timed out" in str(artifact.issues).lower()

    def test_github_checks_failure_detected(self):
        """GitHub checks failure should be detected."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-6",
            final_status="failed",
            iterations_used=0,
            test_reports=[],  # No test reports
            github={"checks_summary": {"failing": 2, "passing": 0}},
        )

        artifact = evaluator.evaluate(eval_input)

        assert artifact.failure_class == FailureClass.GITHUB_CHECKS_FAILURE


# ---------------------------------------------------------------------------
# Test Root Cause Detection
# ---------------------------------------------------------------------------


class TestRootCauseDetection:
    """Test detection of root causes from test output."""

    def test_assertion_error_detected(self):
        """AssertionError should be detected in stderr."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-7",
            final_status="failed",
            iterations_used=0,
            test_reports=[make_test_report(
                exit_code=1,
                stderr="test_foo.py:42: AssertionError: expected 5, got 3"
            )],
        )

        artifact = evaluator.evaluate(eval_input)

        assert artifact.root_cause_hint == RootCauseHint.ASSERTION_ERROR

    def test_import_error_detected(self):
        """ImportError should be detected in stderr."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-8",
            final_status="failed",
            iterations_used=0,
            test_reports=[make_test_report(
                exit_code=1,
                stderr="ImportError: No module named 'foo'"
            )],
        )

        artifact = evaluator.evaluate(eval_input)

        assert artifact.root_cause_hint == RootCauseHint.IMPORT_ERROR

    def test_module_not_found_error_detected(self):
        """ModuleNotFoundError should be detected."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-9",
            final_status="failed",
            iterations_used=0,
            test_reports=[make_test_report(
                exit_code=1,
                stderr="ModuleNotFoundError: No module named 'bar'"
            )],
        )

        artifact = evaluator.evaluate(eval_input)

        assert artifact.root_cause_hint == RootCauseHint.IMPORT_ERROR

    def test_syntax_error_detected(self):
        """SyntaxError should be detected in stderr."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-10",
            final_status="failed",
            iterations_used=0,
            test_reports=[make_test_report(
                exit_code=1,
                stderr="SyntaxError: invalid syntax"
            )],
        )

        artifact = evaluator.evaluate(eval_input)

        assert artifact.root_cause_hint == RootCauseHint.SYNTAX_ERROR


# ---------------------------------------------------------------------------
# Test Strategy Recommendations
# ---------------------------------------------------------------------------


class TestStrategyRecommendations:
    """Test generation of strategy recommendations."""

    def test_assertion_error_recommends_target_test(self):
        """AssertionError should recommend targeting failing test."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-11",
            final_status="failed",
            iterations_used=0,
            test_reports=[make_test_report(
                exit_code=1,
                stderr="AssertionError: test failed"
            )],
        )

        artifact = evaluator.evaluate(eval_input)

        assert StrategyRecommendation.TARGET_FAILING_TEST_FIRST in artifact.strategy_recommendations
        assert StrategyRecommendation.MINIMIZE_CHANGESET in artifact.strategy_recommendations

    def test_timeout_recommends_increase_timeout(self):
        """Timeout should recommend increasing timeout."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-12",
            final_status="failed",
            iterations_used=0,
            test_reports=[make_test_report(timed_out=True)],
        )

        artifact = evaluator.evaluate(eval_input)

        assert StrategyRecommendation.INCREASE_TIMEOUT_ONCE in artifact.strategy_recommendations

    def test_many_iterations_recommends_operator_help(self):
        """Many iterations should recommend operator assistance."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-13",
            final_status="failed",
            iterations_used=5,
            test_reports=[make_test_report(exit_code=1)],
        )

        artifact = evaluator.evaluate(eval_input)

        assert StrategyRecommendation.ASK_OPERATOR_WITH_CONTEXT in artifact.strategy_recommendations


# ---------------------------------------------------------------------------
# Test Evidence Collection
# ---------------------------------------------------------------------------


class TestEvidenceCollection:
    """Test collection of evidence references."""

    def test_evidence_includes_failed_test_report(self):
        """Failed test report should be included in evidence."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-14",
            final_status="failed",
            iterations_used=0,
            test_reports=[
                make_test_report(exit_code=1, stderr="Error details here"),
            ],
        )

        artifact = evaluator.evaluate(eval_input)

        assert len(artifact.evidence) > 0
        assert artifact.evidence[0]["type"] == "test_report"
        assert artifact.evidence[0]["exit_code"] == 1

    def test_evidence_includes_timeout_info(self):
        """Timed out test should be included in evidence."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-15",
            final_status="failed",
            iterations_used=0,
            test_reports=[make_test_report(timed_out=True)],
        )

        artifact = evaluator.evaluate(eval_input)

        assert len(artifact.evidence) > 0
        assert artifact.evidence[0]["timed_out"] is True


# ---------------------------------------------------------------------------
# Test Score Boundaries
# ---------------------------------------------------------------------------


class TestScoreBoundaries:
    """Test that scores are properly bounded."""

    def test_score_never_negative(self):
        """Score should never go below 0."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-16",
            final_status="failed",
            iterations_used=10,  # -50
            test_reports=[make_test_report(timed_out=True)],  # -40 (fail) -25 (timeout)
        )

        artifact = evaluator.evaluate(eval_input)

        # 100 - 50 - 40 - 25 = -15, but should be capped at 0
        assert artifact.score >= 0
        assert artifact.score == 0

    def test_score_never_exceeds_100(self):
        """Score should never exceed 100."""
        evaluator = RunEvaluator()
        eval_input = EvaluationInput(
            run_id="test-run-17",
            final_status="completed",
            iterations_used=0,
            test_reports=[make_test_report(exit_code=0)],
        )

        artifact = evaluator.evaluate(eval_input)

        assert artifact.score <= 100
