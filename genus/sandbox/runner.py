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
from genus.security.kill_switch import KillSwitch, DEFAULT_KILL_SWITCH


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
            RuntimeError: If kill-switch is disabled.
            SandboxPolicyError: If command violates policy.
            SandboxError: If execution fails.
        """
        # Check kill-switch
        self.kill_switch.assert_enabled()

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

        Args:
            env: Environment variables from command.

        Returns:
            Filtered environment dict or None to inherit parent env.
        """
        if env is None:
            # Inherit parent environment (already filtered by OS)
            return None

        # Filter to only allowed keys
        filtered = {
            k: v for k, v in env.items() if k in self.policy.allowed_env_keys
        }

        # Merge with minimal safe environment
        # Add PATH from parent if not present
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
