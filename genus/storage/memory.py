"""
In-memory key-value store with namespacing.

``MemoryStore`` gives agents a fast, ephemeral scratch-pad for sharing
small data between pipeline steps (e.g. "last analysis result").
It is intentionally **not** a database — use ``DecisionStore`` /
``FeedbackStore`` for persistent data.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List


class MemoryStore:
    """Namespaced in-memory key-value store."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._history: List[Dict[str, Any]] = []
        self._max_history = 500

    def set(self, namespace: str, key: str, value: Any) -> None:
        self._store[namespace][key] = value
        self._history.append({
            "action": "set",
            "namespace": namespace,
            "key": key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        return self._store[namespace].get(key, default)

    def get_all(self, namespace: str) -> Dict[str, Any]:
        return dict(self._store.get(namespace, {}))

    def delete(self, namespace: str, key: str) -> bool:
        if key in self._store[namespace]:
            del self._store[namespace][key]
            return True
        return False

    def clear_namespace(self, namespace: str) -> None:
        self._store[namespace].clear()

    def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._history[-limit:]
