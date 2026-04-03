"""Memory Store - Namespaced key-value store for agent data."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from collections import defaultdict


class MemoryStore:
    """
    In-memory key-value store with namespacing.

    Provides:
    - Namespaced storage (each agent can have its own namespace)
    - Operation history for observability
    - Simple get/set/delete operations

    No global singleton - instances created and injected.
    """

    def __init__(self):
        """Initialize the memory store."""
        self._store: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._history: List[Dict[str, Any]] = []
        self._max_history = 1000

    def set(self, namespace: str, key: str, value: Any) -> None:
        """
        Set a value in a namespace.

        Args:
            namespace: The namespace (e.g., agent ID)
            key: The key within the namespace
            value: The value to store
        """
        self._store[namespace][key] = value
        self._history.append({
            "action": "set",
            "namespace": namespace,
            "key": key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """
        Get a value from a namespace.

        Args:
            namespace: The namespace
            key: The key within the namespace
            default: Default value if key doesn't exist

        Returns:
            The value or default
        """
        return self._store[namespace].get(key, default)

    def get_all(self, namespace: str) -> Dict[str, Any]:
        """
        Get all key-value pairs in a namespace.

        Args:
            namespace: The namespace

        Returns:
            Dictionary of all keys and values in the namespace
        """
        return dict(self._store.get(namespace, {}))

    def delete(self, namespace: str, key: str) -> bool:
        """
        Delete a key from a namespace.

        Args:
            namespace: The namespace
            key: The key to delete

        Returns:
            True if key existed and was deleted, False otherwise
        """
        if key in self._store[namespace]:
            del self._store[namespace][key]
            self._history.append({
                "action": "delete",
                "namespace": namespace,
                "key": key,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if len(self._history) > self._max_history:
                self._history.pop(0)
            return True
        return False

    def clear_namespace(self, namespace: str) -> None:
        """
        Clear all data in a namespace.

        Args:
            namespace: The namespace to clear
        """
        self._store[namespace].clear()
        self._history.append({
            "action": "clear_namespace",
            "namespace": namespace,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get operation history.

        Args:
            limit: Maximum number of history entries to return

        Returns:
            List of history entries
        """
        return self._history[-limit:]

    def get_namespaces(self) -> List[str]:
        """
        Get all namespaces.

        Returns:
            List of namespace names
        """
        return list(self._store.keys())
