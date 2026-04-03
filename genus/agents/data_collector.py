"""
Data Collector Agent

Fetches external data (or mock data) and publishes a ``data.collected``
message.  Includes SSRF-mitigation: only ``http``/``https`` schemes are
allowed and requests to private/loopback addresses are rejected.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message
from genus.storage.memory import MemoryStore

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_PREFIXES = ("localhost", "127.", "0.", "169.254.", "::1", "fd", "fc")


def _is_safe_host(host: str) -> bool:
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
    """Fetches and preprocesses external data."""

    def __init__(
        self,
        message_bus: MessageBus,
        memory: MemoryStore,
        *,
        agent_id: str = "data_collector",
        name: str = "Data Collector",
    ) -> None:
        super().__init__(agent_id=agent_id, name=name)
        self._bus = message_bus
        self._memory = memory
        self._collected: List[Dict[str, Any]] = []

    # -- lifecycle -------------------------------------------------------------

    async def initialize(self) -> None:
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        self._transition_state(AgentState.STOPPED)

    # -- core logic ------------------------------------------------------------

    async def execute(self, payload: Any = None) -> List[Dict[str, Any]]:
        payload = payload or {}
        sources = payload.get("sources", [
            {
                "name": "sample_api",
                "url": None,
                "mock_data": {"topic": "AI trends", "value": 42},
            },
        ])

        items: List[Dict[str, Any]] = []
        for source in sources:
            item = await self._fetch(source)
            if item is not None:
                items.append(item)
                self._collected.append(item)

        self._memory.set("data_collector", "last_collection", {
            "count": len(items),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        await self._bus.publish_event(
            "data.collected",
            {"items": items},
            sender=self.id,
        )
        return items

    async def _fetch(self, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            if source.get("url"):
                url = source["url"]
                parsed = urlparse(url)
                if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
                    self._logger.error("Rejected URL with disallowed scheme/host: %s", url)
                    return None
                if not _is_safe_host(parsed.hostname or ""):
                    self._logger.error("Rejected request to private/internal host: %s", url)
                    return None
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    content = resp.json()
            else:
                content = source.get("mock_data", {})

            return {
                "source": source["name"],
                "content": content,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "tags": source.get("tags", []),
            }
        except Exception as exc:
            self._logger.error("Fetch failed for %s: %s", source.get("name"), exc)
            return None

    def get_collected(self) -> List[Dict[str, Any]]:
        return list(self._collected[-50:])
