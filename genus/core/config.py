"""Configuration Management - Environment-based config with validation."""

import os
from typing import Optional


class Config:
    """
    Centralized configuration for GENUS system.

    Loads settings from environment variables with validation.
    Raises ValueError if required settings are missing.
    """

    def __init__(self):
        """Initialize configuration from environment."""
        # API Configuration
        self.api_key = os.getenv("API_KEY")
        if not self.api_key:
            raise ValueError("API_KEY environment variable is required")

        self.api_host = os.getenv("API_HOST", "0.0.0.0")
        self.api_port = int(os.getenv("API_PORT", "8000"))

        # Database Configuration
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://genus:genus@localhost:5432/genus"
        )

        # System Configuration
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # Message Bus Configuration
        self.message_bus_max_queue_size = int(
            os.getenv("MESSAGE_BUS_MAX_QUEUE_SIZE", "1000")
        )
        self.message_bus_max_history = int(
            os.getenv("MESSAGE_BUS_MAX_HISTORY", "1000")
        )

    def __repr__(self) -> str:
        return (
            f"Config(api_host={self.api_host}, api_port={self.api_port}, "
            f"debug={self.debug}, log_level={self.log_level})"
        )
