"""
Unit tests for repo_write tools

Tests the security and functionality of repository write operations.
"""

import pytest
from pathlib import Path

from genus.tools.repo_write import write_text_file, apply_unified_diff


class TestWriteTextFile:
    """Test write_text_file function."""

    def test_write_allowed_file(self, tmp_path):
        """Test writing a file in an allowed path."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        result = write_text_file(
            repo_root=repo_root,
            rel_path="docs/README.md",
            content="# Test\n\nContent here.",
            allowed_paths=["docs/", "genus/"],
        )

        assert result.success is True
        assert result.data["path"] == "docs/README.md"
        assert result.data["bytes_written"] > 0

        # Verify file was written
        written_file = repo_root / "docs/README.md"
        assert written_file.exists()
        assert written_file.read_text() == "# Test\n\nContent here."

    def test_blocks_path_traversal(self, tmp_path):
        """Test that path traversal attempts are blocked."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        result = write_text_file(
            repo_root=repo_root,
            rel_path="../../../etc/passwd",
            content="malicious",
            allowed_paths=["docs/"],
        )

        assert result.success is False
        assert "Path traversal" in result.error
        assert ".." in result.error

    def test_blocks_write_outside_allowlist(self, tmp_path):
        """Test that writes outside the allowlist are blocked."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        result = write_text_file(
            repo_root=repo_root,
            rel_path="secrets/config.json",
            content='{"key": "secret"}',
            allowed_paths=["docs/", "genus/"],
        )

        assert result.success is False
        assert "does not match any allowed prefix" in result.error

    def test_requires_explicit_allowlist(self, tmp_path):
        """Test that allowed_paths must be explicitly provided."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        result = write_text_file(
            repo_root=repo_root,
            rel_path="docs/README.md",
            content="# Test",
            allowed_paths=None,  # Not allowed!
        )

        assert result.success is False
        assert "deny-by-default" in result.error

    def test_create_parent_directories(self, tmp_path):
        """Test creating parent directories when create=True."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        result = write_text_file(
            repo_root=repo_root,
            rel_path="docs/deep/nested/file.txt",
            content="nested content",
            allowed_paths=["docs/"],
            create=True,
        )

        assert result.success is True
        written_file = repo_root / "docs/deep/nested/file.txt"
        assert written_file.exists()
        assert written_file.read_text() == "nested content"

    def test_fail_if_parent_missing_and_no_create(self, tmp_path):
        """Test that writing fails if parent doesn't exist and create=False."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        result = write_text_file(
            repo_root=repo_root,
            rel_path="docs/deep/nested/file.txt",
            content="nested content",
            allowed_paths=["docs/"],
            create=False,
        )

        assert result.success is False
        assert "does not exist" in result.error

    def test_write_to_existing_file_overwrites(self, tmp_path):
        """Test that writing to an existing file overwrites it."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        existing_file = docs_dir / "file.txt"
        existing_file.write_text("old content")

        result = write_text_file(
            repo_root=repo_root,
            rel_path="docs/file.txt",
            content="new content",
            allowed_paths=["docs/"],
        )

        assert result.success is True
        assert existing_file.read_text() == "new content"

    def test_blocks_absolute_path(self, tmp_path):
        """Test that absolute paths are blocked."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Try to write using an absolute path
        result = write_text_file(
            repo_root=repo_root,
            rel_path="/etc/passwd",
            content="malicious",
            allowed_paths=["/etc/"],
        )

        # Should fail because the path doesn't match the allowed prefix
        # or because it's detected as being outside repo_root
        assert result.success is False


class TestApplyUnifiedDiff:
    """Test apply_unified_diff function."""

    def test_not_implemented_v1(self, tmp_path):
        """Test that apply_unified_diff returns not implemented error in v1."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        diff = """
--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-old line
+new line
"""

        result = apply_unified_diff(
            repo_root=repo_root,
            diff_text=diff,
            allowed_paths=["docs/"],
        )

        assert result.success is False
        assert "not implemented" in result.error
        assert "write_text_file" in result.error
