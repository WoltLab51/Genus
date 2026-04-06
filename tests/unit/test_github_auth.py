"""
Tests for GitHub Authentication

Tests the get_github_token_from_env function with various scenarios.
"""

import os
import pytest
from genus.github.auth import get_github_token_from_env


def test_get_github_token_success(monkeypatch):
    """Test successful token retrieval from environment."""
    # Set token in environment
    test_token = "ghp_test_token_12345"
    monkeypatch.setenv("GITHUB_TOKEN", test_token)

    # Retrieve token
    token = get_github_token_from_env()

    # Verify
    assert token == test_token


def test_get_github_token_custom_env_key(monkeypatch):
    """Test token retrieval with custom environment variable name."""
    # Set token in custom env var
    test_token = "ghp_custom_token_67890"
    monkeypatch.setenv("MY_CUSTOM_TOKEN", test_token)

    # Retrieve token with custom key
    token = get_github_token_from_env(env_key="MY_CUSTOM_TOKEN")

    # Verify
    assert token == test_token


def test_get_github_token_missing_env(monkeypatch):
    """Test error when environment variable is not set."""
    # Ensure token is not set
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    # Should raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        get_github_token_from_env()

    # Verify error message
    assert "GitHub token not found" in str(exc_info.value)
    assert "GITHUB_TOKEN" in str(exc_info.value)


def test_get_github_token_empty_string(monkeypatch):
    """Test error when environment variable is empty string."""
    # Set empty token
    monkeypatch.setenv("GITHUB_TOKEN", "")

    # Should raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        get_github_token_from_env()

    # Verify error message
    assert "GitHub token not found" in str(exc_info.value)


def test_get_github_token_whitespace_only(monkeypatch):
    """Test error when environment variable contains only whitespace."""
    # Set whitespace-only token
    monkeypatch.setenv("GITHUB_TOKEN", "   \t\n  ")

    # Should raise RuntimeError (strip() makes it empty)
    with pytest.raises(RuntimeError) as exc_info:
        get_github_token_from_env()

    # Verify error message
    assert "GitHub token not found" in str(exc_info.value)


def test_get_github_token_with_whitespace(monkeypatch):
    """Test that token is stripped of leading/trailing whitespace."""
    # Set token with whitespace
    test_token = "  ghp_token_with_spaces  "
    monkeypatch.setenv("GITHUB_TOKEN", test_token)

    # Retrieve token
    token = get_github_token_from_env()

    # Verify token is stripped
    assert token == "ghp_token_with_spaces"
    assert token == test_token.strip()
