"""Unit tests for format_episodic_for_planner — Phase 13c."""

import pytest

from genus.dev.context_formatter import format_episodic_for_planner


# ---------------------------------------------------------------------------
# Tests — empty / None input
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_empty_list_returns_none(self):
        assert format_episodic_for_planner([]) is None

    def test_returns_none_not_empty_string(self):
        result = format_episodic_for_planner([])
        assert result is None


# ---------------------------------------------------------------------------
# Tests — basic formatting
# ---------------------------------------------------------------------------


class TestBasicFormatting:
    def test_returns_string_for_valid_runs(self):
        runs = [{"goal": "Fix bug"}]
        result = format_episodic_for_planner(runs)
        assert isinstance(result, str)

    def test_contains_header(self):
        runs = [{"goal": "Fix bug"}]
        result = format_episodic_for_planner(runs)
        assert result.startswith("Vorherige Runs:")

    def test_goal_included(self):
        runs = [{"goal": "Fix the login bug"}]
        result = format_episodic_for_planner(runs)
        assert "Fix the login bug" in result

    def test_outcome_included_when_present(self):
        runs = [{"goal": "Fix bug", "feedback": {"outcome": "success"}}]
        result = format_episodic_for_planner(runs)
        assert "success" in result

    def test_failure_class_included(self):
        runs = [
            {
                "goal": "Fix bug",
                "feedback": {"outcome": "failure"},
                "evaluation": {"failure_class": "test_failure"},
            }
        ]
        result = format_episodic_for_planner(runs)
        assert "test_failure" in result

    def test_missing_feedback_no_error(self):
        runs = [{"goal": "Fix bug", "feedback": None}]
        result = format_episodic_for_planner(runs)
        assert result is not None

    def test_missing_evaluation_no_error(self):
        runs = [{"goal": "Fix bug"}]
        result = format_episodic_for_planner(runs)
        assert result is not None

    def test_each_run_on_separate_line(self):
        runs = [{"goal": "Run A"}, {"goal": "Run B"}]
        result = format_episodic_for_planner(runs)
        assert "Run A" in result
        assert "Run B" in result
        assert result.count("- ") >= 2


# ---------------------------------------------------------------------------
# Tests — token budget
# ---------------------------------------------------------------------------


class TestTokenBudget:
    def test_respects_budget(self):
        # Each run goal = "Run N..." — roughly 5-10 tokens per line
        runs = [{"goal": f"Run {i}: " + "word " * 20} for i in range(10)]
        result = format_episodic_for_planner(runs, max_tokens_budget=50)
        # Should be truncated
        assert result is not None
        lines = [l for l in result.split("\n") if l.strip().startswith("-")]
        assert len(lines) < 10

    def test_default_budget_is_pi_safe(self):
        # Default budget of 500 tokens should accept reasonable runs
        runs = [{"goal": "short goal"} for _ in range(20)]
        result = format_episodic_for_planner(runs)
        assert result is not None

    def test_zero_budget_returns_none_or_minimal(self):
        runs = [{"goal": "word " * 100}]  # very long goal
        result = format_episodic_for_planner(runs, max_tokens_budget=1)
        # Token estimate for 100-word goal exceeds budget → no lines fit
        assert result is None

    def test_large_budget_includes_all_runs(self):
        runs = [{"goal": f"Ziel {i}"} for i in range(5)]
        result = format_episodic_for_planner(runs, max_tokens_budget=10_000)
        for i in range(5):
            assert f"Ziel {i}" in result
