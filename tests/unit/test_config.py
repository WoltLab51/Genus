"""Unit tests for configuration module."""
import pytest
import os
from genus.core.config import Config


def test_config_requires_api_key(monkeypatch):
    """Test that Config raises error when API_KEY is not set."""
    # Remove API_KEY if it exists
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(ValueError) as exc_info:
        Config()

    assert "API_KEY" in str(exc_info.value)
    assert "not set" in str(exc_info.value)


def test_config_loads_api_key(monkeypatch):
    """Test that Config loads API_KEY from environment."""
    monkeypatch.setenv("API_KEY", "test-secret-key-123")

    config = Config()

    assert config.api_key == "test-secret-key-123"


def test_config_defaults(monkeypatch):
    """Test that Config sets appropriate defaults."""
    monkeypatch.setenv("API_KEY", "test-key")

    config = Config()

    assert config.environment == "production"
    assert config.debug is False
    assert config.host == "0.0.0.0"
    assert config.port == 8000


def test_config_environment_variables(monkeypatch):
    """Test that Config respects all environment variables."""
    monkeypatch.setenv("API_KEY", "my-key")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "9000")

    config = Config()

    assert config.api_key == "my-key"
    assert config.environment == "development"
    assert config.debug is True
    assert config.host == "127.0.0.1"
    assert config.port == 9000


def test_validate_api_key_valid(monkeypatch):
    """Test API key validation with correct key."""
    monkeypatch.setenv("API_KEY", "correct-key")
    config = Config()

    assert config.validate_api_key("correct-key") is True


def test_validate_api_key_invalid(monkeypatch):
    """Test API key validation with incorrect key."""
    monkeypatch.setenv("API_KEY", "correct-key")
    config = Config()

    assert config.validate_api_key("wrong-key") is False


def test_validate_api_key_none(monkeypatch):
    """Test API key validation with None."""
    monkeypatch.setenv("API_KEY", "correct-key")
    config = Config()

    assert config.validate_api_key(None) is False
