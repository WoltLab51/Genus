"""Tests that github_push_branch correctly checks the kill-switch."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from genus.security.kill_switch import KillSwitch, KillSwitchActiveError
from genus.tools.github_pr import github_push_branch
from genus.security.github_policy import GitHubPolicy


def test_github_push_branch_respects_kill_switch():
    """github_push_branch must return failure result when kill-switch is active."""
    ks = KillSwitch()
    ks.activate(reason="test")

    policy = GitHubPolicy(allow_push=True)
    workspace = MagicMock()

    async def run():
        return await github_push_branch(
            workspace=workspace,
            remote="origin",
            branch="test-branch",
            policy=policy,
            kill_switch=ks,
        )

    result = asyncio.run(run())
    # Kill-switch active → must fail (not succeed)
    assert result.success is False


def test_github_push_branch_uses_assert_not_active():
    """github_push_branch must use assert_not_active (not deprecated assert_enabled)."""
    import warnings
    ks = KillSwitch()

    policy = GitHubPolicy(allow_push=True)
    workspace = MagicMock()

    async def run():
        with patch("genus.tools.github_pr.git_push", new=AsyncMock()) as mock_push:
            from genus.tools.git_tools import ToolResult
            mock_push.return_value = ToolResult(success=True, data={})
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = await github_push_branch(
                    workspace=workspace,
                    remote="origin",
                    branch="test-branch",
                    policy=policy,
                    kill_switch=ks,
                )
                # No DeprecationWarning from assert_enabled() should be raised
                deprecation_warnings = [
                    x for x in w
                    if issubclass(x.category, DeprecationWarning)
                    and "assert_enabled" in str(x.message)
                ]
                assert deprecation_warnings == [], (
                    "assert_enabled() is deprecated and must not be called"
                )
        return result

    result = asyncio.run(run())
    assert result.success is True
