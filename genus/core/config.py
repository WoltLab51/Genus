"""
Configuration

Centralised, layered configuration: defaults → environment variables.
"""

from typing import Any, Dict, Optional
import os


class Config:
    """Read-only configuration container.

    Values come from hard-coded defaults overridden by environment variables.
    The class is intentionally *not* a singleton — pass the instance explicitly.
    """

    def __init__(self) -> None:
        self._config: Dict[str, Any] = self._build()

    # ------------------------------------------------------------------

    @staticmethod
    def _build() -> Dict[str, Any]:
        return {
            "system": {
                "name": "GENUS",
                "version": "0.1.0",
                "environment": os.getenv("GENUS_ENV", "development"),
            },
            "database": {
                "url": os.getenv(
                    "DATABASE_URL",
                    "sqlite+aiosqlite:///./genus.db",
                ),
            },
            "logging": {
                "level": os.getenv("GENUS_LOG_LEVEL", "INFO"),
            },
            "message_bus": {
                "max_history": int(os.getenv("GENUS_MAX_HISTORY", "1000")),
            },
        }

    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-notation lookup, e.g. ``config.get("database.url")``."""
        parts = key.split(".")
        node: Any = self._config
        for p in parts:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                return default
        return node

    def get_all(self) -> Dict[str, Any]:
        return dict(self._config)
