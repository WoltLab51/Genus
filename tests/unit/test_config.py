"""Unit tests for Config."""

import pytest
import os
from genus.core.config import Config


class TestConfig:
    """Test configuration management."""

    def test_config_requires_api_key(self):
        """Test that config requires API_KEY."""
        # Clear API_KEY if set
        old_key = os.environ.pop("API_KEY", None)
        try:
            with pytest.raises(ValueError, match="API_KEY environment variable is required"):
                Config()
        finally:
            if old_key:
                os.environ["API_KEY"] = old_key

    def test_config_with_api_key(self):
        """Test config initialization with API_KEY."""
        os.environ["API_KEY"] = "test_key"
        config = Config()
        assert config.api_key == "test_key"
        assert config.debug is False
        assert config.host == "0.0.0.0"
        assert config.port == 8000

    def test_config_debug_mode(self):
        """Test debug mode configuration."""
        os.environ["API_KEY"] = "test_key"
        os.environ["DEBUG"] = "true"
        config = Config()
        assert config.debug is True
        os.environ["DEBUG"] = "false"

    def test_config_custom_port(self):
        """Test custom port configuration."""
        os.environ["API_KEY"] = "test_key"
        os.environ["PORT"] = "9000"
        config = Config()
        assert config.port == 9000
        os.environ["PORT"] = "8000"
