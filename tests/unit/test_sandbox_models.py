"""
Tests for Sandbox Models

Tests SandboxCommand, SandboxResult, and error classes.
"""

import pytest

from genus.sandbox.models import (
    SandboxCommand,
    SandboxResult,
    SandboxError,
    SandboxPolicyError,
)


class TestSandboxCommand:
    """Tests for SandboxCommand dataclass."""

    def test_create_command(self):
        """Should create a valid SandboxCommand."""
        cmd = SandboxCommand(
            argv=["python", "-m", "pytest"],
            cwd=".",
        )
        assert cmd.argv == ["python", "-m", "pytest"]
        assert cmd.cwd == "."
        assert cmd.env is None

    def test_create_command_with_env(self):
        """Should create command with environment variables."""
        cmd = SandboxCommand(
            argv=["python", "script.py"],
            cwd="src",
            env={"KEY": "value"},
        )
        assert cmd.env == {"KEY": "value"}

    def test_argv_is_list(self):
        """argv should be a list, not a string."""
        cmd = SandboxCommand(
            argv=["ls", "-la"],
            cwd=".",
        )
        assert isinstance(cmd.argv, list)
        assert len(cmd.argv) == 2


class TestSandboxResult:
    """Tests for SandboxResult dataclass."""

    def test_create_result(self):
        """Should create a valid SandboxResult."""
        result = SandboxResult(
            exit_code=0,
            stdout="output",
            stderr="",
            duration_s=1.5,
            timed_out=False,
        )
        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.duration_s == 1.5
        assert result.timed_out is False

    def test_result_with_timeout(self):
        """Should represent a timed-out execution."""
        result = SandboxResult(
            exit_code=124,
            stdout="partial",
            stderr="",
            duration_s=60.0,
            timed_out=True,
        )
        assert result.timed_out is True
        assert result.exit_code == 124

    def test_result_with_error(self):
        """Should represent a failed execution."""
        result = SandboxResult(
            exit_code=1,
            stdout="",
            stderr="error message",
            duration_s=0.5,
            timed_out=False,
        )
        assert result.exit_code == 1
        assert "error message" in result.stderr


class TestSandboxErrors:
    """Tests for sandbox error classes."""

    def test_sandbox_error_is_runtime_error(self):
        """SandboxError should inherit from RuntimeError."""
        err = SandboxError("test error")
        assert isinstance(err, RuntimeError)
        assert str(err) == "test error"

    def test_sandbox_policy_error_is_value_error(self):
        """SandboxPolicyError should inherit from ValueError."""
        err = SandboxPolicyError("policy violation")
        assert isinstance(err, ValueError)
        assert str(err) == "policy violation"

    def test_sandbox_error_can_be_raised(self):
        """Should be able to raise SandboxError."""
        with pytest.raises(SandboxError) as exc_info:
            raise SandboxError("test")
        assert "test" in str(exc_info.value)

    def test_sandbox_policy_error_can_be_raised(self):
        """Should be able to raise SandboxPolicyError."""
        with pytest.raises(SandboxPolicyError) as exc_info:
            raise SandboxPolicyError("not allowed")
        assert "not allowed" in str(exc_info.value)
