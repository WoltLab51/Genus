"""Unit tests for DevContextExtractor — Phase 13c."""

import pytest

from genus.conversation.dev_context_extractor import DevRunContext, extract_dev_context


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _Profile:
    def __init__(
        self,
        display_name="Ronny",
        projects=None,
        decisions=None,
    ):
        self.display_name = display_name
        self.projects = projects or []
        self.decisions = decisions or []


# ---------------------------------------------------------------------------
# Tests — without profile / history
# ---------------------------------------------------------------------------


class TestExtractDevContextMinimal:
    def test_returns_devruncontext(self):
        result = extract_dev_context("Bau einen Agent")
        assert isinstance(result, DevRunContext)

    def test_goal_preserved(self):
        result = extract_dev_context("Implementiere einen Logger")
        assert result.goal == "Implementiere einen Logger"

    def test_no_profile_empty_requirements(self):
        result = extract_dev_context("Bau etwas")
        assert result.requirements == []

    def test_no_profile_empty_constraints(self):
        result = extract_dev_context("Bau etwas")
        assert result.constraints == []

    def test_no_history_empty_summary(self):
        result = extract_dev_context("Bau etwas")
        assert result.conversation_summary == ""


# ---------------------------------------------------------------------------
# Tests — with profile
# ---------------------------------------------------------------------------


class TestExtractDevContextWithProfile:
    def test_projects_become_requirement(self):
        profile = _Profile(projects=["GENUS", "Solar"])
        result = extract_dev_context("Bau etwas", profile=profile)
        assert any("GENUS" in r for r in result.requirements)
        assert any("Solar" in r for r in result.requirements)

    def test_decisions_become_constraints(self):
        decisions = [
            {"entscheidung": "kein Redis", "grund": "Pi zu klein"},
            {"entscheidung": "kein Docker"},
        ]
        profile = _Profile(decisions=decisions)
        result = extract_dev_context("Bau etwas", profile=profile)
        assert any("kein Redis" in c for c in result.constraints)
        assert any("kein Docker" in c for c in result.constraints)

    def test_decisions_include_grund(self):
        decisions = [{"entscheidung": "kein Redis", "grund": "Pi zu klein"}]
        profile = _Profile(decisions=decisions)
        result = extract_dev_context("Bau etwas", profile=profile)
        assert any("Pi zu klein" in c for c in result.constraints)

    def test_max_three_decisions(self):
        decisions = [
            {"entscheidung": f"Entscheidung-{i}"} for i in range(5)
        ]
        profile = _Profile(decisions=decisions)
        result = extract_dev_context("Bau etwas", profile=profile)
        # Only last 3 decisions
        assert len(result.constraints) == 3

    def test_no_projects_no_requirement(self):
        profile = _Profile(projects=[])
        result = extract_dev_context("Bau etwas", profile=profile)
        assert result.requirements == []


# ---------------------------------------------------------------------------
# Tests — with conversation history
# ---------------------------------------------------------------------------


class TestExtractDevContextWithHistory:
    def test_summary_includes_last_five_messages(self):
        history = [
            {"role": "user", "content": f"Nachricht {i}"}
            for i in range(7)
        ]
        result = extract_dev_context("Bau etwas", conversation_history=history)
        # Only last 5 should appear (indices 2–6)
        assert "Nachricht 1" not in result.conversation_summary
        assert "Nachricht 0" not in result.conversation_summary
        assert "Nachricht 6" in result.conversation_summary

    def test_summary_labels_assistant_as_genus(self):
        history = [{"role": "assistant", "content": "Hallo!"}]
        result = extract_dev_context("Bau etwas", conversation_history=history)
        assert "GENUS" in result.conversation_summary

    def test_summary_labels_user_with_display_name(self):
        profile = _Profile(display_name="Ronny")
        history = [{"role": "user", "content": "Hallo GENUS"}]
        result = extract_dev_context("Bau etwas", profile=profile, conversation_history=history)
        assert "Ronny" in result.conversation_summary

    def test_summary_labels_user_without_profile(self):
        history = [{"role": "user", "content": "Hallo"}]
        result = extract_dev_context("Bau etwas", conversation_history=history)
        assert "User" in result.conversation_summary

    def test_summary_truncates_long_messages(self):
        long_content = "A" * 200
        history = [{"role": "user", "content": long_content}]
        result = extract_dev_context("Bau etwas", conversation_history=history)
        # Content is truncated to 100 chars
        assert len(result.conversation_summary) < 200

    def test_empty_history_empty_summary(self):
        result = extract_dev_context("Bau etwas", conversation_history=[])
        assert result.conversation_summary == ""
