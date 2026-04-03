"""Configuration management for GENUS."""

import os
from typing import Optional


class Config:
    """Application configuration with validation."""

    def __init__(self):
        """Initialize configuration from environment variables.

        Raises:
            ValueError: If required configuration is missing
        """
        self.api_key = os.getenv("API_KEY")
        if not self.api_key:
            raise ValueError("API_KEY environment variable is required")

        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///genus.db")

    def __repr__(self) -> str:
        """String representation of config (without secrets)."""
        return f"Config(debug={self.debug}, host={self.host}, port={self.port})"
