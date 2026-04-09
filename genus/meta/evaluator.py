"""
Run Evaluator - Heuristic-based Evaluation

Implements deterministic heuristics for scoring runs and generating
recommendations. No ML, no external services, no network calls.

The evaluator analyzes run artifacts and events to produce an evaluation
artifact with scores, failure classifications, and actionable recommendations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from genus.meta.evaluation_models import EvaluationArtifact, EvaluationInput
from genus.meta.taxonomy import FailureClass, RootCauseHint, StrategyRecommendation


class RunEvaluator:
    """Evaluates a run and produces an evaluation artifact.

    Uses deterministic heuristics to score runs and generate recommendations.
    All logic is explainable and transparent.

    Usage::

        evaluator = RunEvaluator()
        input_data = EvaluationInput(
            run_id="run-123",
            final_status="completed",
            iterations_used=3,
            test_reports=[...],
        )
        artifact = evaluator.evaluate(input_data)
        # artifact.score, artifact.failure_class, etc.
    """

    def evaluate(self, inp: EvaluationInput) -> EvaluationArtifact:
        """Evaluate a run and produce an evaluation artifact.

        Args:
            inp: The evaluation input data.

        Returns:
            An EvaluationArtifact with scores, classifications, and recommendations.
        """
        # Start with base score
        score = 100

        # Track issues and highlights
        issues = []
        highlights = []
        evidence = []

        # Deduct points for iterations used
        iteration_penalty = min(inp.iterations_used * 10, 50)
        score -= iteration_penalty
        if inp.iterations_used > 0:
            issues.append(f"Used {inp.iterations_used} iteration(s) to complete")
        if inp.iterations_used == 0:
            highlights.append("Completed without fix iterations")
        elif inp.iterations_used == 1:
            highlights.append("Completed after one fix iteration")

        # Determine failure class and root cause
        failure_class = None
        root_cause_hint = None

        if inp.final_status == "failed":
            # Major penalty for failure
            score -= 40
            issues.append("Run failed to complete successfully")

            # Determine failure class from test reports
            failure_class, root_cause_hint = self._classify_failure(
                inp.test_reports, inp.github
            )

            # Additional penalties based on failure type
            if failure_class == FailureClass.TIMEOUT:
                score -= 25
                issues.append("Execution timed out")
            elif failure_class == FailureClass.TEST_FAILURE:
                score -= 20
                issues.append("Tests failed")
            elif failure_class == FailureClass.GITHUB_CHECKS_FAILURE:
                score -= 20
                issues.append("GitHub checks failed")

        else:
            # Highlight successful completion
            highlights.append("Run completed successfully")

            # Still check for test issues even on success
            for report in inp.test_reports:
                if report.get("exit_code") == 0:
                    highlights.append("All tests passed")
                    break

        # Cap score at 0-100 range
        score = max(0, min(100, score))

        # Generate recommendations
        recommendations, strategy_recommendations = self._generate_recommendations(
            failure_class=failure_class,
            root_cause_hint=root_cause_hint,
            iterations_used=inp.iterations_used,
            final_status=inp.final_status,
            tool_context=inp.tool_context,
        )

        # Build evidence from test reports
        for idx, report in enumerate(inp.test_reports):
            if report.get("exit_code") != 0 or report.get("timed_out"):
                evidence.append({
                    "type": "test_report",
                    "index": idx,
                    "exit_code": report.get("exit_code"),
                    "timed_out": report.get("timed_out"),
                    "stderr_summary": report.get("stderr_summary", "")[:200],
                })

        # Create evaluation artifact
        artifact = EvaluationArtifact(
            run_id=inp.run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            score=score,
            final_status=inp.final_status,
            failure_class=failure_class,
            root_cause_hint=root_cause_hint,
            highlights=highlights,
            issues=issues,
            recommendations=recommendations,
            strategy_recommendations=strategy_recommendations,
            evidence=evidence,
        )

        return artifact

    def _classify_failure(
        self,
        test_reports: List[Dict[str, Any]],
        github: Optional[Dict[str, Any]],
    ) -> tuple:
        """Classify failure type and determine root cause hint.

        Args:
            test_reports: List of test report artifacts.
            github: Optional GitHub context.

        Returns:
            Tuple of (failure_class, root_cause_hint).
        """
        failure_class = FailureClass.UNKNOWN
        root_cause_hint = RootCauseHint.UNKNOWN

        # Check test reports first
        for report in test_reports:
            # Check for timeout
            if report.get("timed_out"):
                failure_class = FailureClass.TIMEOUT
                break

            # Check for test failure
            if report.get("exit_code") != 0:
                failure_class = FailureClass.TEST_FAILURE

                # Scan stderr/stdout for root cause patterns
                root_cause_hint = self._detect_root_cause(
                    report.get("stderr_summary", ""),
                    report.get("stdout_summary", ""),
                )
                break

        # Check GitHub checks if no test failure detected
        if failure_class == FailureClass.UNKNOWN and github:
            checks = github.get("checks_summary", {})
            if checks.get("failing", 0) > 0:
                failure_class = FailureClass.GITHUB_CHECKS_FAILURE

        return failure_class, root_cause_hint

    def _detect_root_cause(self, stderr: str, stdout: str) -> str:
        """Detect root cause from stderr/stdout patterns.

        Args:
            stderr: Standard error output.
            stdout: Standard output.

        Returns:
            Root cause hint constant.
        """
        combined = stderr + "\n" + stdout

        # Check for specific error patterns
        if "AssertionError" in combined:
            return RootCauseHint.ASSERTION_ERROR

        if "ImportError" in combined or "ModuleNotFoundError" in combined:
            return RootCauseHint.IMPORT_ERROR

        if "SyntaxError" in combined:
            return RootCauseHint.SYNTAX_ERROR

        # Could add more patterns here in future versions

        return RootCauseHint.UNKNOWN

    def _generate_recommendations(
        self,
        failure_class: Optional[str],
        root_cause_hint: Optional[str],
        iterations_used: int,
        final_status: str,
        tool_context: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """Generate human-readable and machine-readable recommendations.

        Args:
            failure_class: The classified failure class.
            root_cause_hint: The detected root cause hint.
            iterations_used: Number of iterations used.
            final_status: Final status of the run.
            tool_context: Optional tool usage context from EvaluationInput.

        Returns:
            Tuple of (recommendations, strategy_recommendations).
        """
        recommendations = []
        strategy_recommendations = []

        # Recommendations for successful runs
        if final_status == "completed":
            if iterations_used == 0:
                recommendations.append("Great work! Completed on first try.")
            elif iterations_used <= 2:
                recommendations.append("Good job! Completed with minimal iterations.")
            else:
                recommendations.append(
                    "Consider analyzing why multiple iterations were needed."
                )

        else:
            # Recommendations for failed runs
            if failure_class == FailureClass.TEST_FAILURE:
                if root_cause_hint == RootCauseHint.ASSERTION_ERROR:
                    recommendations.append(
                        "Focus on fixing the specific failing assertion(s)."
                    )
                    strategy_recommendations.append(
                        StrategyRecommendation.TARGET_FAILING_TEST_FIRST
                    )
                    strategy_recommendations.append(
                        StrategyRecommendation.MINIMIZE_CHANGESET
                    )
                elif root_cause_hint == RootCauseHint.IMPORT_ERROR:
                    recommendations.append(
                        "Check for missing dependencies or incorrect imports."
                    )
                elif root_cause_hint == RootCauseHint.SYNTAX_ERROR:
                    recommendations.append("Fix syntax errors before proceeding.")
                else:
                    recommendations.append("Review test output to identify root cause.")
                    strategy_recommendations.append(
                        StrategyRecommendation.TARGET_FAILING_TEST_FIRST
                    )

            elif failure_class == FailureClass.TIMEOUT:
                recommendations.append(
                    "Execution timed out. Consider increasing timeout or optimizing code."
                )
                strategy_recommendations.append(
                    StrategyRecommendation.INCREASE_TIMEOUT_ONCE
                )

            elif failure_class == FailureClass.GITHUB_CHECKS_FAILURE:
                recommendations.append("Review GitHub checks for specific failures.")

            # General recommendation for repeated failures
            if iterations_used > 3:
                recommendations.append(
                    "Multiple iterations suggest a complex issue. "
                    "Consider requesting operator assistance."
                )
                strategy_recommendations.append(
                    StrategyRecommendation.ASK_OPERATOR_WITH_CONTEXT
                )

            # Fallback recommendation
            if not recommendations:
                recommendations.append("Review run artifacts for diagnostic information.")
                strategy_recommendations.append(
                    StrategyRecommendation.ASK_OPERATOR_WITH_CONTEXT
                )

        # -- Tool-Context-Analyse (falls vorhanden) --
        if tool_context is not None:
            tool_insights = self._analyze_tool_context(tool_context)
            recommendations.extend(tool_insights["recommendations"])
            strategy_recommendations.extend(tool_insights["strategy_recommendations"])

        return recommendations, strategy_recommendations

    def _analyze_tool_context(
        self,
        tool_context: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        """Analyse tool usage patterns and derive recommendations.

        Heuristics:
        - sandbox_run called 0 times in fix phase (but indexed_run_count >= 3)
          → "verify_sandbox_tool_usage" recommendation
        - No tools recorded in fix phase at all (top_tools_fix is empty,
          but indexed_run_count >= 3)
          → "review_tool_selection" recommendation
        - sandbox_run calls_in_phase > 0 but < 2 on average per run
          (calls_in_phase / indexed_run_count < 0.5, indexed_run_count >= 5)
          → "verify_sandbox_tool_usage" recommendation (low sandbox usage signal)

        Args:
            tool_context: Dict with "top_tools_fix" and "indexed_run_count".

        Returns:
            Dict with "recommendations" (List[str]) and
            "strategy_recommendations" (List[str]).
        """
        recommendations = []
        strategy_recommendations = []

        top_tools_fix = tool_context.get("top_tools_fix", [])
        indexed_run_count = tool_context.get("indexed_run_count", 0)

        # Only apply heuristics if we have enough history
        if indexed_run_count < 3:
            return {"recommendations": recommendations, "strategy_recommendations": strategy_recommendations}

        tool_names_in_fix = {t["tool_name"] for t in top_tools_fix}

        # Heuristic 1: No tools at all in fix phase
        if not top_tools_fix:
            recommendations.append(
                "No tools were recorded in the fix phase across recent runs. "
                "Review tool selection logic."
            )
            strategy_recommendations.append(StrategyRecommendation.REVIEW_TOOL_SELECTION)
            return {"recommendations": recommendations, "strategy_recommendations": strategy_recommendations}

        # Heuristic 2: sandbox_run completely absent in fix phase
        if "sandbox_run" not in tool_names_in_fix:
            recommendations.append(
                "sandbox_run was not used in the fix phase across recent runs. "
                "Verify that the Sandbox is being utilized during fix iterations."
            )
            strategy_recommendations.append(StrategyRecommendation.VERIFY_SANDBOX_TOOL_USAGE)
            return {"recommendations": recommendations, "strategy_recommendations": strategy_recommendations}

        # Heuristic 3: sandbox_run present but low usage rate
        if indexed_run_count >= 5:
            sandbox_stat = next(
                (t for t in top_tools_fix if t["tool_name"] == "sandbox_run"), None
            )
            if sandbox_stat is not None:
                usage_rate = sandbox_stat["calls_in_phase"] / indexed_run_count
                if usage_rate < 0.5:
                    recommendations.append(
                        f"sandbox_run usage rate in fix phase is low "
                        f"({sandbox_stat['calls_in_phase']} calls across "
                        f"{indexed_run_count} runs). "
                        "Verify Sandbox is being used effectively."
                    )
                    strategy_recommendations.append(
                        StrategyRecommendation.VERIFY_SANDBOX_TOOL_USAGE
                    )

        return {"recommendations": recommendations, "strategy_recommendations": strategy_recommendations}
