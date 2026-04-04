"""
Configuration Management

Provides centralized configuration management for the GENUS system.
Supports environment variables, file-based config, and defaults.
"""

from typing import Any, Dict, Optional
import os
import json
from pathlib import Path


class Config:
    """
    Configuration manager for GENUS.

    Follows the Single Responsibility Principle by handling only configuration.
    Supports layered configuration: defaults -> file -> environment variables.
    """

    _instance: Optional['Config'] = None
    _initialized: bool = False

    def __new__(cls):
        """Implement singleton pattern for configuration."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize configuration with defaults."""
        if not self._initialized:
            self._config: Dict[str, Any] = self._get_default_config()
            self._initialized = True

    def _get_default_config(self) -> Dict[str, Any]:
        """
        Get default configuration values.

        Returns:
            Dictionary of default configuration values
        """
        return {
            "system": {
                "name": "GENUS",
                "version": "0.1.0",
                "environment": os.getenv("GENUS_ENV", "development"),
            },
            "message_bus": {
                "max_queue_size": int(os.getenv("GENUS_MAX_QUEUE_SIZE", "1000")),
                "max_history": int(os.getenv("GENUS_MAX_HISTORY", "1000")),
            },
            "logging": {
                "level": os.getenv("GENUS_LOG_LEVEL", "INFO"),
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "file": os.getenv("GENUS_LOG_FILE", None),
            },
            "agents": {
                "startup_timeout": int(os.getenv("GENUS_AGENT_STARTUP_TIMEOUT", "30")),
                "shutdown_timeout": int(os.getenv("GENUS_AGENT_SHUTDOWN_TIMEOUT", "30")),
            },
        }

    def load_from_file(self, filepath: str) -> None:
        """
        Load configuration from a JSON file.

        Args:
            filepath: Path to the configuration file
        """
        path = Path(filepath)
        if path.exists():
            with open(path, 'r') as f:
                file_config = json.load(f)
                self._merge_config(file_config)

    def _merge_config(self, new_config: Dict[str, Any]) -> None:
        """
        Merge new configuration into existing config.

        Args:
            new_config: New configuration dictionary to merge
        """
        def deep_merge(base: Dict, override: Dict) -> Dict:
            """Recursively merge two dictionaries."""
            result = base.copy()
            for key, value in override.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result

        self._config = deep_merge(self._config, new_config)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            key: Configuration key (e.g., 'system.name' or 'logging.level')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value using dot notation.

        Args:
            key: Configuration key (e.g., 'system.name')
            value: Value to set
        """
        keys = key.split('.')
        config = self._config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def get_all(self) -> Dict[str, Any]:
        """
        Get all configuration values.

        Returns:
            Dictionary of all configuration values
        """
        return self._config.copy()

    def reset(self) -> None:
        """Reset configuration to defaults."""
        self._config = self._get_default_config()

    def __repr__(self) -> str:
        return f"Config(environment={self.get('system.environment')})"
