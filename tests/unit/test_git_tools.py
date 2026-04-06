"""
Unit tests for git_tools

Tests git operations via SandboxRunner with policy validation.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from genus.tools.git_tools import (
    git_status,
    git_diff,
    git_create_branch,
    git_add_all,
    git_commit,
    _create_git_policy,
)
from genus.workspace.workspace import RunWorkspace
from genus.sandbox.models import SandboxPolicyError


class TestGitPolicy:
    """Test git policy creation and validation."""

    def test_create_git_policy_allows_git_commands(self):
        """Test that git policy allows required git commands."""
        policy = _create_git_policy()

        # Check that git is in allowed executables
        assert "git" in policy.allowed_executables
        assert "git.exe" in policy.allowed_executables

        # Check that required git command prefixes are allowed
        expected_prefixes = [
            ["git", "status", "--porcelain"],
            ["git", "diff"],
            ["git", "diff", "--staged"],
            ["git", "checkout", "-b"],
            ["git", "add", "-A"],
            ["git", "commit", "-m"],
        ]

        for prefix in expected_prefixes:
            assert prefix in policy.allowed_argv_prefixes

    def test_git_policy_blocks_push(self):
        """Test that git push is NOT in the allowlist (reserved for PR #29)."""
        policy = _create_git_policy()

        # git push should not be in allowed prefixes
        push_prefixes = [
            ["git", "push"],
            ["git", "push", "-f"],
            ["git", "push", "--force"],
        ]

        for prefix in push_prefixes:
            assert prefix not in policy.allowed_argv_prefixes


class TestGitToolsMocked:
    """Test git tools with mocked SandboxRunner."""

    @pytest.mark.asyncio
    async def test_git_status_success(self, tmp_path):
        """Test git status returns status output."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        # Mock the SandboxRunner.run method
        with patch("genus.tools.git_tools.SandboxRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            # Mock successful result
            mock_result = AsyncMock()
            mock_result.exit_code = 0
            mock_result.stdout = " M file.txt\n"
            mock_result.stderr = ""
            mock_runner.run.return_value = mock_result

            result = await git_status(workspace)

            assert result.success is True
            assert result.data["exit_code"] == 0
            assert " M file.txt" in result.data["stdout"]

    @pytest.mark.asyncio
    async def test_git_diff_unstaged(self, tmp_path):
        """Test git diff for unstaged changes."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        with patch("genus.tools.git_tools.SandboxRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            mock_result = AsyncMock()
            mock_result.exit_code = 0
            mock_result.stdout = "diff --git a/file.txt b/file.txt\n"
            mock_result.stderr = ""
            mock_runner.run.return_value = mock_result

            result = await git_diff(workspace, staged=False)

            assert result.success is True
            assert "diff --git" in result.data["stdout"]

    @pytest.mark.asyncio
    async def test_git_diff_staged(self, tmp_path):
        """Test git diff for staged changes."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        with patch("genus.tools.git_tools.SandboxRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            mock_result = AsyncMock()
            mock_result.exit_code = 0
            mock_result.stdout = "diff --git a/staged.txt b/staged.txt\n"
            mock_result.stderr = ""
            mock_runner.run.return_value = mock_result

            result = await git_diff(workspace, staged=True)

            assert result.success is True
            assert "diff --git" in result.data["stdout"]

            # Verify that --staged was passed
            call_args = mock_runner.run.call_args
            command = call_args[0][0]
            assert command.argv == ["git", "diff", "--staged"]

    @pytest.mark.asyncio
    async def test_git_create_branch_success(self, tmp_path):
        """Test creating a new git branch."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        with patch("genus.tools.git_tools.SandboxRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            mock_result = AsyncMock()
            mock_result.exit_code = 0
            mock_result.stdout = "Switched to a new branch 'feature/test'\n"
            mock_result.stderr = ""
            mock_runner.run.return_value = mock_result

            result = await git_create_branch(workspace, "feature/test")

            assert result.success is True
            assert result.data["branch"] == "feature/test"

            # Verify command
            call_args = mock_runner.run.call_args
            command = call_args[0][0]
            assert command.argv == ["git", "checkout", "-b", "feature/test"]

    @pytest.mark.asyncio
    async def test_git_add_all_success(self, tmp_path):
        """Test staging all changes."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        with patch("genus.tools.git_tools.SandboxRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            mock_result = AsyncMock()
            mock_result.exit_code = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            mock_runner.run.return_value = mock_result

            result = await git_add_all(workspace)

            assert result.success is True

            # Verify command
            call_args = mock_runner.run.call_args
            command = call_args[0][0]
            assert command.argv == ["git", "add", "-A"]

    @pytest.mark.asyncio
    async def test_git_commit_success(self, tmp_path):
        """Test creating a git commit."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        with patch("genus.tools.git_tools.SandboxRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            mock_result = AsyncMock()
            mock_result.exit_code = 0
            mock_result.stdout = "[main abc123] feat: add feature\n 1 file changed\n"
            mock_result.stderr = ""
            mock_runner.run.return_value = mock_result

            result = await git_commit(workspace, "feat: add feature")

            assert result.success is True
            assert result.data["nothing_to_commit"] is False

            # Verify command
            call_args = mock_runner.run.call_args
            command = call_args[0][0]
            assert command.argv == ["git", "commit", "-m", "feat: add feature"]

    @pytest.mark.asyncio
    async def test_git_commit_nothing_to_commit(self, tmp_path):
        """Test git commit when there's nothing to commit."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        with patch("genus.tools.git_tools.SandboxRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            mock_result = AsyncMock()
            mock_result.exit_code = 1
            mock_result.stdout = "nothing to commit, working tree clean\n"
            mock_result.stderr = ""
            mock_runner.run.return_value = mock_result

            result = await git_commit(workspace, "feat: add feature")

            # Should still succeed but indicate nothing to commit
            assert result.success is True
            assert result.data["nothing_to_commit"] is True

    @pytest.mark.asyncio
    async def test_git_command_failure_returns_error(self, tmp_path):
        """Test that git command failures are properly handled."""
        workspace = RunWorkspace.create("test-run", workspace_root=tmp_path)
        workspace.ensure_dirs()

        with patch("genus.tools.git_tools.SandboxRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            mock_result = AsyncMock()
            mock_result.exit_code = 128
            mock_result.stdout = ""
            mock_result.stderr = "fatal: not a git repository\n"
            mock_runner.run.return_value = mock_result

            result = await git_status(workspace)

            assert result.success is False
            assert "git status failed" in result.error
            assert "not a git repository" in result.error
