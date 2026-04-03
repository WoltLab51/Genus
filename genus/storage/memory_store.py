"""Memory storage for agent observations and data."""

from typing import Any, Dict, List, Optional
from datetime import datetime, UTC


class MemoryStore:
    """
    In-memory storage for agent observations and working memory.

    This store maintains a history of observations and provides
    query capabilities for agents to access historical data.
    """

    def __init__(self):
        """Initialize the memory store."""
        self._memories: List[Dict[str, Any]] = []

    async def store(self, memory: Dict[str, Any]) -> str:
        """
        Store a memory entry.

        Args:
            memory: Memory data to store

        Returns:
            Memory ID (index as string)
        """
        memory_entry = {
            "id": str(len(self._memories)),
            "timestamp": datetime.now(UTC).isoformat(),
            **memory
        }
        self._memories.append(memory_entry)
        return memory_entry["id"]

    async def retrieve(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific memory by ID.

        Args:
            memory_id: ID of the memory to retrieve

        Returns:
            Memory data or None if not found
        """
        try:
            idx = int(memory_id)
            if 0 <= idx < len(self._memories):
                return self._memories[idx]
        except (ValueError, IndexError):
            pass
        return None

    async def query(self, filters: Optional[Dict[str, Any]] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Query memories with optional filters.

        Args:
            filters: Optional filter criteria
            limit: Maximum number of results

        Returns:
            List of matching memories
        """
        results = self._memories.copy()

        if filters:
            filtered_results = []
            for memory in results:
                match = True
                for key, value in filters.items():
                    if key not in memory or memory[key] != value:
                        match = False
                        break
                if match:
                    filtered_results.append(memory)
            results = filtered_results

        return results[-limit:]

    async def clear(self) -> None:
        """Clear all memories."""
        self._memories.clear()

    def count(self) -> int:
        """Get total count of memories."""
        return len(self._memories)
