"""
Tests for ToolRegistry role-guard on replace=True

Verifies:
- replace=True + actor_role="ADMIN" → no error
- replace=True + actor_role=None → PermissionError
- replace=True + actor_role="OPERATOR" → PermissionError
- replace=False + actor_role=None → no error (standard behavior unchanged)
"""

import pytest

from genus.tools.registry import ToolRegistry, ToolSpec


def _handler():
    pass


def _spec(name: str = "tool") -> ToolSpec:
    return ToolSpec(name=name, handler=_handler, description="Test")


class TestToolRegistryRoleGuard:
    def test_replace_admin_succeeds(self):
        """replace=True with actor_role='ADMIN' must not raise."""
        registry = ToolRegistry()
        registry.register(_spec())
        # Should not raise
        registry.register(_spec(), replace=True, actor_role="ADMIN")
        assert registry.get("tool") is not None

    def test_replace_none_role_raises_permission_error(self):
        """replace=True with actor_role=None must raise PermissionError."""
        registry = ToolRegistry()
        registry.register(_spec())
        with pytest.raises(PermissionError):
            registry.register(_spec(), replace=True, actor_role=None)

    def test_replace_operator_role_raises_permission_error(self):
        """replace=True with actor_role='OPERATOR' must raise PermissionError."""
        registry = ToolRegistry()
        registry.register(_spec())
        with pytest.raises(PermissionError):
            registry.register(_spec(), replace=True, actor_role="OPERATOR")

    def test_replace_false_no_role_succeeds_for_new_tool(self):
        """replace=False (default) with no actor_role must not raise for new tools."""
        registry = ToolRegistry()
        # Should not raise — standard registration
        registry.register(_spec(), actor_role=None)
        assert registry.get("tool") is not None

    def test_role_check_before_duplicate_check(self):
        """PermissionError must be raised even if tool is not yet registered."""
        registry = ToolRegistry()
        # Tool not registered yet — but replace=True + bad role should still fail
        with pytest.raises(PermissionError):
            registry.register(_spec(), replace=True, actor_role="OPERATOR")

    def test_replace_false_duplicate_still_raises_value_error(self):
        """replace=False duplicate must still raise ValueError (behavior unchanged)."""
        registry = ToolRegistry()
        registry.register(_spec())
        with pytest.raises(ValueError):
            registry.register(_spec())  # replace defaults to False

    def test_permission_error_message_contains_role_and_name(self):
        """PermissionError message must mention the attempted role and tool name."""
        registry = ToolRegistry()
        registry.register(_spec("my_tool"))
        with pytest.raises(PermissionError) as exc_info:
            registry.register(_spec("my_tool"), replace=True, actor_role="USER")
        msg = str(exc_info.value)
        assert "ADMIN" in msg
        assert "my_tool" in msg
