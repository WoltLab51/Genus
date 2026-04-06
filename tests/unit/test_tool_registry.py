"""
Tests for the ToolRegistry.

Verifies:
- Registration and lookup of tools
- Unknown tools return None (deny by default)
- Overwrite behavior (deny by default, allow with replace=True)
- list_names() returns sorted tool names
"""

import pytest

from genus.tools.registry import ToolRegistry, ToolSpec


# ---------------------------------------------------------------------------
# Helper functions for testing
# ---------------------------------------------------------------------------

def dummy_tool(x: int) -> int:
    """A simple dummy tool for testing."""
    return x * 2


def another_tool(message: str) -> str:
    """Another dummy tool."""
    return message.upper()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToolRegistry:

    def test_register_and_get(self):
        """Test basic registration and retrieval."""
        registry = ToolRegistry()
        spec = ToolSpec(name="dummy", handler=dummy_tool, description="Test tool")

        registry.register(spec)
        retrieved = registry.get("dummy")

        assert retrieved is not None
        assert retrieved.name == "dummy"
        assert retrieved.handler is dummy_tool
        assert retrieved.description == "Test tool"

    def test_get_unknown_tool_returns_none(self):
        """Unknown tools should return None (deny by default)."""
        registry = ToolRegistry()
        result = registry.get("nonexistent")
        assert result is None

    def test_register_duplicate_raises_error(self):
        """Registering the same tool name twice should raise ValueError."""
        registry = ToolRegistry()
        spec1 = ToolSpec(name="tool1", handler=dummy_tool)
        spec2 = ToolSpec(name="tool1", handler=another_tool)

        registry.register(spec1)

        with pytest.raises(ValueError) as exc_info:
            registry.register(spec2)

        assert "already registered" in str(exc_info.value).lower()
        assert "tool1" in str(exc_info.value)

    def test_register_with_replace_true(self):
        """Registering with replace=True should allow overwriting."""
        registry = ToolRegistry()
        spec1 = ToolSpec(name="tool1", handler=dummy_tool, description="First")
        spec2 = ToolSpec(name="tool1", handler=another_tool, description="Second")

        registry.register(spec1)
        registry.register(spec2, replace=True)

        retrieved = registry.get("tool1")
        assert retrieved is not None
        assert retrieved.handler is another_tool
        assert retrieved.description == "Second"

    def test_list_names_empty(self):
        """list_names() should return an empty list for an empty registry."""
        registry = ToolRegistry()
        assert registry.list_names() == []

    def test_list_names_single_tool(self):
        """list_names() should return a list with one tool name."""
        registry = ToolRegistry()
        spec = ToolSpec(name="echo", handler=dummy_tool)
        registry.register(spec)

        assert registry.list_names() == ["echo"]

    def test_list_names_multiple_tools_sorted(self):
        """list_names() should return a sorted list of tool names."""
        registry = ToolRegistry()
        registry.register(ToolSpec(name="zebra", handler=dummy_tool))
        registry.register(ToolSpec(name="apple", handler=dummy_tool))
        registry.register(ToolSpec(name="mango", handler=dummy_tool))

        assert registry.list_names() == ["apple", "mango", "zebra"]

    def test_toolspec_description_optional(self):
        """ToolSpec description should default to empty string."""
        spec = ToolSpec(name="test", handler=dummy_tool)
        assert spec.description == ""

    def test_toolspec_with_description(self):
        """ToolSpec should allow setting a description."""
        spec = ToolSpec(
            name="test",
            handler=dummy_tool,
            description="A test tool"
        )
        assert spec.description == "A test tool"
