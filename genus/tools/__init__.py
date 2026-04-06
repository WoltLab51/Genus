"""
GENUS Tool-Call Contracts

Provides topic constants and message factories for tool-call delegation
over the MessageBus (Option 2 – tool-oriented topics).

Also exports the ToolRegistry for managing tool registration and lookup.
"""

from genus.tools.registry import ToolRegistry, ToolSpec

__all__ = ["ToolRegistry", "ToolSpec"]
