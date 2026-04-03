"""In-memory storage for agent data."""

from typing import Any, Dict, List, Optional
from datetime import datetime


class MemoryStore:
    """Simple in-memory key-value store for agent data."""

    def __init__(self):
        """Initialize the memory store."""
        self._data: Dict[str, Any] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    async def store(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Store a value with optional metadata.

        Args:
            key: Storage key
            value: Value to store
            metadata: Optional metadata (e.g., timestamp, source)
        """
        self._data[key] = value
        self._metadata[key] = metadata or {"timestamp": datetime.utcnow()}

    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve a value by key.

        Args:
            key: Storage key

        Returns:
            Stored value or None if not found
        """
        return self._data.get(key)

    async def delete(self, key: str) -> bool:
        """Delete a value by key.

        Args:
            key: Storage key

        Returns:
            True if deleted, False if not found
        """
        if key in self._data:
            del self._data[key]
            del self._metadata[key]
            return True
        return False

    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """List all keys, optionally filtered by prefix.

        Args:
            prefix: Optional key prefix filter

        Returns:
            List of matching keys
        """
        if prefix:
            return [k for k in self._data.keys() if k.startswith(prefix)]
        return list(self._data.keys())

    def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a key.

        Args:
            key: Storage key

        Returns:
            Metadata dict or None if not found
        """
        return self._metadata.get(key)
