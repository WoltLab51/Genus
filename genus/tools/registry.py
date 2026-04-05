"""
Tool Registry

Provides a central registry and whitelist for GENUS tools. The ToolRegistry
manages tool registration, lookup, and maintains a deny-by-default policy.

Design principles:
- Tools are small, testable units (sync or async callables)
- Registry enforces a whitelist (unknown tools return None)
- No dependencies on Redis or IO
- Explicit registration prevents accidental tool exposure
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional


@dataclass
class ToolSpec:
    """Specification for a single tool.

    Attributes:
        name: The unique tool identifier (e.g. "echo", "add").
        handler: The callable that implements the tool (sync or async).
        description: Optional human-readable description of what the tool does.
    """

    name: str
    handler: Callable
    description: str = ""


class ToolRegistry:
    """Central registry for GENUS tools.

    Maintains a whitelist of registered tools. Unknown tools are denied by
    default (get() returns None). Tools cannot be accidentally overwritten
    unless replace=True is explicitly passed.

    Usage::

        registry = ToolRegistry()

        def echo(message: str) -> str:
            return message

        registry.register(ToolSpec(name="echo", handler=echo))
        spec = registry.get("echo")  # Returns ToolSpec
        spec = registry.get("unknown")  # Returns None

    No Redis, no IO, no external dependencies.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec, *, replace: bool = False) -> None:
        """Register a tool in the registry.

        Args:
            tool: The ToolSpec to register.
            replace: If True, allow overwriting an existing tool with the same name.
                     If False (default), raise ValueError on duplicate names.

        Raises:
            ValueError: If a tool with the same name is already registered and
                        replace=False.
        """
        if tool.name in self._tools and not replace:
            raise ValueError(
                "Tool '{}' is already registered. Use replace=True to overwrite.".format(
                    tool.name
                )
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolSpec]:
        """Look up a tool by name.

        Args:
            name: The tool name to look up.

        Returns:
            The ToolSpec if found, None otherwise (deny by default).
        """
        return self._tools.get(name)

    def list_names(self) -> list:
        """Return a list of all registered tool names.

        Returns:
            A sorted list of tool names currently in the registry.
        """
        return sorted(self._tools.keys())
