"""
Sandbox Execution Tool

Provides a high-level API for safe command execution in the sandbox.
"""

from typing import Optional, Dict, List

from genus.workspace.workspace import RunWorkspace
from genus.sandbox.models import SandboxCommand, SandboxResult
from genus.sandbox.policy import SandboxPolicy
from genus.sandbox.runner import SandboxRunner
from genus.security.kill_switch import DEFAULT_KILL_SWITCH


async def sandbox_run(
    workspace: RunWorkspace,
    argv: List[str],
    *,
    cwd: str = ".",
    env: Optional[Dict[str, str]] = None,
    timeout_s: Optional[float] = None,
    policy: Optional[SandboxPolicy] = None,
) -> SandboxResult:
    """Execute a command safely in the sandbox.

    This is the primary API for running commands in GENUS. It provides:
    - Automatic policy enforcement
    - Kill-switch integration
    - Output capture and truncation
    - Timeout handling

    Args:
        workspace: The RunWorkspace to execute in.
        argv: Command arguments as a list (e.g., ["python", "-m", "pytest"]).
        cwd: Relative working directory within workspace (default: ".").
        env: Optional environment variables.
        timeout_s: Optional timeout in seconds.
        policy: Optional custom SandboxPolicy (uses default if None).

    Returns:
        SandboxResult with execution details.

    Raises:
        RuntimeError: If kill-switch is disabled.
        SandboxPolicyError: If command violates policy.
        SandboxError: If execution fails.

    Example:
        ```python
        from genus.workspace.workspace import RunWorkspace
        from genus.tools.sandbox_run import sandbox_run

        workspace = RunWorkspace.create("test-run-001")
        workspace.ensure_dirs()

        # Run pytest
        result = await sandbox_run(
            workspace=workspace,
            argv=["python", "-m", "pytest", "tests/"],
            timeout_s=60,
        )

        if result.exit_code == 0:
            print("Tests passed!")
        else:
            print(f"Tests failed: {result.stderr}")
        ```
    """
    # Use default policy if none provided
    if policy is None:
        policy = SandboxPolicy()

    # Create command
    command = SandboxCommand(
        argv=argv,
        cwd=cwd,
        env=env,
    )

    # Create runner and execute
    runner = SandboxRunner(
        workspace=workspace,
        policy=policy,
        kill_switch=DEFAULT_KILL_SWITCH,
    )

    return await runner.run(command, timeout_s=timeout_s)
