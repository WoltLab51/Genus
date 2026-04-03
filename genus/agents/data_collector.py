"""DataCollector Agent - Fetches and preprocesses external data."""

import httpx
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import ipaddress
import logging

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message, MessagePriority
from genus.storage.memory import MemoryStore
from genus.storage.models import DataItem


# SSRF Mitigation
_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_PREFIXES = ("localhost", "127.", "0.", "169.254.", "::1", "fd", "fc")


def _is_safe_host(host: str) -> bool:
    """
    Validate host is not private/loopback (SSRF mitigation).

    Args:
        host: Hostname to validate

    Returns:
        True if host is safe to contact
    """
    if not host:
        return False
    hostname = host.split(":")[0].lower()
    for prefix in _BLOCKED_PREFIXES:
        if hostname.startswith(prefix):
            return False
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_global and not addr.is_private and not addr.is_loopback
    except ValueError:
        pass
    return True


class DataCollectorAgent(Agent):
    """
    Collects and preprocesses external data.

    Responsibilities:
    - Fetch data from configured sources
    - Validate URLs (SSRF protection)
    - Store collected items
    - Publish 'data.collected' events

    Clean Architecture:
    - Dependencies injected via constructor
    - Subscriptions in initialize() NOT __init__
    - Communicates only via MessageBus
    """

    def __init__(
        self,
        message_bus: MessageBus,
        memory_store: MemoryStore,
        agent_id: str = "data_collector",
        name: str = "Data Collector"
    ):
        """
        Initialize the Data Collector agent.

        Args:
            message_bus: Message bus for communication
            memory_store: Memory store for state
            agent_id: Unique identifier
            name: Human-readable name
        """
        super().__init__(agent_id, name)
        self._message_bus = message_bus
        self._memory_store = memory_store
        self._logger = logging.getLogger(f"genus.agent.{self.id}")
        self._collected_items: List[DataItem] = []

    async def initialize(self) -> None:
        """Initialize agent and subscribe to topics."""
        self._logger.info(f"Initializing {self.name}")
        # Subscriptions happen HERE, not in __init__
        # (none needed for DataCollector - it's triggered via API)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Start the agent."""
        self._logger.info(f"Starting {self.name}")
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        """Stop the agent."""
        self._logger.info(f"Stopping {self.name}")
        self._message_bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    async def collect(self, sources: Optional[List[Dict[str, Any]]] = None) -> List[DataItem]:
        """
        Collect data from sources.

        Args:
            sources: List of source configurations. Each source has:
                - name: Source identifier
                - url: Optional URL to fetch from
                - mock_data: Optional mock data (for testing)
                - tags: Optional tags

        Returns:
            List of collected data items
        """
        self._update_last_active()

        # Default mock source for demo
        if not sources:
            sources = [
                {
                    "name": "sample_api",
                    "url": None,
                    "mock_data": {"topic": "AI trends", "value": 42},
                }
            ]

        items = []
        for source in sources:
            item = await self._fetch(source)
            if item:
                items.append(item)
                self._collected_items.append(item)

        # Store in memory
        self._memory_store.set(
            self.id,
            "last_collection",
            {
                "count": len(items),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Publish event for downstream agents
        message = Message(
            topic="data.collected",
            payload={"items": [i.model_dump() for i in items]},
            sender_id=self.id,
            priority=MessagePriority.NORMAL,
        )
        await self._message_bus.publish(message)

        self._logger.info(f"Collected {len(items)} items from {len(sources)} sources")
        return items

    async def _fetch(self, source: Dict[str, Any]) -> Optional[DataItem]:
        """
        Fetch data from a single source.

        Args:
            source: Source configuration

        Returns:
            DataItem or None if fetch failed
        """
        try:
            if source.get("url"):
                url = source["url"]
                parsed = urlparse(url)

                # SSRF protection
                if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
                    self._logger.error(f"Rejected URL with disallowed scheme/host: {url}")
                    return None
                if not _is_safe_host(parsed.hostname or ""):
                    self._logger.error(f"Rejected request to private/internal host: {url}")
                    return None

                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    content = resp.json()
            else:
                # Use mock data
                content = source.get("mock_data", {})

            return DataItem(
                source=source["name"],
                content=content,
                tags=source.get("tags", []),
            )
        except Exception as exc:
            self._logger.error(f"Failed to fetch from {source.get('name')}: {exc}")
            return None

    def get_collected(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recently collected items.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of items as dictionaries
        """
        return [i.model_dump() for i in self._collected_items[-limit:]]
