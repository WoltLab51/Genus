"""
Repo Write Tools

Provides safe, controlled write operations to workspace repositories.
All writes are path-restricted and require explicit allowlists.

Design principles:
- Deny-by-default: All paths must be explicitly allowed
- Path traversal protection: Prevents ../../../etc/passwd attacks
- Atomic operations: Each write is a single, complete action
- Evidence trail: Returns ToolResult with evidence for journal logging
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from genus.workspace.paths import ensure_within


@dataclass
class ToolResult:
    """Standard response format for repo write tools.

    Attributes:
        success: Whether the operation succeeded.
        data: The main result data.
        error: Optional error message if success is False.
    """

    success: bool
    data: Any
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to a dictionary for serialization."""
        result = {
            "success": self.success,
            "data": self.data,
        }
        if self.error is not None:
            result["error"] = self.error
        return result


def write_text_file(
    repo_root: Path,
    rel_path: str,
    content: str,
    *,
    allowed_paths: Optional[List[str]] = None,
    create: bool = True,
) -> ToolResult:
    """Write text content to a file in the repository.

    This is a controlled write operation with security restrictions:
    - Path traversal protection (no ../)
    - Allowlist enforcement (deny-by-default)
    - UTF-8 encoding only

    Args:
        repo_root: Root directory of the repository workspace.
        rel_path: Path to the file relative to repo_root.
        content: Text content to write (UTF-8).
        allowed_paths: List of allowed path prefixes (e.g., ["genus/", "tests/", "docs/"]).
                      If None, an error is raised (deny-by-default).
        create: If True, create parent directories if they don't exist.
                If False, fail if the file or its parent directories don't exist.

    Returns:
        ToolResult with success status and file info.

    Raises:
        None - all errors are returned in ToolResult.error

    Security:
        - Blocks path traversal attempts (../)
        - Requires explicit allowlist (allowed_paths must be provided)
        - Validates path is within repo_root
        - Only allows paths matching allowed_paths prefixes

    Example::

        result = write_text_file(
            repo_root=Path("/workspace/repo"),
            rel_path="docs/NOTES.md",
            content="# Notes\\n\\nSome notes here.",
            allowed_paths=["docs/", "genus/"],
        )

        if result.success:
            print(f"Wrote {result.data['bytes_written']} bytes to {result.data['path']}")
        else:
            print(f"Error: {result.error}")
    """
    # Enforce explicit allowlist (deny-by-default)
    if allowed_paths is None:
        return ToolResult(
            success=False,
            data=None,
            error="allowed_paths must be explicitly specified (deny-by-default policy)",
        )

    # Check for path traversal
    if ".." in rel_path:
        return ToolResult(
            success=False,
            data=None,
            error="Path traversal (..) not allowed in rel_path: '{}'".format(rel_path),
        )

    # Check if path matches any allowed prefix
    path_allowed = False
    for allowed_prefix in allowed_paths:
        if rel_path.startswith(allowed_prefix):
            path_allowed = True
            break

    if not path_allowed:
        return ToolResult(
            success=False,
            data=None,
            error="Path '{}' does not match any allowed prefix: {}".format(
                rel_path, allowed_paths
            ),
        )

    try:
        # Build target path
        target = repo_root / rel_path

        # Security: Ensure path is within repo_root
        target_resolved = ensure_within(repo_root, target)

        # Check if parent directory exists
        parent_dir = target_resolved.parent
        if not parent_dir.exists():
            if not create:
                return ToolResult(
                    success=False,
                    data=None,
                    error="Parent directory '{}' does not exist and create=False".format(
                        parent_dir.relative_to(repo_root)
                    ),
                )
            # Create parent directories
            parent_dir.mkdir(parents=True, exist_ok=True)

        # Write file content
        target_resolved.write_text(content, encoding="utf-8")

        # Return success with file info
        bytes_written = len(content.encode("utf-8"))

        return ToolResult(
            success=True,
            data={
                "path": rel_path,
                "bytes_written": bytes_written,
                "created": not target_resolved.exists() or target_resolved.stat().st_size == 0,
            },
        )

    except ValueError as e:
        # Path traversal or outside repo_root
        return ToolResult(
            success=False,
            data=None,
            error="Security error: {}".format(str(e)),
        )
    except Exception as e:
        return ToolResult(
            success=False,
            data=None,
            error="Error writing file '{}': {}".format(rel_path, str(e)),
        )


def apply_unified_diff(
    repo_root: Path,
    diff_text: str,
    *,
    allowed_paths: Optional[List[str]] = None,
) -> ToolResult:
    """Apply a unified diff to repository files.

    This is a v1 placeholder implementation that returns an error directing
    users to use write_text_file instead. Full unified diff parsing and
    application can be added in a future version if needed.

    Args:
        repo_root: Root directory of the repository workspace.
        diff_text: Unified diff text (patch format).
        allowed_paths: List of allowed path prefixes.

    Returns:
        ToolResult with error indicating this is not yet implemented.

    Note:
        For v1, use write_text_file to write complete file contents instead
        of applying patches. This keeps the implementation simple and safe.
    """
    return ToolResult(
        success=False,
        data=None,
        error=(
            "apply_unified_diff is not implemented in v1. "
            "Use write_text_file to write complete file contents instead."
        ),
    )
