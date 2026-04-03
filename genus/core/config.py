"""Configuration management for GENUS."""
import os
from typing import Optional


class Config:
    """Application configuration with environment variable support."""

    def __init__(self):
        """Initialize configuration from environment variables."""
        self.api_key: str = self._get_required_env("API_KEY")
        self.environment: str = os.getenv("ENVIRONMENT", "production")
        self.debug: bool = os.getenv("DEBUG", "false").lower() == "true"
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))

    @staticmethod
    def _get_required_env(key: str) -> str:
        """Get required environment variable or raise error.

        Args:
            key: Environment variable name

        Returns:
            Environment variable value

        Raises:
            ValueError: If environment variable is not set
        """
        value = os.getenv(key)
        if value is None:
            raise ValueError(
                f"Required environment variable '{key}' is not set. "
                f"Please set {key} before starting the application."
            )
        return value

    def validate_api_key(self, provided_key: Optional[str]) -> bool:
        """Validate provided API key against configured key.

        Args:
            provided_key: API key to validate

        Returns:
            True if valid, False otherwise
        """
        if provided_key is None:
            return False
        return provided_key == self.api_key
