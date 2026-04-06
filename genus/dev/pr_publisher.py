"""
PR Publisher - Orchestrator Hook for GitHub PR Operations

Provides a high-level interface for publishing run results as GitHub PRs.
This module keeps GitHub write operations separate from the core DevLoop
orchestrator while maintaining integration with GENUS security and memory
systems.

Design principles:
- Ask/Stop gate integration for human confirmation
- Policy-based security enforcement
- Journal logging for all operations
- No auto-merge (only PR create/update/comment)
- Separation from core orchestrator
"""

from typing import Dict, Any, Optional

from genus.workspace.workspace import RunWorkspace
from genus.memory.run_journal import RunJournal
from genus.security.github_policy import GitHubPolicy, should_ask_for_github_write
from genus.github.client import GitHubClient
from genus.github.config import GitHubConfig
from genus.github.auth import get_github_token_from_env
from genus.tools.github_pr import (
    github_push_branch,
    github_create_or_update_pr,
    github_comment_pr,
    github_wait_for_checks,
)


class PublishResult:
    """Result of publish_run_as_pr operation.

    Attributes:
        success: Whether the operation succeeded.
        pr_url: URL of the created/updated PR (if successful).
        pr_number: PR number (if successful).
        action: Action taken ("created", "updated", "needs_confirmation").
        error: Error message (if failed).
        data: Additional result data.
    """

    def __init__(
        self,
        success: bool,
        pr_url: Optional[str] = None,
        pr_number: Optional[int] = None,
        action: Optional[str] = None,
        error: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.pr_url = pr_url
        self.pr_number = pr_number
        self.action = action
        self.error = error
        self.data = data or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "success": self.success,
            "action": self.action,
        }
        if self.pr_url:
            result["pr_url"] = self.pr_url
        if self.pr_number:
            result["pr_number"] = self.pr_number
        if self.error:
            result["error"] = self.error
        if self.data:
            result["data"] = self.data
        return result


