"""
Sandbox Data Models

Defines the core data structures for sandbox command execution.
"""

from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class SandboxCommand:
    """A command to execute in the sandbox.

    Attributes:
        argv: Command arguments as a list (NOT a shell string).
              Example: ["python", "-m", "pytest", "tests/"]
        cwd: Relative subdirectory within workspace (e.g., "." or "src").
             Must not contain path traversal patterns.
        env: Optional environment variables to set.
             If None, inherits filtered environment from parent.
    """

    argv: List[str]
    cwd: str
    env: Optional[Dict[str, str]] = None


@dataclass
class SandboxResult:
    """Result of a sandbox command execution.

    Attributes:
        exit_code: Process exit code (0 = success).
        stdout: Standard output, truncated if exceeds max_stdout_bytes.
        stderr: Standard error, truncated if exceeds max_stderr_bytes.
        duration_s: Execution time in seconds.
        timed_out: True if execution was terminated due to timeout.
    """

    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool


class SandboxError(RuntimeError):
    """Base exception for sandbox execution errors."""

    pass


class SandboxPolicyError(ValueError):
    """Raised when a command violates sandbox policy."""

    pass
