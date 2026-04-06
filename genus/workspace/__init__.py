"""
Workspace Module

Provides workspace management for GENUS runs, including:
- Windows-safe path normalization and validation
- Per-run workspace isolation
- Read-only repository tools with evidence capture
"""

from genus.workspace.paths import (
    default_workspace_root,
    safe_run_id,
    ensure_within,
)
from genus.workspace.workspace import RunWorkspace
from genus.workspace.repo_tools import (
    Evidence,
    ToolResponse,
    GrepMatch,
    read_file,
    list_tree,
    grep_text,
)

__all__ = [
    "default_workspace_root",
    "safe_run_id",
    "ensure_within",
    "RunWorkspace",
    "Evidence",
    "ToolResponse",
    "GrepMatch",
    "read_file",
    "list_tree",
    "grep_text",
]
