"""
Path Utilities for Workspace Management

Provides Windows-safe path normalization and validation functions.
All functions ensure cross-platform compatibility with special attention
to Windows path restrictions and security concerns like path traversal.
"""

import re
from pathlib import Path
from typing import Union


def default_workspace_root() -> Path:
    """Return the default workspace root directory.

    Returns:
        Path to the default workspace root (~/genus-workspaces).
    """
    return Path.home() / "genus-workspaces"


def safe_run_id(run_id: str) -> str:
    """Return a Windows-safe version of the run_id.

    Replaces characters that are problematic on Windows filesystems
    (such as :, \\, /, <, >, |, ?, *, and ..) with underscores.
    Only allows [a-zA-Z0-9._-] characters.

    Args:
        run_id: The original run identifier.

    Returns:
        A filesystem-safe version of the run_id.

    Raises:
        ValueError: If the run_id is empty or becomes empty after sanitization.

    Examples:
        >>> safe_run_id("2026-04-05T14:07:12Z__task__abc123")
        '2026-04-05T14-07-12Z__task__abc123'
        >>> safe_run_id("task/with\\bad:chars")
        'task_with_bad_chars'
    """
    if not run_id or not run_id.strip():
        raise ValueError("run_id cannot be empty")

    # Replace problematic characters with underscores
    # Only keep alphanumeric, dot, underscore, and hyphen
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", run_id)

    # Remove any potential path traversal patterns
    safe = safe.replace("..", "_")

    # Ensure not empty after sanitization
    if not safe or not safe.strip("_"):
        raise ValueError(
            "run_id '{}' becomes empty after sanitization".format(run_id)
        )

    return safe


def ensure_within(base: Path, target: Path) -> Path:
    """Ensure that target path is within base directory.

    Resolves both paths to absolute, normalized forms and verifies
    that target is a subdirectory of base. This protects against
    path traversal attacks using .. or symlinks.

    Args:
        base: The base directory that should contain the target.
        target: The target path to validate.

    Returns:
        The resolved absolute target path.

    Raises:
        ValueError: If target is not within base directory.

    Examples:
        >>> base = Path("/home/user/workspace")
        >>> target = Path("/home/user/workspace/run1/file.txt")
        >>> ensure_within(base, target)
        PosixPath('/home/user/workspace/run1/file.txt')

        >>> target = Path("/home/user/workspace/../etc/passwd")
        >>> ensure_within(base, target)
        Traceback (most recent call last):
            ...
        ValueError: Path '/home/user/etc/passwd' is not within '/home/user/workspace'
    """
    # Resolve to absolute, normalized paths
    base_resolved = base.resolve()
    target_resolved = target.resolve()

    # Check if target is relative to base
    try:
        target_resolved.relative_to(base_resolved)
    except ValueError:
        raise ValueError(
            "Path '{}' is not within '{}'".format(target_resolved, base_resolved)
        )

    return target_resolved
