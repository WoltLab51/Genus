from datetime import datetime
from typing import Any, Optional
from agents.base_agent import BaseAgent
from models.schemas import AnalysisResult, DataItem


class AnalysisAgent(BaseAgent):
    """Processes and interprets collected data."""

    def __init__(self):
        super().__init__(agent_id="analysis", name="Analysis Agent")
        self._results: list[AnalysisResult] = []
        self.bus.subscribe("data.collected", self._on_data_collected)

    async def _on_data_collected(self, event: dict) -> None:
        items_raw = event.get("payload", {}).get("items", [])
        if items_raw:
            items = [DataItem(**i) for i in items_raw]
            await self.run({"items": items})

    async def execute(self, payload: Optional[dict] = None) -> AnalysisResult:
        payload = payload or {}
        items: list[DataItem] = payload.get("items", [])

        if not items:
            stored = self.memory.get("data_collector", "last_collection")
            summary = "No data available for analysis."
            insights = []
            confidence = 0.0
        else:
            contents = [str(item.content) for item in items]
            summary = f"Analyzed {len(items)} data item(s) from sources: {', '.join(set(i.source for i in items))}."
            insights = self._extract_insights(items)
            confidence = min(0.5 + len(items) * 0.1, 0.95)

        result = AnalysisResult(
            input_data={"item_count": len(items)},
            summary=summary,
            insights=insights,
            confidence=confidence,
        )
        self._results.append(result)
        self.memory.set("analysis", "last_result", result.model_dump())
        await self.bus.publish("data.analyzed", {"result": result.model_dump()})
        return result

    def _extract_insights(self, items: list[DataItem]) -> list[str]:
        insights = []
        for item in items:
            content = item.content
            if isinstance(content, dict):
                for k, v in content.items():
                    insights.append(f"Key '{k}' has value: {v}")
            else:
                insights.append(f"Data from '{item.source}': {str(content)[:100]}")
        return insights[:10]

    def get_results(self) -> list[dict]:
        return [r.model_dump() for r in self._results[-20:]]


analysis_agent = AnalysisAgent()
