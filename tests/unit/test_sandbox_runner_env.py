"""Tests that SandboxRunner._filter_env never leaks credentials."""
import os
import pytest
from unittest.mock import patch
from genus.sandbox.runner import SandboxRunner, _SAFE_ENV_KEYS, _BLOCKED_ENV_KEYS
from genus.sandbox.policy import SandboxPolicy


def make_runner():
    """Create a SandboxRunner stub for testing _filter_env only."""
    runner = object.__new__(SandboxRunner)
    runner.policy = SandboxPolicy()
    return runner


def test_filter_env_none_never_returns_none():
    """_filter_env(None) must never return None (never inherit full parent env)."""
    runner = make_runner()
    result = runner._filter_env(None)
    assert result is not None


def test_filter_env_none_excludes_github_token():
    """GITHUB_TOKEN must not appear in filtered env."""
    runner = make_runner()
    with patch.dict(os.environ, {"GITHUB_TOKEN": "secret-token", "PATH": "/usr/bin"}):
        result = runner._filter_env(None)
    assert "GITHUB_TOKEN" not in result


def test_filter_env_none_excludes_anthropic_key():
    runner = make_runner()
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-secret", "PATH": "/usr/bin"}):
        result = runner._filter_env(None)
    assert "ANTHROPIC_API_KEY" not in result


def test_filter_env_none_excludes_aws_keys():
    runner = make_runner()
    with patch.dict(os.environ, {
        "AWS_ACCESS_KEY_ID": "AKID",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "PATH": "/usr/bin"
    }):
        result = runner._filter_env(None)
    assert "AWS_ACCESS_KEY_ID" not in result
    assert "AWS_SECRET_ACCESS_KEY" not in result


def test_filter_env_none_includes_path():
    """PATH must always be present in the safe env."""
    runner = make_runner()
    with patch.dict(os.environ, {"PATH": "/usr/local/bin:/usr/bin"}):
        result = runner._filter_env(None)
    assert "PATH" in result


def test_filter_env_none_includes_home():
    runner = make_runner()
    with patch.dict(os.environ, {"HOME": "/home/user", "PATH": "/usr/bin"}):
        result = runner._filter_env(None)
    assert "HOME" in result


def test_blocked_keys_not_in_safe_keys():
    """_BLOCKED_ENV_KEYS and _SAFE_ENV_KEYS must not overlap."""
    overlap = _SAFE_ENV_KEYS & _BLOCKED_ENV_KEYS
    assert overlap == frozenset(), "Keys in both sets: {}".format(overlap)
