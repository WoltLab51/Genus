"""
Tests for workspace.workspace module.

Verifies:
- RunWorkspace.create() creates proper workspace instances
- RunWorkspace directory properties work correctly
- RunWorkspace.ensure_dirs() creates all required directories
- RunWorkspace.get_safe_path() validates paths correctly
"""

import pytest
from pathlib import Path
import tempfile

from genus.workspace.workspace import RunWorkspace


class TestRunWorkspace:
    """Tests for RunWorkspace class."""

    def test_create_with_valid_run_id(self, tmp_path):
        """Should create workspace with valid run_id."""
        run_id = "2026-04-05T14-07-12Z__task__abc123"
        workspace = RunWorkspace.create(run_id, workspace_root=tmp_path)

        assert workspace.run_id == run_id
        assert workspace.root == tmp_path / "2026-04-05T14-07-12Z__task__abc123"

    def test_create_sanitizes_run_id(self, tmp_path):
        """Should sanitize run_id for filesystem safety."""
        run_id = "2026-04-05T14:07:12Z__task__abc123"  # Contains colons
        workspace = RunWorkspace.create(run_id, workspace_root=tmp_path)

        # Original run_id preserved
        assert workspace.run_id == run_id
        # But path is sanitized (colons replaced)
        assert ":" not in str(workspace.root)
        assert workspace.root == tmp_path / "2026-04-05T14_07_12Z__task__abc123"

    def test_create_uses_default_workspace_root(self):
        """Should use default workspace root when not specified."""
        run_id = "test-run-123"
        workspace = RunWorkspace.create(run_id)

        expected_root = Path.home() / "genus-workspaces" / "test-run-123"
        assert workspace.root == expected_root

    def test_create_with_custom_workspace_root(self, tmp_path):
        """Should use custom workspace root when specified."""
        run_id = "test-run-123"
        custom_root = tmp_path / "custom-workspaces"

        workspace = RunWorkspace.create(run_id, workspace_root=custom_root)

        assert workspace.root == custom_root / "test-run-123"

    def test_repo_dir_property(self, tmp_path):
        """Should return correct repo directory path."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        expected = workspace.root / "repo"
        assert workspace.repo_dir == expected

    def test_artifacts_dir_property(self, tmp_path):
        """Should return correct artifacts directory path."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        expected = workspace.root / "artifacts"
        assert workspace.artifacts_dir == expected

    def test_temp_dir_property(self, tmp_path):
        """Should return correct temp directory path."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        expected = workspace.root / "temp"
        assert workspace.temp_dir == expected

    def test_ensure_dirs_creates_all_directories(self, tmp_path):
        """Should create all required workspace directories."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)

        # Directories should not exist yet
        assert not workspace.root.exists()
        assert not workspace.repo_dir.exists()
        assert not workspace.artifacts_dir.exists()
        assert not workspace.temp_dir.exists()

        # Create directories
        workspace.ensure_dirs()

        # All directories should now exist
        assert workspace.root.exists()
        assert workspace.root.is_dir()
        assert workspace.repo_dir.exists()
        assert workspace.repo_dir.is_dir()
        assert workspace.artifacts_dir.exists()
        assert workspace.artifacts_dir.is_dir()
        assert workspace.temp_dir.exists()
        assert workspace.temp_dir.is_dir()

    def test_ensure_dirs_is_idempotent(self, tmp_path):
        """Should be safe to call ensure_dirs() multiple times."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)

        # Call multiple times
        workspace.ensure_dirs()
        workspace.ensure_dirs()
        workspace.ensure_dirs()

        # Should still have all directories
        assert workspace.root.exists()
        assert workspace.repo_dir.exists()
        assert workspace.artifacts_dir.exists()
        assert workspace.temp_dir.exists()

    def test_get_safe_path_accepts_valid_relative_path(self, tmp_path):
        """Should accept valid relative path within workspace."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        safe_path = workspace.get_safe_path("repo/src/main.py")

        expected = workspace.root / "repo" / "src" / "main.py"
        assert safe_path == expected.resolve()

    def test_get_safe_path_rejects_traversal_attack(self, tmp_path):
        """Should reject path traversal attempts using ..."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        with pytest.raises(ValueError) as exc_info:
            workspace.get_safe_path("../../etc/passwd")

        assert "is not within" in str(exc_info.value).lower()

    def test_get_safe_path_handles_absolute_paths_within_workspace(self, tmp_path):
        """Should handle absolute paths that are within workspace."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        # Absolute path within workspace
        abs_path = workspace.root / "repo" / "file.txt"
        result = workspace.get_safe_path(str(abs_path))

        assert result == abs_path.resolve()

    def test_get_safe_path_rejects_absolute_paths_outside_workspace(self, tmp_path):
        """Should reject absolute paths outside workspace."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        outside_path = tmp_path / "other" / "file.txt"

        with pytest.raises(ValueError) as exc_info:
            workspace.get_safe_path(str(outside_path))

        assert "is not within" in str(exc_info.value).lower()

    def test_workspace_structure_matches_specification(self, tmp_path):
        """Should create directory structure matching specification.

        Expected structure:
            {root}/
            ├── repo/
            ├── artifacts/
            └── temp/
        """
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        # Check all expected directories exist
        assert (workspace.root / "repo").exists()
        assert (workspace.root / "artifacts").exists()
        assert (workspace.root / "temp").exists()

        # Check they are directories
        assert (workspace.root / "repo").is_dir()
        assert (workspace.root / "artifacts").is_dir()
        assert (workspace.root / "temp").is_dir()


class TestRunWorkspaceIntegration:
    """Integration tests for RunWorkspace with real file operations."""

    def test_workspace_isolation(self, tmp_path):
        """Should isolate workspaces for different run_ids."""
        run1 = RunWorkspace.create("run1", workspace_root=tmp_path)
        run2 = RunWorkspace.create("run2", workspace_root=tmp_path)

        run1.ensure_dirs()
        run2.ensure_dirs()

        # Different root directories
        assert run1.root != run2.root

        # Both exist independently
        assert run1.root.exists()
        assert run2.root.exists()

        # Write to one doesn't affect the other
        test_file1 = run1.repo_dir / "test.txt"
        test_file1.write_text("run1 content")

        assert test_file1.exists()
        assert not (run2.repo_dir / "test.txt").exists()

    def test_nested_path_creation(self, tmp_path):
        """Should handle deeply nested paths correctly."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        # Get safe path for deeply nested file
        nested = workspace.get_safe_path("repo/src/utils/helpers/util.py")

        # Create the file
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("# utility code")

        # Verify it exists
        assert nested.exists()
        assert nested.read_text() == "# utility code"

        # Verify it's within workspace
        assert nested.is_relative_to(workspace.root)
