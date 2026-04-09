"""
Git Tools

Provides safe git operations via SandboxRunner.
All git commands are executed via allowlisted argv patterns.

Design principles:
- No shell execution: All commands use argv lists
- Allowlist enforcement: Only specific git commands are permitted
- Workspace-scoped: All operations happen within RunWorkspace

Security:
- All git commands run through SandboxRunner with SandboxPolicy
- Command arguments must match allowlisted patterns
- Branch and remote names are validated internally before use
- No arbitrary command execution
"""

import re
from typing import Any, Dict, List, Optional

from genus.workspace.workspace import RunWorkspace
from genus.sandbox.models import SandboxCommand, SandboxResult
from genus.sandbox.runner import SandboxRunner
from genus.sandbox.policy import SandboxPolicy
from genus.security.kill_switch import DEFAULT_KILL_SWITCH

# Allowed characters: alphanumeric, hyphens, underscores, slashes, dots
_BRANCH_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._\-/]*$')
_BRANCH_MAX_LEN = 200

# Remote names may not contain slashes
_REMOTE_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._\-]*$')
_REMOTE_MAX_LEN = 100


def _validate_branch_name(name: str) -> str:
    """Validate and return a git branch name.

    Raises:
        ValueError: If the name is invalid or potentially dangerous.
    """
    if not name or not name.strip():
        raise ValueError("Branch name cannot be empty")
    name = name.strip()
    if len(name) > _BRANCH_MAX_LEN:
        raise ValueError(
            "Branch name too long: {} > {} chars".format(len(name), _BRANCH_MAX_LEN)
        )
    if name.startswith("-"):
        raise ValueError(
            "Branch name must not start with '-' (would be interpreted as flag): {!r}".format(name)
        )
    if ".." in name:
        raise ValueError("Branch name must not contain '..': {!r}".format(name))
    if "@{" in name:
        raise ValueError("Branch name must not contain '@{{': {!r}".format(name))
    if name.endswith(".lock"):
        raise ValueError("Branch name must not end with '.lock': {!r}".format(name))
    if name.endswith("."):
        raise ValueError("Branch name must not end with '.': {!r}".format(name))
    if not _BRANCH_NAME_RE.match(name):
        raise ValueError(
            "Branch name contains invalid characters: {!r}. "
            "Allowed: alphanumeric, hyphens, underscores, slashes, dots.".format(name)
        )
    return name


def _validate_remote_name(name: str) -> str:
    """Validate and return a git remote name.

    Raises:
        ValueError: If the name is invalid or potentially dangerous.
    """
    if not name or not name.strip():
        raise ValueError("Remote name cannot be empty")
    name = name.strip()
    if len(name) > _REMOTE_MAX_LEN:
        raise ValueError("Remote name too long: {!r}".format(name))
    if name.startswith("-"):
        raise ValueError("Remote name must not start with '-': {!r}".format(name))
    if not _REMOTE_NAME_RE.match(name):
        raise ValueError(
            "Remote name contains invalid characters: {!r}. "
            "Allowed: alphanumeric, hyphens, underscores, dots.".format(name)
        )
    return name


