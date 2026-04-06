"""
Tests for genus/dev/policy.py

Validates that should_ask_user returns the correct (ask, reason) tuple for
all policy rules.
"""

import pytest

from genus.dev.policy import should_ask_user


class TestShouldAskUserSecurityImpact:
    def test_security_impact_true_triggers_ask(self):
        ask, reason = should_ask_user([], [], scope_change=False, security_impact=True)
        assert ask is True

    def test_security_impact_true_provides_reason(self):
        _, reason = should_ask_user([], [], scope_change=False, security_impact=True)
        assert reason != ""

    def test_security_impact_overrides_no_other_triggers(self):
        ask, _ = should_ask_user([], [], scope_change=False, security_impact=True)
        assert ask is True


class TestShouldAskUserScopeChange:
    def test_scope_change_true_triggers_ask(self):
        ask, reason = should_ask_user([], [], scope_change=True, security_impact=False)
        assert ask is True

    def test_scope_change_true_provides_reason(self):
        _, reason = should_ask_user([], [], scope_change=True, security_impact=False)
        assert reason != ""

    def test_scope_change_false_alone_does_not_trigger(self):
        ask, _ = should_ask_user([], [], scope_change=False, security_impact=False)
        assert ask is False


class TestShouldAskUserHighSeverityFinding:
    def test_high_severity_triggers_ask(self):
        findings = [{"severity": "high", "message": "issue"}]
        ask, _ = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert ask is True

    def test_critical_severity_triggers_ask(self):
        findings = [{"severity": "critical", "message": "critical issue"}]
        ask, _ = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert ask is True

    def test_high_severity_provides_reason_containing_severity(self):
        findings = [{"severity": "high", "message": "x"}]
        _, reason = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert "high" in reason

    def test_medium_severity_does_not_trigger(self):
        findings = [{"severity": "medium", "message": "x"}]
        ask, _ = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert ask is False

    def test_low_severity_does_not_trigger(self):
        findings = [{"severity": "low", "message": "x"}]
        ask, _ = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert ask is False

    def test_info_severity_does_not_trigger(self):
        findings = [{"severity": "info", "message": "x"}]
        ask, _ = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert ask is False

    def test_none_severity_does_not_trigger(self):
        findings = [{"severity": "none", "message": "x"}]
        ask, _ = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert ask is False

    def test_unknown_severity_does_not_trigger(self):
        findings = [{"severity": "unknown_xyz", "message": "x"}]
        ask, _ = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert ask is False

    def test_missing_severity_key_does_not_trigger(self):
        findings = [{"message": "no severity key"}]
        ask, _ = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert ask is False

    def test_severity_comparison_is_case_insensitive(self):
        findings = [{"severity": "HIGH", "message": "x"}]
        ask, _ = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert ask is True

    def test_multiple_findings_one_high_triggers(self):
        findings = [
            {"severity": "low", "message": "minor"},
            {"severity": "high", "message": "major"},
        ]
        ask, _ = should_ask_user(findings, [], scope_change=False, security_impact=False)
        assert ask is True


class TestShouldAskUserNoAsk:
    def test_no_triggers_returns_false(self):
        ask, reason = should_ask_user([], [], scope_change=False, security_impact=False)
        assert ask is False
        assert reason == ""

    def test_empty_findings_no_ask(self):
        ask, _ = should_ask_user([], [], scope_change=False, security_impact=False)
        assert ask is False

    def test_risks_list_alone_does_not_trigger(self):
        risks = [{"description": "some risk"}]
        ask, _ = should_ask_user([], risks, scope_change=False, security_impact=False)
        assert ask is False


class TestShouldAskUserReturnType:
    def test_returns_tuple(self):
        result = should_ask_user([], [], scope_change=False, security_impact=False)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_bool(self):
        ask, _ = should_ask_user([], [], scope_change=False, security_impact=False)
        assert isinstance(ask, bool)

    def test_second_element_is_str(self):
        _, reason = should_ask_user([], [], scope_change=False, security_impact=False)
        assert isinstance(reason, str)
