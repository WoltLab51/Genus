"""
Configuration management for GENUS.
"""
import os
from typing import Optional


class Config:
    """
    Application configuration.
    API_KEY environment variable is required at startup.
    """

    def __init__(self):
        """Initialize and validate configuration."""
        self.api_key = os.getenv("API_KEY")
        if not self.api_key:
            raise ValueError("API_KEY environment variable is required")

        self.database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./genus.db")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

    @property
    def database_path(self) -> Optional[str]:
        """Extract database file path from URL."""
        if self.database_url.startswith("sqlite"):
            return self.database_url.split("///")[-1]
        return None
