from datetime import datetime
from typing import Any, Optional
from agents.base_agent import BaseAgent
from models.schemas import Decision, AnalysisResult


class DecisionAgent(BaseAgent):
    """Selects relevant outputs for the user based on analysis."""

    def __init__(self):
        super().__init__(agent_id="decision", name="Decision Agent")
        self._decisions: list[Decision] = []
        self.bus.subscribe("data.analyzed", self._on_data_analyzed)

    async def _on_data_analyzed(self, event: dict) -> None:
        result_raw = event.get("payload", {}).get("result", {})
        if result_raw:
            result = AnalysisResult(**result_raw)
            await self.run({"analysis_result": result})

    async def execute(self, payload: Optional[dict] = None) -> Decision:
        payload = payload or {}
        analysis_result: Optional[AnalysisResult] = payload.get("analysis_result")

        if analysis_result is None:
            last = self.memory.get("analysis", "last_result")
            if last:
                analysis_result = AnalysisResult(**last)
            else:
                analysis_result = AnalysisResult(
                    input_data={},
                    summary="No analysis available.",
                    insights=[],
                    confidence=0.0,
                )

        recommendation = self._decide(analysis_result)
        priority = self._calculate_priority(analysis_result)

        decision = Decision(
            analysis_result=analysis_result,
            recommendation=recommendation,
            priority=priority,
        )
        self._decisions.append(decision)
        self.memory.set("decision", "last_decision", decision.model_dump())
        await self.bus.publish("decision.made", {"decision": decision.model_dump()})
        return decision

    def _decide(self, result: AnalysisResult) -> str:
        if result.confidence >= 0.8:
            return f"High confidence ({result.confidence:.0%}): {result.summary} Act on these insights."
        elif result.confidence >= 0.5:
            return f"Moderate confidence ({result.confidence:.0%}): {result.summary} Review insights before acting."
        else:
            return "Low confidence: Insufficient data. Collect more data before making decisions."

    def _calculate_priority(self, result: AnalysisResult) -> int:
        if result.confidence >= 0.8:
            return 1
        elif result.confidence >= 0.6:
            return 2
        elif result.confidence >= 0.4:
            return 3
        else:
            return 4

    def get_decisions(self) -> list[dict]:
        return [d.model_dump() for d in self._decisions[-20:]]


decision_agent = DecisionAgent()
