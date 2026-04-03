import json
from datetime import datetime
from typing import Any, Optional
from collections import defaultdict


class MemoryStore:
    """In-memory key-value store with namespacing for GENUS agents."""

    def __init__(self):
        self._store: dict[str, dict[str, Any]] = defaultdict(dict)
        self._history: list[dict] = []

    def set(self, namespace: str, key: str, value: Any) -> None:
        self._store[namespace][key] = value
        self._history.append({
            "action": "set",
            "namespace": namespace,
            "key": key,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        return self._store[namespace].get(key, default)

    def get_all(self, namespace: str) -> dict[str, Any]:
        return dict(self._store.get(namespace, {}))

    def delete(self, namespace: str, key: str) -> bool:
        if key in self._store[namespace]:
            del self._store[namespace][key]
            return True
        return False

    def clear_namespace(self, namespace: str) -> None:
        self._store[namespace].clear()

    def history(self, limit: int = 50) -> list[dict]:
        return self._history[-limit:]


# Global singleton memory store
memory_store = MemoryStore()
