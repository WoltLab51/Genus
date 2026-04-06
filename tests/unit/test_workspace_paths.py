"""
Tests for workspace.paths module.

Verifies:
- default_workspace_root() returns correct path
- safe_run_id() sanitizes run IDs for Windows
- ensure_within() protects against path traversal
"""

import pytest
from pathlib import Path
import tempfile
import os

from genus.workspace.paths import (
    default_workspace_root,
    safe_run_id,
    ensure_within,
)


class TestDefaultWorkspaceRoot:
    """Tests for default_workspace_root()."""

    def test_returns_path_in_home_directory(self):
        """Should return a Path in the user's home directory."""
        root = default_workspace_root()
        assert isinstance(root, Path)
        assert root == Path.home() / "genus-workspaces"

    def test_returns_consistent_value(self):
        """Should return the same value on multiple calls."""
        root1 = default_workspace_root()
        root2 = default_workspace_root()
        assert root1 == root2


class TestSafeRunId:
    """Tests for safe_run_id()."""

    def test_keeps_valid_characters(self):
        """Should keep alphanumeric, dots, underscores, and hyphens."""
        run_id = "abc123-DEF_456.xyz"
        result = safe_run_id(run_id)
        assert result == "abc123-DEF_456.xyz"

    def test_replaces_colons(self):
        """Should replace colons (from timestamps) with underscores."""
        run_id = "2026-04-05T14:07:12Z__task__abc123"
        result = safe_run_id(run_id)
        assert ":" not in result
        assert result == "2026-04-05T14_07_12Z__task__abc123"

    def test_replaces_forward_slashes(self):
        """Should replace forward slashes with underscores."""
        run_id = "task/subtask/run"
        result = safe_run_id(run_id)
        assert "/" not in result
        assert result == "task_subtask_run"

    def test_replaces_backslashes(self):
        """Should replace backslashes with underscores."""
        run_id = "task\\subtask\\run"
        result = safe_run_id(run_id)
        assert "\\" not in result
        assert result == "task_subtask_run"

    def test_replaces_windows_problematic_chars(self):
        """Should replace Windows-problematic characters (<>|?*) with underscores."""
        run_id = "task<>with|bad?chars*"
        result = safe_run_id(run_id)
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result
        assert result == "task__with_bad_chars_"

    def test_removes_path_traversal_patterns(self):
        """Should replace .. patterns with underscores."""
        run_id = "task/../etc/passwd"
        result = safe_run_id(run_id)
        assert ".." not in result
        assert result == "task___etc_passwd"

    def test_raises_on_empty_string(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError) as exc_info:
            safe_run_id("")
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_raises_on_whitespace_only(self):
        """Should raise ValueError for whitespace-only string."""
        with pytest.raises(ValueError) as exc_info:
            safe_run_id("   ")
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_raises_when_result_empty_after_sanitization(self):
        """Should raise ValueError when result is empty after sanitization."""
        with pytest.raises(ValueError) as exc_info:
            safe_run_id("///")
        assert "becomes empty after sanitization" in str(exc_info.value).lower()

    def test_preserves_double_underscores(self):
        """Should preserve double underscores used in run_id format."""
        run_id = "timestamp__slug__suffix"
        result = safe_run_id(run_id)
        assert "__" in result
        assert result == "timestamp__slug__suffix"


class TestEnsureWithin:
    """Tests for ensure_within()."""

    def test_accepts_path_within_base(self, tmp_path):
        """Should accept a path that is within base directory."""
        base = tmp_path / "workspace"
        base.mkdir()
        target = base / "subdir" / "file.txt"

        result = ensure_within(base, target)
        assert result == target.resolve()

    def test_rejects_path_outside_base(self, tmp_path):
        """Should reject a path outside base directory."""
        base = tmp_path / "workspace"
        base.mkdir()
        outside = tmp_path / "other" / "file.txt"

        with pytest.raises(ValueError) as exc_info:
            ensure_within(base, outside)
        assert "is not within" in str(exc_info.value).lower()

    def test_rejects_parent_directory_traversal(self, tmp_path):
        """Should reject paths using .. to escape base."""
        base = tmp_path / "workspace"
        base.mkdir()
        target = base / ".." / "etc" / "passwd"

        with pytest.raises(ValueError) as exc_info:
            ensure_within(base, target)
        assert "is not within" in str(exc_info.value).lower()

    def test_resolves_relative_paths(self, tmp_path):
        """Should resolve both base and target to absolute paths."""
        base = tmp_path / "workspace"
        base.mkdir()

        # Create a relative target
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            target = Path("workspace") / "file.txt"

            result = ensure_within(base, target)
            assert result.is_absolute()
            assert result == (base / "file.txt").resolve()
        finally:
            os.chdir(original_cwd)

    def test_handles_symlinks_safely(self, tmp_path):
        """Should resolve symlinks and validate the real path."""
        # Skip on Windows where symlinks require admin privileges
        if os.name == 'nt':
            pytest.skip("Symlink test requires Unix-like OS")

        base = tmp_path / "workspace"
        base.mkdir()

        outside = tmp_path / "outside"
        outside.mkdir()

        # Create symlink inside base pointing outside
        symlink = base / "link"
        symlink.symlink_to(outside)

        # The symlink target resolves outside base, should be rejected
        with pytest.raises(ValueError):
            ensure_within(base, symlink)

    def test_accepts_base_itself(self, tmp_path):
        """Should accept the base directory itself."""
        base = tmp_path / "workspace"
        base.mkdir()

        result = ensure_within(base, base)
        assert result == base.resolve()

    def test_normalizes_path_separators(self, tmp_path):
        """Should normalize path separators (/ vs \\) on all platforms."""
        base = tmp_path / "workspace"
        base.mkdir()

        # Use forward slashes even on Windows
        target_str = str(base / "subdir/file.txt")
        target = Path(target_str)

        result = ensure_within(base, target)
        assert result.is_absolute()
