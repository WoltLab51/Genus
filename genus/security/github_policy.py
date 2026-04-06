"""
GitHub Policy - Security Layer for GitHub Write Operations

Implements deny-by-default security policy for GitHub write operations.
All GitHub write actions (push, PR create/update, comment) require explicit
permission and Ask/Stop gate by default.

Design principles:
- Deny-by-default: All operations denied unless explicitly allowed
- Allowlist enforcement: Only specific owner/repo combinations allowed
- Ask/Stop gates: Human confirmation required for sensitive operations
- Rate limiting awareness: Respects GitHub API limits
- No auto-merge: Only PR creation/update, never automatic merging
"""

from typing import Set, Tuple


class GitHubPolicyError(Exception):
    """Raised when a GitHub operation violates policy."""

    pass


class GitHubPolicy:
    """Security policy for GitHub write operations.

    Controls which GitHub operations are permitted and enforces
    security constraints like allowed repositories and Ask/Stop gates.

    Attributes:
        allow_push: Whether git push is allowed (default False).
        allow_create_pr: Whether PR creation is allowed (default False).
        allow_comment: Whether PR commenting is allowed (default False).
        allowed_owner_repos: Set of allowed "owner/repo" strings (default {"WoltLab51/Genus"}).
        max_pr_body_chars: Maximum PR body size in characters (default 20000).
        require_ask_stop_for_push: Whether to require Ask/Stop gate for push (default True).
        require_ask_stop_for_create_pr: Whether to require Ask/Stop gate for PR creation (default True).
    """

    def __init__(
        self,
        *,
        allow_push: bool = False,
        allow_create_pr: bool = False,
        allow_comment: bool = False,
        allowed_owner_repos: Set[str] = None,
        max_pr_body_chars: int = 20000,
        require_ask_stop_for_push: bool = True,
        require_ask_stop_for_create_pr: bool = True,
    ):
        """Initialize GitHub policy.

        Args:
            allow_push: Whether git push is allowed (default False).
            allow_create_pr: Whether PR creation is allowed (default False).
            allow_comment: Whether PR commenting is allowed (default False).
            allowed_owner_repos: Set of allowed "owner/repo" strings.
                                 Default: {"WoltLab51/Genus"}
            max_pr_body_chars: Maximum PR body size in characters (default 20000).
            require_ask_stop_for_push: Whether to require Ask/Stop gate for push (default True).
            require_ask_stop_for_create_pr: Whether to require Ask/Stop gate for PR creation (default True).
        """
        self.allow_push = allow_push
        self.allow_create_pr = allow_create_pr
        self.allow_comment = allow_comment

        if allowed_owner_repos is None:
            allowed_owner_repos = {"WoltLab51/Genus"}
        self.allowed_owner_repos = set(allowed_owner_repos)

        self.max_pr_body_chars = max_pr_body_chars
        self.require_ask_stop_for_push = require_ask_stop_for_push
        self.require_ask_stop_for_create_pr = require_ask_stop_for_create_pr

    def assert_repo_allowed(self, owner: str, repo: str) -> None:
        """Verify that the owner/repo combination is allowed.

        Args:
            owner: Repository owner.
            repo: Repository name.

        Raises:
            GitHubPolicyError: If the owner/repo is not in the allowlist.

        Example::

            policy = GitHubPolicy()
            policy.assert_repo_allowed("WoltLab51", "Genus")  # OK
            policy.assert_repo_allowed("other", "repo")  # Raises GitHubPolicyError
        """
        repo_id = "{}/{}".format(owner, repo)

        if repo_id not in self.allowed_owner_repos:
            raise GitHubPolicyError(
                "Repository '{}' is not in allowlist. Allowed: {}".format(
                    repo_id, sorted(self.allowed_owner_repos)
                )
            )

    def assert_action_allowed(self, action: str) -> None:
        """Verify that the specified action is allowed.

        Args:
            action: Action name ("push", "create_pr", "comment").

        Raises:
            GitHubPolicyError: If the action is not allowed by policy.

        Example::

            policy = GitHubPolicy(allow_create_pr=True)
            policy.assert_action_allowed("create_pr")  # OK
            policy.assert_action_allowed("push")  # Raises GitHubPolicyError
        """
        action_map = {
            "push": self.allow_push,
            "create_pr": self.allow_create_pr,
            "comment": self.allow_comment,
        }

        if action not in action_map:
            raise GitHubPolicyError(
                "Unknown action '{}'. Allowed actions: {}".format(
                    action, list(action_map.keys())
                )
            )

        if not action_map[action]:
            raise GitHubPolicyError(
                "Action '{}' is not allowed by policy (flag is False)".format(action)
            )


def should_ask_for_github_write(
    action: str,
    branch: str,
    *,
    files_changed: int = 0,
    tests_passed: bool = False,
    risk_flags: list = None,
) -> Tuple[bool, str]:
    """Determine if Ask/Stop gate should be triggered for a GitHub write operation.

    This is a conservative v1 implementation that defaults to asking for confirmation
    on all write operations. Future versions can implement more sophisticated logic
    based on risk assessment.

    Args:
        action: GitHub action ("push", "create_pr", "comment").
        branch: Branch name being operated on.
        files_changed: Number of files changed (optional).
        tests_passed: Whether tests have passed (optional).
        risk_flags: List of risk indicators (optional).

    Returns:
        Tuple of (should_ask: bool, reason: str).
        - should_ask: True if confirmation is needed, False otherwise.
        - reason: Human-readable explanation.

    Example::

        should_ask, reason = should_ask_for_github_write(
            action="push",
            branch="main",
            files_changed=5,
            tests_passed=True,
        )

        if should_ask:
            print(f"Confirmation required: {reason}")
    """
    if risk_flags is None:
        risk_flags = []

    # v1: Always ask for safety
    # Future versions can implement sophisticated logic:
    # - Allow auto-push if tests passed and < 10 files changed
    # - Allow auto-comment on non-main branches
    # - Require confirmation if pushing to main
    # - Require confirmation if risk_flags present

    reasons = []

    # Check action type
    if action == "push":
        reasons.append("git push requires confirmation")
    elif action == "create_pr":
        reasons.append("PR creation requires confirmation")
    elif action == "comment":
        reasons.append("PR comment requires confirmation")

    # Check branch
    if branch in ("main", "master", "production"):
        reasons.append("operation targets protected branch '{}'".format(branch))

    # Check test status
    if not tests_passed:
        reasons.append("tests have not passed")

    # Check risk flags
    if risk_flags:
        reasons.append("risk flags detected: {}".format(", ".join(risk_flags)))

    # v1: Always ask
    reason = "; ".join(reasons) if reasons else "GitHub write operation requires confirmation (v1 default)"

    return (True, reason)
