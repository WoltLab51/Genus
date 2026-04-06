"""
Tests for GitHub PR Tools

Tests the github_pr tools layer with mocked dependencies.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from genus.tools.github_pr import (
    github_push_branch,
    github_create_or_update_pr,
    github_comment_pr,
    github_wait_for_checks,
    ToolResult,
)
from genus.workspace.workspace import RunWorkspace
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.security.github_policy import GitHubPolicy
from genus.github.client import GitHubClient
from genus.github.config import GitHubConfig


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace."""
    workspace = RunWorkspace.create("test-run-001", workspace_root=tmp_path)
    workspace.ensure_dirs()
    return workspace


@pytest.fixture
def journal(workspace, tmp_path):
    """Create a test journal."""
    store = JsonlRunStore(base_dir=tmp_path / "runs")
    journal = RunJournal("test-run-001", store)
    journal.initialize(goal="Test GitHub tools")
    return journal


@pytest.fixture
def policy():
    """Create a permissive test policy."""
    return GitHubPolicy(
        allow_push=True,
        allow_create_pr=True,
        allow_comment=True,
        allowed_owner_repos={"test-owner/test-repo"},
    )


@pytest.fixture
def github_config():
    """Create a test GitHub configuration."""
    return GitHubConfig(
        owner="test-owner",
        repo="test-repo",
    )


@pytest.fixture
def github_client(github_config):
    """Create a mock GitHub client."""
    return Mock(spec=GitHubClient)


@pytest.mark.asyncio
async def test_github_push_branch_success(workspace, policy, journal):
    """Test successful branch push."""
    with patch("genus.tools.github_pr.git_push", new=AsyncMock()) as mock_push:
        mock_push.return_value = ToolResult(
            success=True,
            data={"remote": "origin", "branch": "test-branch"},
        )

        result = await github_push_branch(
            workspace=workspace,
            remote="origin",
            branch="test-branch",
            policy=policy,
            journal=journal,
        )

        assert result.success is True
        assert result.data["branch"] == "test-branch"

        # Verify git_push was called
        mock_push.assert_called_once()


@pytest.mark.asyncio
async def test_github_push_branch_policy_denied(workspace, journal):
    """Test push denied by policy."""
    # Policy with push disabled
    policy = GitHubPolicy(allow_push=False)

    result = await github_push_branch(
        workspace=workspace,
        remote="origin",
        branch="test-branch",
        policy=policy,
        journal=journal,
    )

    assert result.success is False
    assert "not allowed" in result.error.lower()


@pytest.mark.asyncio
async def test_github_create_or_update_pr_creates_new(
    workspace, github_client, github_config, policy, journal
):
    """Test creating a new PR when none exists."""
    # Mock: no existing PR
    github_client.find_open_pull_request.return_value = None

    # Mock: create PR returns data
    github_client.create_pull_request.return_value = {
        "number": 123,
        "html_url": "https://github.com/test-owner/test-repo/pull/123",
    }

    result = await github_create_or_update_pr(
        workspace=workspace,
        client=github_client,
        config=github_config,
        head="feature-branch",
        base="main",
        title="Test PR",
        body="Test body",
        policy=policy,
        journal=journal,
    )

    assert result.success is True
    assert result.data["number"] == 123
    assert result.data["action"] == "created"

    # Verify create was called
    github_client.create_pull_request.assert_called_once()


@pytest.mark.asyncio
async def test_github_create_or_update_pr_updates_existing(
    workspace, github_client, github_config, policy, journal
):
    """Test updating an existing PR."""
    # Mock: existing PR found
    github_client.find_open_pull_request.return_value = {
        "number": 456,
        "html_url": "https://github.com/test-owner/test-repo/pull/456",
    }

    # Mock: update PR returns data
    github_client.update_pull_request.return_value = {
        "number": 456,
        "html_url": "https://github.com/test-owner/test-repo/pull/456",
    }

    result = await github_create_or_update_pr(
        workspace=workspace,
        client=github_client,
        config=github_config,
        head="feature-branch",
        base="main",
        title="Updated PR",
        body="Updated body",
        policy=policy,
        journal=journal,
    )

    assert result.success is True
    assert result.data["number"] == 456
    assert result.data["action"] == "updated"

    # Verify update was called, not create
    github_client.update_pull_request.assert_called_once()
    github_client.create_pull_request.assert_not_called()


