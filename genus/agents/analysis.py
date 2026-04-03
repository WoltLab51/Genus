"""
Analysis Agent

Subscribes to ``data.collected`` events (during ``initialize()``, not
``__init__``).  Extracts simple insights and publishes ``data.analyzed``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message
from genus.storage.memory import MemoryStore


class AnalysisAgent(Agent):
    """Processes and interprets collected data."""

    def __init__(
        self,
        message_bus: MessageBus,
        memory: MemoryStore,
        *,
        agent_id: str = "analysis",
        name: str = "Analysis Agent",
    ) -> None:
        super().__init__(agent_id=agent_id, name=name)
        self._bus = message_bus
        self._memory = memory
        self._results: List[Dict[str, Any]] = []

    # -- lifecycle -------------------------------------------------------------

    async def initialize(self) -> None:
        self._bus.subscribe("data.collected", self._on_data_collected)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        self._bus.unsubscribe("data.collected", self._on_data_collected)
        self._transition_state(AgentState.STOPPED)

    # -- event handler ---------------------------------------------------------

    async def _on_data_collected(self, message: Message) -> None:
        items = message.payload.get("items", [])
        if items:
            await self.execute({"items": items})

    # -- core logic ------------------------------------------------------------

    async def execute(self, payload: Any = None) -> Dict[str, Any]:
        payload = payload or {}
        items: List[Dict[str, Any]] = payload.get("items", [])

        if not items:
            summary = "No data available for analysis."
            insights: List[str] = []
            confidence = 0.0
        else:
            sources = {i.get("source", "unknown") for i in items}
            summary = f"Analyzed {len(items)} data item(s) from sources: {', '.join(sources)}."
            insights = self._extract_insights(items)
            confidence = min(0.5 + len(items) * 0.1, 0.95)

        result: Dict[str, Any] = {
            "input_data": {"item_count": len(items)},
            "summary": summary,
            "insights": insights,
            "confidence": confidence,
        }
        self._results.append(result)
        self._memory.set("analysis", "last_result", result)
        await self._bus.publish_event(
            "data.analyzed",
            {"result": result},
            sender=self.id,
        )
        return result

    @staticmethod
    def _extract_insights(items: List[Dict[str, Any]]) -> List[str]:
        insights: List[str] = []
        for item in items:
            content = item.get("content", {})
            if isinstance(content, dict):
                for k, v in content.items():
                    insights.append(f"Key '{k}' has value: {v}")
            else:
                insights.append(f"Data from '{item.get('source', '?')}': {str(content)[:100]}")
        return insights[:10]

    def get_results(self) -> List[Dict[str, Any]]:
        return list(self._results[-20:])
