"""
Tests for Sandbox Policy

Tests the deny-by-default security policy enforcement.
"""

import pytest

from genus.sandbox.models import SandboxCommand, SandboxPolicyError
from genus.sandbox.policy import SandboxPolicy


class TestSandboxPolicyDefaults:
    """Tests for default policy configuration."""

    def test_default_allowed_executables(self):
        """Default policy should allow python/pytest."""
        policy = SandboxPolicy()
        assert "python" in policy.allowed_executables
        assert "python.exe" in policy.allowed_executables
        assert "pytest" in policy.allowed_executables

    def test_default_allowed_prefixes(self):
        """Default policy should allow python -m pytest."""
        policy = SandboxPolicy()
        assert ["python", "-m", "pytest"] in policy.allowed_argv_prefixes
        assert ["python", "-m", "ruff"] in policy.allowed_argv_prefixes

    def test_default_env_keys_empty(self):
        """Default policy should not allow any env vars."""
        policy = SandboxPolicy()
        assert len(policy.allowed_env_keys) == 0

    def test_default_output_limits(self):
        """Default policy should have reasonable output limits."""
        policy = SandboxPolicy()
        assert policy.max_stdout_bytes == 1024 * 1024  # 1 MB
        assert policy.max_stderr_bytes == 1024 * 1024  # 1 MB

    def test_default_timeouts(self):
        """Default policy should have reasonable timeouts."""
        policy = SandboxPolicy()
        assert policy.default_timeout_s == 300.0  # 5 minutes
        assert policy.max_timeout_s == 600.0  # 10 minutes


class TestSandboxPolicyValidation:
    """Tests for policy validation."""

    def test_empty_argv_rejected(self):
        """Empty argv should be rejected."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(argv=[], cwd=".")
        with pytest.raises(SandboxPolicyError) as exc_info:
            policy.validate(cmd)
        assert "cannot be empty" in str(exc_info.value)

    def test_disallowed_executable_rejected(self):
        """Executables not in allowlist should be rejected."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(argv=["bash", "-c", "echo hi"], cwd=".")
        with pytest.raises(SandboxPolicyError) as exc_info:
            policy.validate(cmd)
        assert "not in allowlist" in str(exc_info.value)
        assert "bash" in str(exc_info.value)

    def test_allowed_executable_accepted(self):
        """Allowed executables should pass validation."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(argv=["python", "-m", "pytest"], cwd=".")
        # Should not raise
        policy.validate(cmd)

    def test_shell_metacharacters_rejected(self):
        """Shell metacharacters should be rejected."""
        policy = SandboxPolicy()
        dangerous_patterns = ["&&", "||", "|", "&"]

        for pattern in dangerous_patterns:
            cmd = SandboxCommand(
                argv=["python", "-c", "test{}file".format(pattern)],
                cwd=".",
            )
            with pytest.raises(SandboxPolicyError) as exc_info:
                policy.validate(cmd)
            assert "Dangerous pattern" in str(exc_info.value)

    def test_path_traversal_in_cwd_rejected(self):
        """Path traversal (..) in cwd should be rejected."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(argv=["python", "-m", "pytest"], cwd="../etc")
        with pytest.raises(SandboxPolicyError) as exc_info:
            policy.validate(cmd)
        assert "traversal" in str(exc_info.value).lower()

    def test_allowed_prefix_matching(self):
        """Commands matching allowed prefixes should pass."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(
            argv=["python", "-m", "pytest", "tests/", "-v"],
            cwd=".",
        )
        # Should not raise
        policy.validate(cmd)

    def test_disallowed_prefix_rejected(self):
        """Commands not matching any allowed prefix should be rejected."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(
            argv=["python", "script.py"],  # Not in allowed prefixes
            cwd=".",
        )
        with pytest.raises(SandboxPolicyError) as exc_info:
            policy.validate(cmd)
        assert "does not match any allowed prefix" in str(exc_info.value)

    def test_env_vars_not_in_allowlist_rejected(self):
        """Environment variables not in allowlist should be rejected."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(
            argv=["python", "-m", "pytest"],
            cwd=".",
            env={"MALICIOUS": "value"},
        )
        with pytest.raises(SandboxPolicyError) as exc_info:
            policy.validate(cmd)
        assert "not in allowlist" in str(exc_info.value)
        assert "MALICIOUS" in str(exc_info.value)

    def test_allowed_env_vars_accepted(self):
        """Environment variables in allowlist should be accepted."""
        policy = SandboxPolicy(allowed_env_keys={"PYTEST_ARGS"})
        cmd = SandboxCommand(
            argv=["python", "-m", "pytest"],
            cwd=".",
            env={"PYTEST_ARGS": "-v"},
        )
        # Should not raise
        policy.validate(cmd)


class TestSandboxPolicyCustomConfiguration:
    """Tests for custom policy configuration."""

    def test_custom_allowed_executables(self):
        """Should accept custom allowed executables."""
        policy = SandboxPolicy(allowed_executables={"myapp"})
        assert "myapp" in policy.allowed_executables
        assert "python" not in policy.allowed_executables

    def test_custom_allowed_prefixes(self):
        """Should accept custom allowed prefixes."""
        policy = SandboxPolicy(
            allowed_executables={"myapp"},
            allowed_argv_prefixes=[["myapp", "run"]],
        )
        cmd = SandboxCommand(argv=["myapp", "run", "test"], cwd=".")
        # Should not raise
        policy.validate(cmd)

    def test_custom_env_keys(self):
        """Should accept custom allowed env keys."""
        policy = SandboxPolicy(allowed_env_keys={"MY_VAR"})
        assert "MY_VAR" in policy.allowed_env_keys

    def test_custom_output_limits(self):
        """Should accept custom output limits."""
        policy = SandboxPolicy(
            max_stdout_bytes=1024,
            max_stderr_bytes=512,
        )
        assert policy.max_stdout_bytes == 1024
        assert policy.max_stderr_bytes == 512

    def test_custom_timeouts(self):
        """Should accept custom timeouts."""
        policy = SandboxPolicy(
            default_timeout_s=60.0,
            max_timeout_s=120.0,
        )
        assert policy.default_timeout_s == 60.0
        assert policy.max_timeout_s == 120.0


class TestSandboxPolicyPrefixMatching:
    """Tests for prefix matching logic."""

    def test_exact_prefix_match(self):
        """Should match exact prefix."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(argv=["python", "-m", "pytest"], cwd=".")
        # Should not raise
        policy.validate(cmd)

    def test_prefix_with_additional_args(self):
        """Should match prefix with additional arguments."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(
            argv=["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
            cwd=".",
        )
        # Should not raise
        policy.validate(cmd)

    def test_partial_prefix_not_matched(self):
        """Should not match partial prefix."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(argv=["python", "-m"], cwd=".")
        with pytest.raises(SandboxPolicyError):
            policy.validate(cmd)

    def test_wrong_order_not_matched(self):
        """Should not match wrong argument order."""
        policy = SandboxPolicy()
        cmd = SandboxCommand(argv=["python", "pytest", "-m"], cwd=".")
        with pytest.raises(SandboxPolicyError):
            policy.validate(cmd)
