"""
Tests for Sandbox Runner

Tests sandbox execution with security invariants:
- Kill-switch enforcement
- Policy validation
- Timeout handling
- Output capture and truncation
- Working directory restriction
"""

import pytest
import asyncio
import tempfile
from pathlib import Path

from genus.workspace.workspace import RunWorkspace
from genus.sandbox.models import SandboxCommand, SandboxPolicyError
from genus.sandbox.policy import SandboxPolicy
from genus.sandbox.runner import SandboxRunner
from genus.security.kill_switch import KillSwitch


class TestSandboxRunnerKillSwitch:
    """Tests for kill-switch enforcement."""

    @pytest.mark.asyncio
    async def test_kill_switch_disabled_blocks_execution(self):
        """Disabled kill-switch should block execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-001", root=Path(tmpdir))
            workspace.ensure_dirs()

            kill_switch = KillSwitch()
            kill_switch.disable()

            policy = SandboxPolicy()
            runner = SandboxRunner(
                workspace=workspace,
                policy=policy,
                kill_switch=kill_switch,
            )

            cmd = SandboxCommand(argv=["python", "-m", "pytest"], cwd=".")

            with pytest.raises(RuntimeError) as exc_info:
                await runner.run(cmd)
            assert "Sandbox execution disabled" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_kill_switch_enabled_allows_execution(self):
        """Enabled kill-switch should allow execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-002", root=Path(tmpdir))
            workspace.ensure_dirs()

            kill_switch = KillSwitch()
            kill_switch.enable()

            policy = SandboxPolicy()
            runner = SandboxRunner(
                workspace=workspace,
                policy=policy,
                kill_switch=kill_switch,
            )

            cmd = SandboxCommand(argv=["python", "--version"], cwd=".")

            # Should not raise
            result = await runner.run(cmd, timeout_s=5)
            assert result is not None


class TestSandboxRunnerPolicyEnforcement:
    """Tests for policy enforcement."""

    @pytest.mark.asyncio
    async def test_policy_violation_blocks_execution(self):
        """Policy violations should prevent execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-003", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy()
            runner = SandboxRunner(workspace=workspace, policy=policy)

            # Command not in allowlist
            cmd = SandboxCommand(argv=["bash", "-c", "echo hi"], cwd=".")

            with pytest.raises(SandboxPolicyError):
                await runner.run(cmd)

    @pytest.mark.asyncio
    async def test_allowed_command_executes(self):
        """Allowed commands should execute successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-004", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy()
            runner = SandboxRunner(workspace=workspace, policy=policy)

            cmd = SandboxCommand(argv=["python", "--version"], cwd=".")

            result = await runner.run(cmd, timeout_s=5)
            assert result.exit_code == 0
            assert "Python" in result.stdout or "Python" in result.stderr


class TestSandboxRunnerExecution:
    """Tests for basic execution."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Should execute command and return result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-005", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy()
            runner = SandboxRunner(workspace=workspace, policy=policy)

            cmd = SandboxCommand(argv=["python", "-c", "print('hello')"], cwd=".")

            result = await runner.run(cmd, timeout_s=5)
            assert result.exit_code == 0
            assert "hello" in result.stdout
            assert result.timed_out is False
            assert result.duration_s > 0

    @pytest.mark.asyncio
    async def test_failed_execution(self):
        """Should capture failed execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-006", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy()
            runner = SandboxRunner(workspace=workspace, policy=policy)

            cmd = SandboxCommand(
                argv=["python", "-c", "import sys; sys.exit(42)"],
                cwd=".",
            )

            result = await runner.run(cmd, timeout_s=5)
            assert result.exit_code == 42
            assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_stderr_capture(self):
        """Should capture stderr output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-007", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy()
            runner = SandboxRunner(workspace=workspace, policy=policy)

            cmd = SandboxCommand(
                argv=["python", "-c", "import sys; sys.stderr.write('error\\n')"],
                cwd=".",
            )

            result = await runner.run(cmd, timeout_s=5)
            assert "error" in result.stderr


class TestSandboxRunnerTimeout:
    """Tests for timeout handling."""

    @pytest.mark.asyncio
    async def test_timeout_terminates_process(self):
        """Should terminate process on timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-008", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy()
            runner = SandboxRunner(workspace=workspace, policy=policy)

            # Command that sleeps longer than timeout
            cmd = SandboxCommand(
                argv=["python", "-c", "import time; time.sleep(10)"],
                cwd=".",
            )

            result = await runner.run(cmd, timeout_s=0.5)
            assert result.timed_out is True
            assert result.exit_code == 124  # Standard timeout exit code

    @pytest.mark.asyncio
    async def test_default_timeout_used(self):
        """Should use policy default timeout when none specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-009", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy(default_timeout_s=1.0)
            runner = SandboxRunner(workspace=workspace, policy=policy)

            cmd = SandboxCommand(
                argv=["python", "-c", "import time; time.sleep(5)"],
                cwd=".",
            )

            result = await runner.run(cmd)
            assert result.timed_out is True

    @pytest.mark.asyncio
    async def test_max_timeout_enforced(self):
        """Should enforce max timeout limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-010", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy(max_timeout_s=2.0)
            runner = SandboxRunner(workspace=workspace, policy=policy)

            cmd = SandboxCommand(
                argv=["python", "-c", "import time; time.sleep(5)"],
                cwd=".",
            )

            # Request 10s timeout, but max is 2s
            result = await runner.run(cmd, timeout_s=10.0)
            # Should timeout around 2s, not 10s
            assert result.timed_out is True
            assert result.duration_s < 3.0


