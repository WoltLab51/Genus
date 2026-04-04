import asyncio

from genus.communication.message_bus import MessageBus
from genus.agents.data_collector_agent import DataCollectorAgent
from genus.agents.analysis_agent import AnalysisAgent
from genus.agents.decision_agent import DecisionAgent


async def main():
    bus = MessageBus()

    collector = DataCollectorAgent("collector", bus)
    analysis = AnalysisAgent("analysis", bus)
    decision = DecisionAgent("decision", bus)

    # Subscriptions
    bus.subscribe("data.collected", analysis.handle_message)
    bus.subscribe("data.analyzed", decision.handle_message)

    # Run one cycle
    await collector.execute()

    # kleine Pause damit async durchläuft
    await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