@pytest.mark.asyncio
async def test_github_create_or_update_pr_body_too_large(
    workspace, github_client, github_config, journal
):
    """Test PR creation with body exceeding max size."""
    # Policy with small max body size
    policy = GitHubPolicy(
        allow_create_pr=True,
        max_pr_body_chars=100,
        allowed_owner_repos={"test-owner/test-repo"},
    )

    large_body = "x" * 200  # Exceeds limit

    result = await github_create_or_update_pr(
        workspace=workspace,
        client=github_client,
        config=github_config,
        head="feature-branch",
        base="main",
        title="Test PR",
        body=large_body,
        policy=policy,
        journal=journal,
    )

    assert result.success is False
    assert "exceeds max size" in result.error


@pytest.mark.asyncio
async def test_github_create_or_update_pr_policy_denied(
    workspace, github_client, github_config, journal
):
    """Test PR creation denied by policy."""
    # Policy with create_pr disabled
    policy = GitHubPolicy(allow_create_pr=False)

    result = await github_create_or_update_pr(
        workspace=workspace,
        client=github_client,
        config=github_config,
        head="feature-branch",
        base="main",
        title="Test PR",
        body="Test body",
        policy=policy,
        journal=journal,
    )

    assert result.success is False
    assert "not allowed" in result.error.lower()


@pytest.mark.asyncio
async def test_github_comment_pr_success(github_client, github_config, policy, journal):
    """Test successful PR comment."""
    # Mock: create comment returns data
    github_client.create_issue_comment.return_value = {
        "id": 789,
        "html_url": "https://github.com/test-owner/test-repo/pull/123#issuecomment-789",
    }

    result = await github_comment_pr(
        client=github_client,
        config=github_config,
        pr_number=123,
        comment="Test comment",
        policy=policy,
        journal=journal,
    )

    assert result.success is True
    assert result.data["pr_number"] == 123
    assert "comment_url" in result.data

    # Verify comment was created
    github_client.create_issue_comment.assert_called_once()


@pytest.mark.asyncio
async def test_github_comment_pr_policy_denied(github_client, github_config, journal):
    """Test PR comment denied by policy."""
    # Policy with comment disabled
    policy = GitHubPolicy(allow_comment=False)

    result = await github_comment_pr(
        client=github_client,
        config=github_config,
        pr_number=123,
        comment="Test comment",
        policy=policy,
        journal=journal,
    )

    assert result.success is False
    assert "not allowed" in result.error.lower()


@pytest.mark.asyncio
async def test_github_wait_for_checks_all_pass(github_client, github_config, journal):
    """Test waiting for checks when all pass."""
    # Mock: all checks completed successfully
    github_client.list_check_runs_for_ref.return_value = [
        {"name": "CI", "status": "completed", "conclusion": "success"},
        {"name": "Lint", "status": "completed", "conclusion": "success"},
    ]

    result = await github_wait_for_checks(
        client=github_client,
        config=github_config,
        ref="abc123",
        timeout_s=60,
        poll_interval_s=1,
        journal=journal,
    )

    assert result.success is True
    assert result.data["conclusion"] == "success"
    assert result.data["total_checks"] == 2
    assert result.data["passed"] == 2
    assert result.data["failed"] == 0


@pytest.mark.asyncio
async def test_github_wait_for_checks_some_fail(github_client, github_config, journal):
    """Test waiting for checks when some fail."""
    # Mock: one check failed
    github_client.list_check_runs_for_ref.return_value = [
        {"name": "CI", "status": "completed", "conclusion": "success"},
        {"name": "Lint", "status": "completed", "conclusion": "failure"},
    ]

    result = await github_wait_for_checks(
        client=github_client,
        config=github_config,
        ref="abc123",
        timeout_s=60,
        poll_interval_s=1,
        journal=journal,
    )

    assert result.success is True
    assert result.data["conclusion"] == "failure"
    assert result.data["passed"] == 1
    assert result.data["failed"] == 1
    assert len(result.data["failing_checks"]) == 1
    assert result.data["failing_checks"][0]["name"] == "Lint"


@pytest.mark.asyncio
async def test_github_wait_for_checks_timeout(github_client, github_config, journal):
    """Test waiting for checks with timeout."""
    # Mock: checks never complete (always pending)
    github_client.list_check_runs_for_ref.return_value = [
        {"name": "CI", "status": "in_progress", "conclusion": None},
    ]

    result = await github_wait_for_checks(
        client=github_client,
        config=github_config,
        ref="abc123",
        timeout_s=2,  # Short timeout
        poll_interval_s=1,
        journal=journal,
    )

    assert result.success is True
    assert result.data["conclusion"] == "timeout"
