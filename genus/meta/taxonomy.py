"""
Failure Taxonomy and Strategy Recommendations

Provides a stable, deterministic classification system for run failures
and recommended strategies. This is v1 - kept simple and explainable.

All enums are string-based for easy serialization and human-readability.
"""


# ---------------------------------------------------------------------------
# Failure Classification
# ---------------------------------------------------------------------------

class FailureClass:
    """High-level failure classification.

    Used to categorize what went wrong during a run. These are mutually
    exclusive categories that help determine the appropriate response strategy.
    """
    TEST_FAILURE = "test_failure"
    """Tests ran but some failed (exit_code != 0)."""

    LINT_FAILURE = "lint_failure"
    """Linting checks failed (optional for v1)."""

    TIMEOUT = "timeout"
    """Execution timed out before completion."""

    GITHUB_CHECKS_FAILURE = "github_checks_failure"
    """GitHub checks (CI/CD) failed."""

    POLICY_BLOCKED = "policy_blocked"
    """Sandbox policy or safety policy blocked execution."""

    UNKNOWN = "unknown"
    """Failure classification could not be determined."""

    @classmethod
    def all_values(cls):
        """Return all failure class values."""
        return [
            cls.TEST_FAILURE,
            cls.LINT_FAILURE,
            cls.TIMEOUT,
            cls.GITHUB_CHECKS_FAILURE,
            cls.POLICY_BLOCKED,
            cls.UNKNOWN,
        ]


# ---------------------------------------------------------------------------
# Root Cause Hints
# ---------------------------------------------------------------------------

class RootCauseHint:
    """More specific hints about the root cause of a failure.

    Derived from scanning stderr/stdout for common error patterns.
    These are optional and provide additional context beyond the failure class.
    """
    ASSERTION_ERROR = "assertion_error"
    """Test assertion failed (AssertionError in stderr/stdout)."""

    IMPORT_ERROR = "import_error"
    """Import or module not found error."""

    SYNTAX_ERROR = "syntax_error"
    """Python syntax error."""

    FLAKY_TEST_SUSPECTED = "flaky_test_suspected"
    """Test behavior suggests flakiness (optional for v1)."""

    ENV_MISSING_DEPENDENCY = "env_missing_dependency"
    """Missing dependency or environment issue."""

    UNKNOWN = "unknown"
    """Root cause could not be determined."""

    @classmethod
    def all_values(cls):
        """Return all root cause hint values."""
        return [
            cls.ASSERTION_ERROR,
            cls.IMPORT_ERROR,
            cls.SYNTAX_ERROR,
            cls.FLAKY_TEST_SUSPECTED,
            cls.ENV_MISSING_DEPENDENCY,
            cls.UNKNOWN,
        ]


# ---------------------------------------------------------------------------
# Strategy Recommendations
# ---------------------------------------------------------------------------

class StrategyRecommendation:
    """Machine-readable strategy recommendations.

    These recommendations are consumed by future strategy layers (PR #32+).
    They suggest what approach should be taken next based on the evaluation.
    """
    TARGET_FAILING_TEST_FIRST = "target_failing_test_first"
    """Focus next iteration on fixing the specific failing test(s)."""

    MINIMIZE_CHANGESET = "minimize_changeset"
    """Reduce the scope of changes in next iteration."""

    INCREASE_TIMEOUT_ONCE = "increase_timeout_once"
    """Increase timeout and retry once (for timeout failures)."""

    REVERT_LAST_COMMIT_AND_RETRY = "revert_last_commit_and_retry"
    """Last commit may have introduced regression (optional for v1)."""

    ASK_OPERATOR_WITH_CONTEXT = "ask_operator_with_context"
    """Situation requires human intervention with full context."""

    @classmethod
    def all_values(cls):
        """Return all strategy recommendation values."""
        return [
            cls.TARGET_FAILING_TEST_FIRST,
            cls.MINIMIZE_CHANGESET,
            cls.INCREASE_TIMEOUT_ONCE,
            cls.REVERT_LAST_COMMIT_AND_RETRY,
            cls.ASK_OPERATOR_WITH_CONTEXT,
        ]
