"""
Unit Tests — AgentCodeTemplate

Tests for :class:`~genus.dev.agents.agent_code_template.AgentCodeTemplate`
and helper functions.
"""

from __future__ import annotations

import ast

import pytest

from genus.dev.agents.agent_code_template import (
    AgentCodeTemplate,
    class_name_to_filename,
    extract_class_name,
    extract_subscribe_topics,
)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestClassNameToFilename:
    def test_family_calendar_agent(self) -> None:
        assert class_name_to_filename("FamilyCalendarAgent") == "family_calendar_agent"

    def test_system_agent(self) -> None:
        assert class_name_to_filename("SystemAgent") == "system_agent"

    def test_single_word(self) -> None:
        assert class_name_to_filename("Agent") == "agent"

    def test_multiple_words(self) -> None:
        assert class_name_to_filename("MyComplexAgentName") == "my_complex_agent_name"


class TestExtractClassName:
    def test_uses_name_from_template(self) -> None:
        assert extract_class_name({"name": "FooAgent"}, "family") == "FooAgent"

    def test_derives_from_domain_when_no_name(self) -> None:
        assert extract_class_name({}, "family") == "FamilyAgent"

    def test_derives_from_domain_empty_string(self) -> None:
        assert extract_class_name({"name": ""}, "finance") == "FinanceAgent"

    def test_strips_whitespace_from_name(self) -> None:
        assert extract_class_name({"name": "  BarAgent  "}, "x") == "BarAgent"

    def test_capitalises_domain_correctly(self) -> None:
        assert extract_class_name({}, "health") == "HealthAgent"


class TestExtractSubscribeTopics:
    def test_returns_topics_list(self) -> None:
        tmpl = {"topics": ["family.calendar.requested", "family.event.created"]}
        result = extract_subscribe_topics(tmpl)
        assert result == ["family.calendar.requested", "family.event.created"]

    def test_returns_empty_when_no_topics_key(self) -> None:
        assert extract_subscribe_topics({}) == []

    def test_returns_empty_when_topics_not_list(self) -> None:
        assert extract_subscribe_topics({"topics": "not-a-list"}) == []

    def test_filters_non_string_items(self) -> None:
        result = extract_subscribe_topics({"topics": ["valid.topic", 42, None, "another.topic"]})
        assert result == ["valid.topic", "another.topic"]


# ---------------------------------------------------------------------------
# AgentCodeTemplate.render() tests
# ---------------------------------------------------------------------------

class TestAgentCodeTemplateRender:
    def _make_template(
        self,
        class_name: str = "FamilyCalendarAgent",
        domain: str = "family",
        need_description: str = "missing_calendar_reminders",
        subscribe_topics=None,
    ) -> AgentCodeTemplate:
        return AgentCodeTemplate(
            class_name=class_name,
            domain=domain,
            need_description=need_description,
            subscribe_topics=subscribe_topics or [],
        )

    def test_render_returns_string(self) -> None:
        tmpl = self._make_template()
        assert isinstance(tmpl.render(), str)

    def test_render_contains_class_name(self) -> None:
        tmpl = self._make_template(class_name="FamilyCalendarAgent")
        code = tmpl.render()
        assert "FamilyCalendarAgent" in code

    def test_render_contains_domain(self) -> None:
        tmpl = self._make_template(domain="family")
        code = tmpl.render()
        assert "family" in code

    def test_render_contains_domain_constant(self) -> None:
        tmpl = self._make_template(domain="family")
        code = tmpl.render()
        assert 'DOMAIN = "family"' in code

    def test_render_contains_need_constant(self) -> None:
        tmpl = self._make_template(need_description="missing_calendar_reminders")
        code = tmpl.render()
        assert 'NEED = "missing_calendar_reminders"' in code

    def test_empty_subscribe_topics_no_subscribe_call(self) -> None:
        tmpl = self._make_template(subscribe_topics=[])
        code = tmpl.render()
        assert "self._bus.subscribe" not in code

    def test_single_topic_one_subscribe_call(self) -> None:
        tmpl = self._make_template(subscribe_topics=["family.calendar.requested"])
        code = tmpl.render()
        assert code.count("self._bus.subscribe") == 1
        assert '"family.calendar.requested"' in code

    def test_multiple_topics_multiple_subscribe_calls(self) -> None:
        topics = ["family.calendar.requested", "family.event.created", "family.reminder.needed"]
        tmpl = self._make_template(subscribe_topics=topics)
        code = tmpl.render()
        assert code.count("self._bus.subscribe") == 3
        for topic in topics:
            assert f'"{topic}"' in code

    def test_rendered_code_is_syntactically_valid(self) -> None:
        tmpl = self._make_template(subscribe_topics=["family.calendar.requested"])
        code = tmpl.render()
        # Should not raise
        ast.parse(code)

    def test_rendered_code_no_topics_is_syntactically_valid(self) -> None:
        tmpl = self._make_template(subscribe_topics=[])
        code = tmpl.render()
        ast.parse(code)

    def test_version_constant_present(self) -> None:
        tmpl = AgentCodeTemplate(
            class_name="TestAgent",
            domain="test",
            need_description="test_need",
            version=3,
        )
        code = tmpl.render()
        assert "VERSION = 3" in code

    def test_default_generated_by_in_docstring(self) -> None:
        tmpl = self._make_template()
        code = tmpl.render()
        assert "GENUS-BuilderAgent" in code