async def publish_run_as_pr(
    run_id: str,
    workspace: RunWorkspace,
    *,
    github_config: GitHubConfig,
    policy: GitHubPolicy,
    journal: Optional[RunJournal] = None,
    title: str,
    body: str,
    branch: str,
    base: Optional[str] = None,
    comment: Optional[str] = None,
    wait_for_checks: bool = False,
    check_timeout_s: float = 600.0,
    files_changed: int = 0,
    tests_passed: bool = False,
) -> PublishResult:
    """Publish a GENUS run as a GitHub pull request.

    This is the main entry point for GitHub PR publishing from orchestrators.
    It handles the complete workflow:
    1. Ask/Stop gate decision (if required by policy)
    2. Push branch to remote
    3. Create or update PR
    4. Optionally add comment
    5. Optionally wait for CI checks

    Args:
        run_id: The run identifier.
        workspace: The RunWorkspace containing the repository.
        github_config: GitHubConfig instance.
        policy: GitHubPolicy instance.
        journal: Optional RunJournal for logging.
        title: PR title.
        body: PR description.
        branch: Branch name to push.
        base: Base branch (defaults to github_config.base_branch).
        comment: Optional comment to add to the PR.
        wait_for_checks: Whether to wait for CI checks to complete.
        check_timeout_s: Timeout for waiting for checks (default 600s).
        files_changed: Number of files changed (for Ask/Stop gate).
        tests_passed: Whether tests have passed (for Ask/Stop gate).

    Returns:
        PublishResult with operation status and PR details.

    Security:
        - Respects GitHubPolicy permissions
        - Ask/Stop gate prevents unauthorized writes (if enabled)
        - All operations logged to journal
        - No secrets in logs

    Example::

        from genus.dev.pr_publisher import publish_run_as_pr
        from genus.github.config import GitHubConfig
        from genus.security.github_policy import GitHubPolicy

        # Configure
        config = GitHubConfig(owner="WoltLab51", repo="Genus")
        policy = GitHubPolicy(
            allow_push=True,
            allow_create_pr=True,
            require_ask_stop_for_push=True,
        )

        # Publish
        result = await publish_run_as_pr(
            run_id="test-run-001",
            workspace=workspace,
            github_config=config,
            policy=policy,
            journal=journal,
            title="feat: add new feature",
            body="Description of changes",
            branch="feature/new-thing",
            tests_passed=True,
        )

        if result.success:
            print(f"PR created: {result.pr_url}")
        elif result.action == "needs_confirmation":
            print(f"Confirmation required: {result.data['reason']}")
        else:
            print(f"Error: {result.error}")
    """
    try:
        # Use default base if not provided
        if base is None:
            base = github_config.base_branch

        # Log start of publish operation
        if journal:
            journal.log_phase_start(
                phase="github_publish",
                run_id=run_id,
                branch=branch,
                base=base,
                title=title,
            )

        # Step 1: Ask/Stop gate decision
        if policy.require_ask_stop_for_push or policy.require_ask_stop_for_create_pr:
            should_ask, reason = should_ask_for_github_write(
                action="push",
                branch=branch,
                files_changed=files_changed,
                tests_passed=tests_passed,
            )

            if should_ask:
                # v1: Return "needs_confirmation" result
                # In future versions, this could integrate with an actual Ask/Stop
                # mechanism that prompts the user and waits for approval.
                if journal:
                    journal.log_decision(
                        phase="github_publish",
                        decision="Requires confirmation before proceeding",
                        reason=reason,
                    )

                return PublishResult(
                    success=False,
                    action="needs_confirmation",
                    data={
                        "reason": reason,
                        "branch": branch,
                        "files_changed": files_changed,
                        "tests_passed": tests_passed,
                    },
                )

        # Step 2: Push branch to remote
        push_result = await github_push_branch(
            workspace=workspace,
            remote=github_config.remote_name,
            branch=branch,
            policy=policy,
            journal=journal,
        )

        if not push_result.success:
            if journal:
                journal.log_error(
                    phase="github_publish",
                    error="Failed to push branch: {}".format(push_result.error),
                )
            return PublishResult(
                success=False,
                error="Push failed: {}".format(push_result.error),
            )

        # Step 3: Create or update PR
        # Get GitHub token
        try:
            token = get_github_token_from_env()
        except RuntimeError as e:
            if journal:
                journal.log_error(
                    phase="github_publish",
                    error="Failed to get GitHub token: {}".format(str(e)),
                )
            return PublishResult(
                success=False,
                error="GitHub token error: {}".format(str(e)),
            )

        # Create GitHub client
        client = GitHubClient(token=token, config=github_config)

        pr_result = await github_create_or_update_pr(
            workspace=workspace,
            client=client,
            config=github_config,
            head=branch,
            base=base,
            title=title,
            body=body,
            policy=policy,
            journal=journal,
        )

        if not pr_result.success:
            if journal:
                journal.log_error(
                    phase="github_publish",
                    error="Failed to create/update PR: {}".format(pr_result.error),
                )
            return PublishResult(
                success=False,
                error="PR operation failed: {}".format(pr_result.error),
            )

        pr_url = pr_result.data["pr_url"]
        pr_number = pr_result.data["number"]
        action = pr_result.data["action"]

        # Step 4: Optionally add comment
        if comment and policy.allow_comment:
            comment_result = await github_comment_pr(
                client=client,
                config=github_config,
                pr_number=pr_number,
                comment=comment,
                policy=policy,
                journal=journal,
            )

            if not comment_result.success and journal:
                journal.log_error(
                    phase="github_publish",
                    error="Failed to add comment: {}".format(comment_result.error),
                )

        # Step 5: Optionally wait for checks
        checks_summary = None
        if wait_for_checks:
            checks_result = await github_wait_for_checks(
                client=client,
                config=github_config,
                ref=branch,
                timeout_s=check_timeout_s,
                journal=journal,
            )

            if checks_result.success:
                checks_summary = checks_result.data
            elif journal:
                journal.log_error(
                    phase="github_publish",
                    error="Failed to wait for checks: {}".format(checks_result.error),
                )

        # Log successful publish
        if journal:
            journal.log_event(
                phase="github_publish",
                event_type="publish_success",
                summary="{} PR #{}: {}".format(action.capitalize(), pr_number, title),
                data={
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                    "action": action,
                    "branch": branch,
                    "base": base,
                    "checks_summary": checks_summary,
                },
            )

        return PublishResult(
            success=True,
            pr_url=pr_url,
            pr_number=pr_number,
            action=action,
            data={
                "branch": branch,
                "base": base,
                "checks_summary": checks_summary,
            },
        )

    except Exception as e:
        error_msg = "Error in publish_run_as_pr: {}".format(str(e))

        if journal:
            journal.log_error(
                phase="github_publish",
                error=error_msg,
            )

        return PublishResult(
            success=False,
            error=error_msg,
        )