class ToolResult:
    """Standard response format for git tools.

    Attributes:
        success: Whether the operation succeeded.
        data: The main result data.
        error: Optional error message if success is False.
    """

    def __init__(self, success: bool, data: Any, error: Optional[str] = None):
        self.success = success
        self.data = data
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to a dictionary for serialization."""
        result = {
            "success": self.success,
            "data": self.data,
        }
        if self.error is not None:
            result["error"] = self.error
        return result


async def git_status(workspace: RunWorkspace) -> ToolResult:
    """Get git status in porcelain format.

    Args:
        workspace: The RunWorkspace containing the git repository.

    Returns:
        ToolResult with status output or error.

    Example::

        result = await git_status(workspace)
        if result.success:
            print(result.data["stdout"])  # Porcelain status output
    """
    try:
        # Create policy that allows git status
        policy = _create_git_policy()

        # Create command
        command = SandboxCommand(
            argv=["git", "status", "--porcelain"],
            cwd=".",
        )

        # Execute via sandbox
        runner = SandboxRunner(
            workspace=workspace,
            policy=policy,
            kill_switch=DEFAULT_KILL_SWITCH,
        )

        result = await runner.run(command, timeout_s=30.0)

        if result.exit_code != 0:
            return ToolResult(
                success=False,
                data=None,
                error="git status failed: {}".format(result.stderr),
            )

        return ToolResult(
            success=True,
            data={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            },
        )

    except Exception as e:
        return ToolResult(
            success=False,
            data=None,
            error="Error running git status: {}".format(str(e)),
        )


async def git_diff(
    workspace: RunWorkspace,
    *,
    staged: bool = False,
) -> ToolResult:
    """Get git diff output.

    Args:
        workspace: The RunWorkspace containing the git repository.
        staged: If True, show staged changes (--staged), otherwise unstaged.

    Returns:
        ToolResult with diff output or error.

    Example::

        result = await git_diff(workspace, staged=False)
        if result.success:
            print(result.data["stdout"])  # Diff output
    """
    try:
        # Create policy that allows git diff
        policy = _create_git_policy()

        # Build argv
        if staged:
            argv = ["git", "diff", "--staged"]
        else:
            argv = ["git", "diff"]

        # Create command
        command = SandboxCommand(
            argv=argv,
            cwd=".",
        )

        # Execute via sandbox
        runner = SandboxRunner(
            workspace=workspace,
            policy=policy,
            kill_switch=DEFAULT_KILL_SWITCH,
        )

        result = await runner.run(command, timeout_s=60.0)

        if result.exit_code != 0:
            return ToolResult(
                success=False,
                data=None,
                error="git diff failed: {}".format(result.stderr),
            )

        return ToolResult(
            success=True,
            data={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            },
        )

    except Exception as e:
        return ToolResult(
            success=False,
            data=None,
            error="Error running git diff: {}".format(str(e)),
        )


async def git_create_branch(
    workspace: RunWorkspace,
    branch: str,
) -> ToolResult:
    """Create and checkout a new git branch.

    Args:
        workspace: The RunWorkspace containing the git repository.
        branch: Name of the branch to create.

    Returns:
        ToolResult with success status or error.

    Security:
        Branch name is validated internally via `_validate_branch_name()`.
        This function uses argv list to prevent shell injection.

    Example::

        result = await git_create_branch(workspace, "feature/new-thing")
        if result.success:
            print("Branch created successfully")
    """
    try:
        branch = _validate_branch_name(branch)

        # Create policy that allows git checkout
        policy = _create_git_policy()

        # Create command
        command = SandboxCommand(
            argv=["git", "checkout", "-b", branch],
            cwd=".",
        )

        # Execute via sandbox
        runner = SandboxRunner(
            workspace=workspace,
            policy=policy,
            kill_switch=DEFAULT_KILL_SWITCH,
        )

        result = await runner.run(command, timeout_s=30.0)

        if result.exit_code != 0:
            return ToolResult(
                success=False,
                data=None,
                error="git checkout -b failed: {}".format(result.stderr),
            )

        return ToolResult(
            success=True,
            data={
                "branch": branch,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            },
        )

    except ValueError as e:
        return ToolResult(
            success=False,
            data=None,
            error="Invalid branch name: {}".format(e),
        )
    except Exception as e:
        return ToolResult(
            success=False,
            data=None,
            error="Error creating branch: {}".format(str(e)),
        )


async def git_add_all(workspace: RunWorkspace) -> ToolResult:
    """Stage all changes in the repository.

    Args:
        workspace: The RunWorkspace containing the git repository.

    Returns:
        ToolResult with success status or error.

    Example::

        result = await git_add_all(workspace)
        if result.success:
            print("Changes staged")
    """
    try:
        # Create policy that allows git add
        policy = _create_git_policy()

        # Create command
        command = SandboxCommand(
            argv=["git", "add", "-A"],
            cwd=".",
        )

        # Execute via sandbox
        runner = SandboxRunner(
            workspace=workspace,
            policy=policy,
            kill_switch=DEFAULT_KILL_SWITCH,
        )

        result = await runner.run(command, timeout_s=60.0)

        if result.exit_code != 0:
            return ToolResult(
                success=False,
                data=None,
                error="git add -A failed: {}".format(result.stderr),
            )

        return ToolResult(
            success=True,
            data={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            },
        )

    except Exception as e:
        return ToolResult(
            success=False,
            data=None,
            error="Error staging changes: {}".format(str(e)),
        )


async def git_commit(
    workspace: RunWorkspace,
    message: str,
) -> ToolResult:
    """Create a git commit with the given message.

    Args:
        workspace: The RunWorkspace containing the git repository.
        message: Commit message.

    Returns:
        ToolResult with success status or error.

    Security:
        Message is passed as a single argv element, preventing shell injection.
        No shell metacharacters are interpreted.

    Example::

        result = await git_commit(workspace, "feat: add new feature")
        if result.success:
            print("Commit created")
    """
    try:
        # Create policy that allows git commit
        policy = _create_git_policy()

        # Create command
        # Use -m flag to pass message directly (no editor)
        command = SandboxCommand(
            argv=["git", "commit", "-m", message],
            cwd=".",
        )

        # Execute via sandbox
        runner = SandboxRunner(
            workspace=workspace,
            policy=policy,
            kill_switch=DEFAULT_KILL_SWITCH,
        )

        result = await runner.run(command, timeout_s=60.0)

        # Note: git commit returns 1 if nothing to commit, which is not always an error
        if result.exit_code != 0:
            # Check if it's "nothing to commit"
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                return ToolResult(
                    success=True,
                    data={
                        "nothing_to_commit": True,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "exit_code": result.exit_code,
                    },
                )
            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error="git commit failed: {}".format(result.stderr),
                )

        return ToolResult(
            success=True,
            data={
                "nothing_to_commit": False,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            },
        )

    except Exception as e:
        return ToolResult(
            success=False,
            data=None,
            error="Error creating commit: {}".format(str(e)),
        )


async def git_push(
    workspace: RunWorkspace,
    *,
    remote: str = "origin",
    branch: str,
    force: bool = False,
) -> ToolResult:
    """Push a branch to a remote repository.

    Args:
        workspace: The RunWorkspace containing the git repository.
        remote: Remote name (default "origin").
        branch: Branch name to push.
        force: If True, force push with --force-with-lease (safer than --force).

    Returns:
        ToolResult with success status or error.

    Security:
        - Only allowed when policy permits
        - Uses --force-with-lease instead of --force for safety
        - Branch and remote names are validated internally via
          `_validate_branch_name()` and `_validate_remote_name()`

    Example::

        result = await git_push(workspace, remote="origin", branch="feature/test")
        if result.success:
            print("Push successful")
    """
    try:
        branch = _validate_branch_name(branch)
        remote = _validate_remote_name(remote)

        # Create policy that allows git push
        policy = _create_git_policy()

        # Build argv
        argv = ["git", "push", remote, branch]
        if force:
            # Use --force-with-lease for safer force push
            argv.append("--force-with-lease")

        # Create command
        command = SandboxCommand(
            argv=argv,
            cwd=".",
        )

        # Execute via sandbox
        runner = SandboxRunner(
            workspace=workspace,
            policy=policy,
            kill_switch=DEFAULT_KILL_SWITCH,
        )

        result = await runner.run(command, timeout_s=120.0)

        if result.exit_code != 0:
            return ToolResult(
                success=False,
                data=None,
                error="git push failed: {}".format(result.stderr),
            )

        return ToolResult(
            success=True,
            data={
                "remote": remote,
                "branch": branch,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            },
        )

    except ValueError as e:
        return ToolResult(
            success=False,
            data=None,
            error="Invalid git argument: {}".format(e),
        )
    except Exception as e:
        return ToolResult(
            success=False,
            data=None,
            error="Error pushing branch: {}".format(str(e)),
        )


def _create_git_policy() -> SandboxPolicy:
    """Create a SandboxPolicy configured for git operations.

    Returns:
        SandboxPolicy with git command allowlist and banned dangerous flags.
    """
    return SandboxPolicy(
        allowed_executables={"git", "git.exe"},
        allowed_argv_prefixes=[
            ["git", "status", "--porcelain"],
            ["git", "diff"],
            ["git", "diff", "--staged"],
            ["git", "checkout", "-b"],
            ["git", "add", "-A"],
            ["git", "commit", "-m"],
            ["git", "push"],
        ],
        # Explicitly ban dangerous push flags (--force-with-lease is intentionally allowed)
        banned_flags=["--force", "-f", "--no-verify", "--delete", "--mirror", "--all"],
        max_stdout_bytes=5 * 1024 * 1024,  # 5 MB for diffs
        max_stderr_bytes=1024 * 1024,  # 1 MB
        default_timeout_s=60.0,
        max_timeout_s=120.0,
    )
