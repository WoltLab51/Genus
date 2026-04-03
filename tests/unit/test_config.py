"""Unit tests for Config."""

import os
import pytest

from genus.core.config import Config


def test_config_requires_api_key(monkeypatch):
    """Test that Config requires API_KEY environment variable."""
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(ValueError, match="API_KEY environment variable is required"):
        Config()


def test_config_from_env(monkeypatch):
    """Test Config.from_env() creates config from environment."""
    monkeypatch.setenv("API_KEY", "test-key-123")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DEBUG", "true")

    config = Config.from_env()

    assert config.api_key == "test-key-123"
    assert config.log_level == "DEBUG"
    assert config.debug is True


def test_config_defaults(monkeypatch):
    """Test Config uses default values for optional settings."""
    monkeypatch.setenv("API_KEY", "test-key-123")

    config = Config()

    assert config.api_key == "test-key-123"
    assert config.log_level == "INFO"
    assert config.debug is False
    assert config.database_url == "sqlite:///./genus.db"
