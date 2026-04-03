import httpx
from datetime import datetime
from typing import Any, Optional
from agents.base_agent import BaseAgent
from models.schemas import DataItem


class DataCollectorAgent(BaseAgent):
    """Fetches and preprocesses external data."""

    def __init__(self):
        super().__init__(agent_id="data_collector", name="Data Collector")
        self._collected_items: list[DataItem] = []

    async def execute(self, payload: Optional[dict] = None) -> list[DataItem]:
        payload = payload or {}
        sources = payload.get("sources", [
            {"name": "sample_api", "url": None, "mock_data": {"topic": "AI trends", "value": 42}},
        ])

        items = []
        for source in sources:
            item = await self._fetch(source)
            if item:
                items.append(item)
                self._collected_items.append(item)

        self.memory.set("data_collector", "last_collection", {
            "count": len(items),
            "timestamp": datetime.utcnow().isoformat(),
        })

        await self.bus.publish("data.collected", {"items": [i.model_dump() for i in items]})
        return items

    async def _fetch(self, source: dict) -> Optional[DataItem]:
        try:
            if source.get("url"):
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(source["url"])
                    resp.raise_for_status()
                    content = resp.json()
            else:
                content = source.get("mock_data", {})

            return DataItem(
                source=source["name"],
                content=content,
                tags=source.get("tags", []),
            )
        except Exception as exc:
            self.logger.error(f"Failed to fetch from {source.get('name')}: {exc}")
            return None

    def get_collected(self) -> list[dict]:
        return [i.model_dump() for i in self._collected_items[-50:]]


data_collector_agent = DataCollectorAgent()
