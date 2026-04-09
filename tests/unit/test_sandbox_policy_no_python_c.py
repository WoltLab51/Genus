"""Tests that python -c is blocked by the default SandboxPolicy."""
import pytest
from genus.sandbox.policy import SandboxPolicy
from genus.sandbox.models import SandboxCommand, SandboxPolicyError


def make_cmd(argv):
    return SandboxCommand(argv=argv, cwd=".")


def test_python_c_is_blocked_by_default():
    """python -c must be rejected by the default policy."""
    policy = SandboxPolicy()
    cmd = make_cmd(["python", "-c", "print('hello')"])
    with pytest.raises(SandboxPolicyError):
        policy.validate(cmd)


def test_python_c_with_dangerous_code_is_blocked():
    """python -c with os.system must be rejected."""
    policy = SandboxPolicy()
    cmd = make_cmd(["python", "-c", "import os; os.system('id')"])
    with pytest.raises(SandboxPolicyError):
        policy.validate(cmd)


def test_python_m_pytest_still_allowed():
    """python -m pytest must still be allowed by default policy."""
    policy = SandboxPolicy()
    cmd = make_cmd(["python", "-m", "pytest", "tests/"])
    policy.validate(cmd)  # must not raise


def test_python_m_ruff_still_allowed():
    """python -m ruff must still be allowed."""
    policy = SandboxPolicy()
    cmd = make_cmd(["python", "-m", "ruff", "check", "."])
    policy.validate(cmd)  # must not raise


def test_python_version_still_allowed():
    """python --version must still be allowed."""
    policy = SandboxPolicy()
    cmd = make_cmd(["python", "--version"])
    policy.validate(cmd)  # must not raise


def test_custom_policy_can_allow_python_c():
    """A custom policy can explicitly allow python -c if needed."""
    policy = SandboxPolicy(
        allowed_argv_prefixes=[["python", "-c"]]
    )
    cmd = make_cmd(["python", "-c", "print('ok')"])
    policy.validate(cmd)  # must not raise with custom policy
