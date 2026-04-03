"""Configuration management."""

import os
from typing import Optional


class Config:
    """Application configuration."""

    def __init__(self):
        """Initialize configuration from environment variables."""
        self.api_key: str = os.getenv("API_KEY", "")
        if not self.api_key:
            raise ValueError("API_KEY environment variable is required")

        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.debug: bool = os.getenv("DEBUG", "false").lower() == "true"
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./genus.db")

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls()
