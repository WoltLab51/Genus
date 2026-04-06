"""
Tests for GitHub Policy

Tests the GitHubPolicy security layer.
"""

import pytest
from genus.security.github_policy import (
    GitHubPolicy,
    GitHubPolicyError,
    should_ask_for_github_write,
)


def test_github_policy_defaults():
    """Test that GitHubPolicy has secure defaults."""
    policy = GitHubPolicy()

    # All actions should be denied by default
    assert policy.allow_push is False
    assert policy.allow_create_pr is False
    assert policy.allow_comment is False

    # Default allowlist should contain WoltLab51/Genus
    assert "WoltLab51/Genus" in policy.allowed_owner_repos

    # Ask/Stop gates should be enabled by default
    assert policy.require_ask_stop_for_push is True
    assert policy.require_ask_stop_for_create_pr is True

    # Max PR body size should be set
    assert policy.max_pr_body_chars == 20000


def test_github_policy_custom_settings():
    """Test GitHubPolicy with custom settings."""
    policy = GitHubPolicy(
        allow_push=True,
        allow_create_pr=True,
        allow_comment=True,
        allowed_owner_repos={"owner1/repo1", "owner2/repo2"},
        max_pr_body_chars=10000,
        require_ask_stop_for_push=False,
        require_ask_stop_for_create_pr=False,
    )

    assert policy.allow_push is True
    assert policy.allow_create_pr is True
    assert policy.allow_comment is True
    assert policy.allowed_owner_repos == {"owner1/repo1", "owner2/repo2"}
    assert policy.max_pr_body_chars == 10000
    assert policy.require_ask_stop_for_push is False
    assert policy.require_ask_stop_for_create_pr is False


def test_assert_repo_allowed_success():
    """Test assert_repo_allowed with allowed repo."""
    policy = GitHubPolicy(allowed_owner_repos={"WoltLab51/Genus", "other/repo"})

    # Should not raise
    policy.assert_repo_allowed("WoltLab51", "Genus")
    policy.assert_repo_allowed("other", "repo")


def test_assert_repo_allowed_failure():
    """Test assert_repo_allowed with disallowed repo."""
    policy = GitHubPolicy(allowed_owner_repos={"WoltLab51/Genus"})

    # Should raise GitHubPolicyError
    with pytest.raises(GitHubPolicyError) as exc_info:
        policy.assert_repo_allowed("unauthorized", "repo")

    assert "unauthorized/repo" in str(exc_info.value)
    assert "not in allowlist" in str(exc_info.value)


def test_assert_action_allowed_push():
    """Test assert_action_allowed for push action."""
    # Push not allowed
    policy = GitHubPolicy(allow_push=False)
    with pytest.raises(GitHubPolicyError) as exc_info:
        policy.assert_action_allowed("push")
    assert "push" in str(exc_info.value)
    assert "not allowed" in str(exc_info.value)

    # Push allowed
    policy = GitHubPolicy(allow_push=True)
    policy.assert_action_allowed("push")  # Should not raise


def test_assert_action_allowed_create_pr():
    """Test assert_action_allowed for create_pr action."""
    # PR creation not allowed
    policy = GitHubPolicy(allow_create_pr=False)
    with pytest.raises(GitHubPolicyError) as exc_info:
        policy.assert_action_allowed("create_pr")
    assert "create_pr" in str(exc_info.value)

    # PR creation allowed
    policy = GitHubPolicy(allow_create_pr=True)
    policy.assert_action_allowed("create_pr")  # Should not raise


def test_assert_action_allowed_comment():
    """Test assert_action_allowed for comment action."""
    # Comment not allowed
    policy = GitHubPolicy(allow_comment=False)
    with pytest.raises(GitHubPolicyError) as exc_info:
        policy.assert_action_allowed("comment")
    assert "comment" in str(exc_info.value)

    # Comment allowed
    policy = GitHubPolicy(allow_comment=True)
    policy.assert_action_allowed("comment")  # Should not raise


def test_assert_action_allowed_unknown_action():
    """Test assert_action_allowed with unknown action."""
    policy = GitHubPolicy()

    with pytest.raises(GitHubPolicyError) as exc_info:
        policy.assert_action_allowed("invalid_action")

    assert "Unknown action" in str(exc_info.value)
    assert "invalid_action" in str(exc_info.value)


def test_should_ask_for_github_write_push():
    """Test should_ask_for_github_write for push action."""
    should_ask, reason = should_ask_for_github_write(
        action="push",
        branch="feature/test",
    )

    assert should_ask is True
    assert "push" in reason.lower()


def test_should_ask_for_github_write_create_pr():
    """Test should_ask_for_github_write for create_pr action."""
    should_ask, reason = should_ask_for_github_write(
        action="create_pr",
        branch="feature/test",
    )

    assert should_ask is True
    assert "pr" in reason.lower() or "creation" in reason.lower()


def test_should_ask_for_github_write_protected_branch():
    """Test should_ask_for_github_write with protected branch."""
    should_ask, reason = should_ask_for_github_write(
        action="push",
        branch="main",
        tests_passed=True,
    )

    assert should_ask is True
    assert "main" in reason.lower() or "protected" in reason.lower()


def test_should_ask_for_github_write_tests_not_passed():
    """Test should_ask_for_github_write when tests haven't passed."""
    should_ask, reason = should_ask_for_github_write(
        action="push",
        branch="feature/test",
        tests_passed=False,
    )

    assert should_ask is True
    assert "test" in reason.lower()


def test_should_ask_for_github_write_risk_flags():
    """Test should_ask_for_github_write with risk flags."""
    should_ask, reason = should_ask_for_github_write(
        action="push",
        branch="feature/test",
        tests_passed=True,
        risk_flags=["large_diff", "security_file_changed"],
    )

    assert should_ask is True
    assert "risk" in reason.lower()
    assert "large_diff" in reason or "security_file_changed" in reason


def test_should_ask_for_github_write_all_safe():
    """Test should_ask_for_github_write with all safe conditions.

    Even with all safe conditions, v1 should still ask for confirmation.
    """
    should_ask, reason = should_ask_for_github_write(
        action="comment",
        branch="feature/test",
        files_changed=2,
        tests_passed=True,
        risk_flags=[],
    )

    # v1 always asks
    assert should_ask is True
    assert len(reason) > 0
