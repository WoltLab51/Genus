"""
Sandbox Runner

Executes commands in an isolated environment with security restrictions.
"""

import asyncio
import time
import os
from typing import Optional

from genus.workspace.workspace import RunWorkspace
from genus.workspace.paths import ensure_within
from genus.sandbox.models import (
    SandboxCommand,
    SandboxResult,
    SandboxError,
)
from genus.sandbox.policy import SandboxPolicy
from genus.security.kill_switch import KillSwitch, KillSwitchActiveError, DEFAULT_KILL_SWITCH

# Safe environment variable keys that may be passed to subprocesses.
# Only keys in this set are candidates when env=None (default).
_SAFE_ENV_KEYS = frozenset({
    "PATH",
    "HOME",
    "USER",
    "USERNAME",        # Windows
    "LOGNAME",
    "SHELL",
    "TMPDIR",
    "TEMP",            # Windows
    "TMP",             # Windows
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    # Git-specific (needed for commits)
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
    "GIT_SSH_COMMAND",
    # Python
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "CONDA_DEFAULT_ENV",
})

# Explicitly blocked keys — these must NEVER be passed to subprocesses.
_BLOCKED_ENV_KEYS = frozenset({
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AZURE_CLIENT_SECRET",
    "DATABASE_URL",
    "SECRET_KEY",
    "API_KEY",
})


class SandboxRunner:
    """Execute commands in a sandboxed environment.

    Provides isolated command execution with:
    - Kill-switch integration
    - Policy validation
    - Working directory restriction
    - Timeout enforcement
    - Output capture and truncation

    Example:
        ```python
        from genus.workspace.workspace import RunWorkspace
        from genus.sandbox.policy import SandboxPolicy
        from genus.sandbox.runner import SandboxRunner
        from genus.sandbox.models import SandboxCommand

        workspace = RunWorkspace.create("test-run-001")
        workspace.ensure_dirs()

        policy = SandboxPolicy()
        runner = SandboxRunner(workspace=workspace, policy=policy)

        command = SandboxCommand(
            argv=["python", "-m", "pytest", "tests/"],
            cwd="."
        )

        result = await runner.run(command, timeout_s=60)
        print(f"Exit code: {result.exit_code}")
        print(f"Stdout: {result.stdout}")
        ```
    """

    def __init__(
        self,
        *,
        workspace: RunWorkspace,
        policy: SandboxPolicy,
        kill_switch: KillSwitch = DEFAULT_KILL_SWITCH,
    ):
        """Initialize the sandbox runner.

        Args:
            workspace: The RunWorkspace to execute commands in.
            policy: The SandboxPolicy to enforce.
            kill_switch: The KillSwitch instance (defaults to DEFAULT_KILL_SWITCH).
        """
        self.workspace = workspace
        self.policy = policy
        self.kill_switch = kill_switch

    async def run(
        self,
        cmd: SandboxCommand,
        *,
        timeout_s: Optional[float] = None,
    ) -> SandboxResult:
        """Execute a command in the sandbox.

        Args:
            cmd: The command to execute.
            timeout_s: Optional timeout in seconds.
                      If None, uses policy.default_timeout_s.

        Returns:
            SandboxResult with execution details.

        Raises:
            KillSwitchActiveError: If the kill-switch is active.
            SandboxPolicyError: If command violates policy.
            SandboxError: If execution fails.
        """
        # Check kill-switch
        self.kill_switch.assert_not_active()

        # Validate command against policy
        self.policy.validate(cmd)

        # Determine timeout
        if timeout_s is None:
            timeout_s = self.policy.default_timeout_s
        elif timeout_s > self.policy.max_timeout_s:
            timeout_s = self.policy.max_timeout_s

        # Resolve working directory within workspace
        cwd_abs = ensure_within(
            self.workspace.repo_dir,
            self.workspace.repo_dir / cmd.cwd,
        )

        # Filter environment variables
        filtered_env = self._filter_env(cmd.env)

        # Execute command
        start_time = time.time()
        timed_out = False
        exit_code = 0
        stdout = ""
        stderr = ""

        try:
            # Create subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd.argv,
                cwd=str(cwd_abs),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=filtered_env,
            )

            # Wait with timeout
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_s
                )
                exit_code = proc.returncode
            except asyncio.TimeoutError:
                # Kill the process on timeout
                timed_out = True
                exit_code = 124  # Standard timeout exit code

                try:
                    proc.kill()
                    # Best effort to collect partial output
                    try:
                        stdout_bytes, stderr_bytes = await asyncio.wait_for(
                            proc.communicate(), timeout=1.0
                        )
                    except asyncio.TimeoutError:
                        stdout_bytes = b""
                        stderr_bytes = b""
                except ProcessLookupError:
                    # Process already terminated
                    stdout_bytes = b""
                    stderr_bytes = b""

            # Decode and truncate output
            stdout = self._decode_and_truncate(
                stdout_bytes, self.policy.max_stdout_bytes, "stdout"
            )
            stderr = self._decode_and_truncate(
                stderr_bytes, self.policy.max_stderr_bytes, "stderr"
            )

        except Exception as e:
            raise SandboxError("Failed to execute command: {}".format(e))

        finally:
            duration_s = time.time() - start_time

        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_s=duration_s,
            timed_out=timed_out,
        )

    def _filter_env(
        self, env: Optional[dict]
    ) -> Optional[dict]:
        """Filter environment variables based on policy.

        When env is None (default), builds a minimal safe environment from the
        parent process environment — only safe, non-secret keys are included.
        This prevents credential leakage to subprocess.

        Args:
            env: Explicit environment dict from command, or None for safe default.

        Returns:
            Filtered environment dict. Never returns None (never inherits full parent env).
        """
        if env is None:
            # Build minimal safe environment from parent — never inherit everything
            safe_env = {}
            for key in _SAFE_ENV_KEYS:
                if key in os.environ and key not in _BLOCKED_ENV_KEYS:
                    safe_env[key] = os.environ[key]
            return safe_env if safe_env else {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}

        # Explicit env dict provided: filter to allowed keys only
        filtered = {
            k: v for k, v in env.items()
            if k in self.policy.allowed_env_keys and k not in _BLOCKED_ENV_KEYS
        }

        # Always include PATH from safe env if not already in filtered
        if "PATH" not in filtered and "PATH" in os.environ:
            filtered["PATH"] = os.environ["PATH"]

        return filtered

    def _decode_and_truncate(
        self, data: bytes, max_bytes: int, stream_name: str
    ) -> str:
        """Decode bytes and truncate if necessary.

        Args:
            data: Raw bytes from process.
            max_bytes: Maximum allowed bytes.
            stream_name: Name of stream (for truncation marker).

        Returns:
            Decoded string, possibly truncated.
        """
        if len(data) <= max_bytes:
            try:
                return data.decode("utf-8", errors="replace")
            except Exception:
                return data.decode("latin-1", errors="replace")

        # Truncate and add marker
        truncated = data[:max_bytes]
        try:
            result = truncated.decode("utf-8", errors="replace")
        except Exception:
            result = truncated.decode("latin-1", errors="replace")

        result += "\n... [{}] OUTPUT TRUNCATED: {}/{} bytes ...".format(
            stream_name.upper(), len(data), max_bytes
        )
        return result