class TestSandboxRunnerOutputTruncation:
    """Tests for output truncation."""

    @pytest.mark.asyncio
    async def test_stdout_truncation(self):
        """Should truncate stdout when exceeding limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-011", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy(max_stdout_bytes=100)
            runner = SandboxRunner(workspace=workspace, policy=policy)

            # Generate output larger than limit
            cmd = SandboxCommand(
                argv=["python", "-c", "print('A' * 1000)"],
                cwd=".",
            )

            result = await runner.run(cmd, timeout_s=5)
            assert "TRUNCATED" in result.stdout
            assert len(result.stdout) < 1000

    @pytest.mark.asyncio
    async def test_stderr_truncation(self):
        """Should truncate stderr when exceeding limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-012", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy(max_stderr_bytes=100)
            runner = SandboxRunner(workspace=workspace, policy=policy)

            cmd = SandboxCommand(
                argv=[
                    "python",
                    "-c",
                    "import sys; sys.stderr.write('B' * 1000)",
                ],
                cwd=".",
            )

            result = await runner.run(cmd, timeout_s=5)
            assert "TRUNCATED" in result.stderr


class TestSandboxRunnerWorkingDirectory:
    """Tests for working directory restriction."""

    @pytest.mark.asyncio
    async def test_cwd_within_workspace(self):
        """Should execute in correct working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-013", root=Path(tmpdir))
            workspace.ensure_dirs()

            # Create a subdirectory
            subdir = workspace.repo_dir / "subdir"
            subdir.mkdir()

            policy = SandboxPolicy()
            runner = SandboxRunner(workspace=workspace, policy=policy)

            cmd = SandboxCommand(
                argv=["python", "-c", "import os; print(os.getcwd())"],
                cwd="subdir",
            )

            result = await runner.run(cmd, timeout_s=5)
            assert result.exit_code == 0
            assert "subdir" in result.stdout

    @pytest.mark.asyncio
    async def test_path_traversal_blocked_by_policy(self):
        """Path traversal should be blocked by policy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-014", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy()
            runner = SandboxRunner(workspace=workspace, policy=policy)

            cmd = SandboxCommand(
                argv=["python", "--version"],
                cwd="../../../etc",  # Attempt path traversal
            )

            with pytest.raises(SandboxPolicyError):
                await runner.run(cmd)


class TestSandboxRunnerSecurityInvariants:
    """Tests for security invariants."""

    @pytest.mark.asyncio
    async def test_no_shell_execution(self):
        """Should not execute shell commands - uses subprocess.exec, not shell."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-015", root=Path(tmpdir))
            workspace.ensure_dirs()

            policy = SandboxPolicy()
            runner = SandboxRunner(workspace=workspace, policy=policy)

            # Python -c executes Python code, not shell
            # This will try to parse as Python and fail
            cmd = SandboxCommand(
                argv=["python", "-c", "print('hello')"],
                cwd=".",
            )

            result = await runner.run(cmd, timeout_s=5)
            # Should execute as Python code successfully
            assert "hello" in result.stdout
            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_env_filtering(self):
        """Should filter environment variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = RunWorkspace(run_id="test-016", root=Path(tmpdir))
            workspace.ensure_dirs()

            # Policy allows no env vars
            policy = SandboxPolicy()
            runner = SandboxRunner(workspace=workspace, policy=policy)

            cmd = SandboxCommand(
                argv=["python", "-c", "import os; print(os.environ.get('MALICIOUS', 'NOTSET'))"],
                cwd=".",
                env={"MALICIOUS": "value"},
            )

            # Should be blocked by policy validation
            with pytest.raises(SandboxPolicyError):
                await runner.run(cmd)
