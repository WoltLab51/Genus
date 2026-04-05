import asyncio

from genus.communication.message_bus import MessageBus
from genus.agents.simple_agent import SimpleAgent
from genus.agents.simple_analysis_agent import SimpleAnalysisAgent
from genus.agents.simple_decision_agent import SimpleDecisionAgent
from genus.agents.simple_feedback_agent import SimpleFeedbackAgent


async def main():
    bus = MessageBus()

    collector = SimpleAgent("collector", bus)
    analysis = SimpleAnalysisAgent("analysis", bus)
    decision = SimpleDecisionAgent("decision", bus)
    feedback = SimpleFeedbackAgent("feedback", bus)

    # Subscriptions (WICHTIG: 3 Parameter!)
    bus.subscribe("data.collected", "analysis", analysis.handle_message)
    bus.subscribe("data.analyzed", "decision", decision.handle_message)
    bus.subscribe("decision.made", "feedback", feedback.handle_message)

    # Start
    await collector.execute()


if __name__ == "__main__":
    asyncio.run(main())