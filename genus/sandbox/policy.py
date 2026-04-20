"""
Sandbox Security Policy

Implements deny-by-default security policy for sandbox command execution.
"""

from typing import Set, List, Optional
from genus.sandbox.models import SandboxCommand, SandboxPolicyError


class SandboxPolicy:
    """Security policy for sandbox command execution.

    Implements a deny-by-default model where only explicitly allowed
    executables and argument patterns are permitted.

    Attributes:
        allowed_executables: Set of allowed executable names.
        allowed_argv_prefixes: List of allowed command argument prefixes.
        allowed_env_keys: Set of allowed environment variable keys.
        max_stdout_bytes: Maximum stdout size before truncation.
        max_stderr_bytes: Maximum stderr size before truncation.
        default_timeout_s: Default timeout in seconds.
        max_timeout_s: Maximum allowed timeout in seconds.
    """

    def __init__(
        self,
        allowed_executables: Set[str] = None,
        allowed_argv_prefixes: List[List[str]] = None,
        allowed_env_keys: Set[str] = None,
        max_stdout_bytes: int = 1024 * 1024,  # 1 MB
        max_stderr_bytes: int = 1024 * 1024,  # 1 MB
        default_timeout_s: float = 300.0,  # 5 minutes
        max_timeout_s: float = 600.0,  # 10 minutes
        banned_flags: Optional[List[str]] = None,
    ):
        """Initialize sandbox policy.

        Args:
            allowed_executables: Set of allowed executable names.
                                Default: {"python", "python.exe", "pytest"}
            allowed_argv_prefixes: List of allowed command prefixes.
                                  Default: common python/pytest/git prefixes
                                  (excludes ["python", "-c"] — see NOTE below)
            allowed_env_keys: Set of allowed environment variable keys.
                             Default: empty set (no env vars allowed)
            max_stdout_bytes: Maximum stdout size before truncation.
            max_stderr_bytes: Maximum stderr size before truncation.
            default_timeout_s: Default timeout in seconds.
            max_timeout_s: Maximum allowed timeout in seconds.
            banned_flags: Flags that must never appear in argv, regardless of
                         prefix matching. Default list bans dangerous push flags
                         (--force, -f, --no-verify, --delete, --mirror, --all,
                         --tags). Pass an empty list to disable all flag banning.
        """
        # Default allowed executables for Python/pytest and git
        if allowed_executables is None:
            allowed_executables = {"python", "python.exe", "pytest", "git", "git.exe"}

        # Default allowed argv prefixes
        # NOTE: ["python", "-c"] is intentionally NOT included — it would allow
        # arbitrary code execution and defeats the purpose of the sandbox policy.
        # If inline Python execution is needed, add a dedicated, restricted prefix.
        if allowed_argv_prefixes is None:
            allowed_argv_prefixes = [
                # Python/pytest commands
                ["python", "-m", "pytest"],
                ["python", "-m", "ruff"],
                ["python", "--version"],
                ["pytest"],
                # Git commands (PR #28)
                ["git", "status", "--porcelain"],
                ["git", "diff"],
                ["git", "diff", "--staged"],
                ["git", "checkout", "-b"],
                ["git", "add", "-A"],
                ["git", "commit", "-m"],
            ]
        # Default: no environment variables allowed
        if allowed_env_keys is None:
            allowed_env_keys = set()

        # Default banned flags: dangerous push/destructive flags
        if banned_flags is None:
            banned_flags = [
                "--force",      # dangerous force push
                "-f",           # short form of --force
                "--no-verify",  # bypasses pre-push hooks
                "--delete",     # deletes remote branches
                "--mirror",     # mirrors entire repository
                "--all",        # pushes all branches
                "--tags",       # pushes all tags uncontrolled
            ]

        self.allowed_executables = set(allowed_executables)
        self.allowed_argv_prefixes = allowed_argv_prefixes
        self.allowed_env_keys = set(allowed_env_keys)
        self.max_stdout_bytes = max_stdout_bytes
        self.max_stderr_bytes = max_stderr_bytes
        self.default_timeout_s = default_timeout_s
        self.max_timeout_s = max_timeout_s
        self.banned_flags = list(banned_flags)

    def validate(self, command: SandboxCommand) -> None:
        """Validate a command against this policy.

        Args:
            command: The command to validate.

        Raises:
            SandboxPolicyError: If the command violates the policy.
        """
        # Check for empty argv
        if not command.argv or len(command.argv) == 0:
            raise SandboxPolicyError("Command argv cannot be empty")

        # Extract executable (first element)
        executable = command.argv[0]

        # Check if executable is allowed
        if executable not in self.allowed_executables:
            raise SandboxPolicyError(
                "Executable '{}' is not in allowlist. Allowed: {}".format(
                    executable, sorted(self.allowed_executables)
                )
            )

        # Check for shell metacharacters in argv (defense in depth)
        # Only check for truly dangerous patterns that indicate shell execution
        # Semicolons in Python code strings are OK since we use exec, not shell
        dangerous_patterns = ["&&", "||", "|", "&"]
        for arg in command.argv:
            for pattern in dangerous_patterns:
                if pattern in arg:
                    raise SandboxPolicyError(
                        "Dangerous pattern '{}' found in argument '{}'".format(
                            pattern, arg
                        )
                    )

        # Check for banned flags (defense in depth for push/destructive safety)
        if self.banned_flags:
            for arg in command.argv:
                if arg in self.banned_flags:
                    raise SandboxPolicyError(
                        "Banned flag '{}' found in command. "
                        "Banned flags: {}".format(arg, self.banned_flags)
                    )

        # Check if argv matches any allowed prefix
        if self.allowed_argv_prefixes:
            matches_prefix = False
            for allowed_prefix in self.allowed_argv_prefixes:
                if self._argv_matches_prefix(command.argv, allowed_prefix):
                    matches_prefix = True
                    break

            if not matches_prefix:
                raise SandboxPolicyError(
                    "Command '{}' does not match any allowed prefix. Allowed prefixes: {}".format(
                        " ".join(command.argv), self.allowed_argv_prefixes
                    )
                )

        # Check for path traversal in cwd
        if ".." in command.cwd:
            raise SandboxPolicyError(
                "Path traversal (..) not allowed in cwd: '{}'".format(command.cwd)
            )

        # Validate environment variables
        if command.env:
            for key in command.env.keys():
                if key not in self.allowed_env_keys:
                    raise SandboxPolicyError(
                        "Environment variable '{}' is not in allowlist. Allowed: {}".format(
                            key, sorted(self.allowed_env_keys)
                        )
                    )

    def _argv_matches_prefix(
        self, argv: List[str], prefix: List[str]
    ) -> bool:
        """Check if argv starts with the given prefix.

        Args:
            argv: Command argument list.
            prefix: Required prefix.

        Returns:
            True if argv starts with prefix.
        """
        if len(argv) < len(prefix):
            return False
        return argv[: len(prefix)] == prefix
