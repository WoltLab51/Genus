"""
GitHub PR Tools

Provides safe, controlled GitHub PR operations.
All operations enforce GitHubPolicy and integrate with RunJournal.

Design principles:
- Deny-by-default via GitHubPolicy
- Kill-switch integration via sandbox git push
- Memory journal logging (no secrets)
- Ask/Stop gate for write operations
- No auto-merge (only create/update/comment)
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from genus.workspace.workspace import RunWorkspace
from genus.memory.run_journal import RunJournal
from genus.security.github_policy import GitHubPolicy
from genus.security.kill_switch import KillSwitch, DEFAULT_KILL_SWITCH
from genus.github.client import GitHubClient
from genus.github.config import GitHubConfig
from genus.tools.git_tools import git_push, ToolResult


async def github_push_branch(
    workspace: RunWorkspace,
    *,
    remote: str,
    branch: str,
    policy: GitHubPolicy,
    journal: Optional[RunJournal] = None,
    kill_switch: KillSwitch = DEFAULT_KILL_SWITCH,
) -> ToolResult:
    """Push a branch to GitHub remote.

    This is a controlled write operation that:
    - Validates against GitHubPolicy
    - Uses sandboxed git push (respects kill-switch)
    - Logs to journal (without secrets)

    Args:
        workspace: The RunWorkspace containing the git repository.
        remote: Remote name (e.g., "origin").
        branch: Branch name to push.
        policy: GitHubPolicy instance.
        journal: Optional RunJournal for logging.
        kill_switch: KillSwitch instance (defaults to DEFAULT_KILL_SWITCH).

    Returns:
        ToolResult with push status.

    Security:
        - Requires policy.allow_push = True
        - Respects kill-switch via sandboxed git
        - No credentials in journal logs

    Example::

        policy = GitHubPolicy(allow_push=True)
        result = await github_push_branch(
            workspace=workspace,
            remote="origin",
            branch="feature/test",
            policy=policy,
            journal=journal,
        )

        if result.success:
            print("Push successful")
    """
    try:
        # Validate action against policy
        policy.assert_action_allowed("push")

        # Check kill-switch
        kill_switch.assert_enabled()

        # Log to journal (if provided)
        if journal:
            journal.log_tool_use(
                phase="github",
                tool_name="github_push_branch",
                remote=remote,
                branch=branch,
            )

        # Execute git push via sandbox
        result = await git_push(
            workspace=workspace,
            remote=remote,
            branch=branch,
        )

        # Log result to journal
        if journal and result.success:
            journal.log_event(
                phase="github",
                event_type="push_success",
                summary="Successfully pushed branch '{}' to remote '{}'".format(branch, remote),
                data={
                    "remote": remote,
                    "branch": branch,
                },
            )

        return result

    except Exception as e:
        error_msg = "Error in github_push_branch: {}".format(str(e))

        # Log error to journal
        if journal:
            journal.log_error(
                phase="github",
                error=error_msg,
            )

        return ToolResult(
            success=False,
            data=None,
            error=error_msg,
        )


async def github_create_or_update_pr(
    workspace: RunWorkspace,
    *,
    client: GitHubClient,
    config: GitHubConfig,
    head: str,
    base: str,
    title: str,
    body: str,
    policy: GitHubPolicy,
    journal: Optional[RunJournal] = None,
) -> ToolResult:
    """Create a new PR or update an existing one.

    If an open PR already exists for the head/base combination, it will be updated.
    Otherwise, a new PR will be created.

    Args:
        workspace: The RunWorkspace (for context).
        client: GitHubClient instance.
        config: GitHubConfig instance.
        head: Branch to merge from.
        base: Branch to merge into.
        title: PR title.
        body: PR description.
        policy: GitHubPolicy instance.
        journal: Optional RunJournal for logging.

    Returns:
        ToolResult with PR data: {"pr_url": "...", "number": N, "action": "created"|"updated"}.

    Security:
        - Requires policy.allow_create_pr = True
        - Validates repo against policy.allowed_owner_repos
        - Enforces max body size from policy
        - No secrets logged to journal

    Example::

        policy = GitHubPolicy(allow_create_pr=True)
        result = await github_create_or_update_pr(
            workspace=workspace,
            client=client,
            config=config,
            head="feature/test",
            base="main",
            title="Add new feature",
            body="Description",
            policy=policy,
            journal=journal,
        )

        if result.success:
            print(f"PR: {result.data['pr_url']}")
    """
    try:
        # Validate action against policy
        policy.assert_action_allowed("create_pr")

        # Validate repo against policy
        policy.assert_repo_allowed(config.owner, config.repo)

        # Enforce max body size
        if len(body) > policy.max_pr_body_chars:
            return ToolResult(
                success=False,
                data=None,
                error="PR body exceeds max size: {} > {} chars".format(
                    len(body), policy.max_pr_body_chars
                ),
            )

        # Log to journal (if provided)
        if journal:
            journal.log_tool_use(
                phase="github",
                tool_name="github_create_or_update_pr",
                head=head,
                base=base,
                title=title,
            )

        # Check if PR already exists
        existing_pr = client.find_open_pull_request(
            owner=config.owner,
            repo=config.repo,
            head=head,
            base=base,
        )

        if existing_pr:
            # Update existing PR
            pr = client.update_pull_request(
                owner=config.owner,
                repo=config.repo,
                pr_number=existing_pr["number"],
                title=title,
                body=body,
            )
            action = "updated"
        else:
            # Create new PR
            pr = client.create_pull_request(
                owner=config.owner,
                repo=config.repo,
                head=head,
                base=base,
                title=title,
                body=body,
            )
            action = "created"

        # Extract PR data
        pr_url = pr.get("html_url", "")
        pr_number = pr.get("number", 0)

        # Log to journal
        if journal:
            journal.log_event(
                phase="github",
                event_type="pr_{}".format(action),
                summary="{} PR #{}: {}".format(action.capitalize(), pr_number, title),
                data={
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                    "action": action,
                    "head": head,
                    "base": base,
                },
            )

        return ToolResult(
            success=True,
            data={
                "pr_url": pr_url,
                "number": pr_number,
                "action": action,
            },
        )

    except Exception as e:
        error_msg = "Error in github_create_or_update_pr: {}".format(str(e))

        # Log error to journal
        if journal:
            journal.log_error(
                phase="github",
                error=error_msg,
            )

        return ToolResult(
            success=False,
            data=None,
            error=error_msg,
        )


async def github_comment_pr(
    *,
    client: GitHubClient,
    config: GitHubConfig,
    pr_number: int,
    comment: str,
    policy: GitHubPolicy,
    journal: Optional[RunJournal] = None,
) -> ToolResult:
    """Add a comment to a pull request.

    Args:
        client: GitHubClient instance.
        config: GitHubConfig instance.
        pr_number: PR number to comment on.
        comment: Comment text.
        policy: GitHubPolicy instance.
        journal: Optional RunJournal for logging.

    Returns:
        ToolResult with comment data.

    Security:
        - Requires policy.allow_comment = True
        - Validates repo against policy.allowed_owner_repos
        - No secrets logged to journal

    Example::

        policy = GitHubPolicy(allow_comment=True)
        result = await github_comment_pr(
            client=client,
            config=config,
            pr_number=123,
            comment="Tests passed!",
            policy=policy,
            journal=journal,
        )

        if result.success:
            print(f"Comment added: {result.data['comment_url']}")
    """
    try:
        # Validate action against policy
        policy.assert_action_allowed("comment")

        # Validate repo against policy
        policy.assert_repo_allowed(config.owner, config.repo)

        # Log to journal (if provided)
        if journal:
            journal.log_tool_use(
                phase="github",
                tool_name="github_comment_pr",
                pr_number=pr_number,
            )

        # Create comment
        comment_data = client.create_issue_comment(
            owner=config.owner,
            repo=config.repo,
            issue_number=pr_number,
            body=comment,
        )

        comment_url = comment_data.get("html_url", "")

        # Log to journal
        if journal:
            journal.log_event(
                phase="github",
                event_type="pr_comment",
                summary="Added comment to PR #{}".format(pr_number),
                data={
                    "pr_number": pr_number,
                    "comment_url": comment_url,
                },
            )

        return ToolResult(
            success=True,
            data={
                "comment_url": comment_url,
                "pr_number": pr_number,
            },
        )

    except Exception as e:
        error_msg = "Error in github_comment_pr: {}".format(str(e))

        # Log error to journal
        if journal:
            journal.log_error(
                phase="github",
                error=error_msg,
            )

        return ToolResult(
            success=False,
            data=None,
            error=error_msg,
        )


async def github_wait_for_checks(
    *,
    client: GitHubClient,
    config: GitHubConfig,
    ref: str,
    timeout_s: float = 600.0,
    poll_interval_s: float = 30.0,
    journal: Optional[RunJournal] = None,
) -> ToolResult:
    """Wait for GitHub check runs to complete.

    Polls check-runs API until all checks complete or timeout is reached.

    Args:
        client: GitHubClient instance.
        config: GitHubConfig instance.
        ref: Commit SHA or branch name.
        timeout_s: Maximum time to wait in seconds (default 600 = 10 minutes).
        poll_interval_s: Seconds between polls (default 30).
        journal: Optional RunJournal for logging.

    Returns:
        ToolResult with check summary:
        {
            "conclusion": "success"|"failure"|"timeout",
            "total_checks": N,
            "passed": N,
            "failed": N,
            "pending": N,
            "failing_checks": [...],
        }

    Example::

        result = await github_wait_for_checks(
            client=client,
            config=config,
            ref="abc123",
            timeout_s=300,
            journal=journal,
        )

        if result.success and result.data["conclusion"] == "success":
            print("All checks passed!")
    """
    try:
        # Log to journal (if provided)
        if journal:
            journal.log_tool_use(
                phase="github",
                tool_name="github_wait_for_checks",
                ref=ref,
                timeout_s=timeout_s,
            )

        start_time = time.time()
        last_status = None

        while True:
            elapsed = time.time() - start_time

            if elapsed >= timeout_s:
                # Timeout
                summary = {
                    "conclusion": "timeout",
                    "total_checks": 0,
                    "passed": 0,
                    "failed": 0,
                    "pending": 0,
                    "failing_checks": [],
                }

                if journal:
                    journal.log_event(
                        phase="github",
                        event_type="checks_timeout",
                        summary="Check runs timed out after {} seconds".format(timeout_s),
                        data=summary,
                    )

                return ToolResult(
                    success=True,
                    data=summary,
                )

            # Get check runs
            check_runs = client.list_check_runs_for_ref(
                owner=config.owner,
                repo=config.repo,
                ref=ref,
            )

            # Analyze check runs
            total_checks = len(check_runs)
            passed = 0
            failed = 0
            pending = 0
            failing_checks = []

            for check in check_runs:
                status = check.get("status", "")
                conclusion = check.get("conclusion", "")

                if status == "completed":
                    if conclusion == "success":
                        passed += 1
                    else:
                        failed += 1
                        failing_checks.append({
                            "name": check.get("name", ""),
                            "conclusion": conclusion,
                        })
                else:
                    pending += 1

            # Check if all completed
            if pending == 0 and total_checks > 0:
                # All checks completed
                conclusion = "success" if failed == 0 else "failure"
                summary = {
                    "conclusion": conclusion,
                    "total_checks": total_checks,
                    "passed": passed,
                    "failed": failed,
                    "pending": pending,
                    "failing_checks": failing_checks,
                }

                if journal:
                    journal.log_event(
                        phase="github",
                        event_type="checks_completed",
                        summary="Check runs completed: {}".format(conclusion),
                        data=summary,
                    )

                return ToolResult(
                    success=True,
                    data=summary,
                )

            # Log progress if status changed
            current_status = (passed, failed, pending)
            if current_status != last_status:
                if journal:
                    journal.log_event(
                        phase="github",
                        event_type="checks_progress",
                        summary="Checks: {} passed, {} failed, {} pending".format(passed, failed, pending),
                        data={
                            "passed": passed,
                            "failed": failed,
                            "pending": pending,
                        },
                    )
                last_status = current_status

            # Wait before next poll
            await asyncio.sleep(poll_interval_s)

    except Exception as e:
        error_msg = "Error in github_wait_for_checks: {}".format(str(e))

        # Log error to journal
        if journal:
            journal.log_error(
                phase="github",
                error=error_msg,
            )

        return ToolResult(
            success=False,
            data=None,
            error=error_msg,
        )
