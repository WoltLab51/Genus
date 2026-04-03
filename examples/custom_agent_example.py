"""Example: Custom agent with feedback integration."""
import asyncio
from genus.core import Agent, Message
from genus.communication import MessageBus, EventBus
from genus.storage import MemoryStore, FeedbackStore


class DecisionMakingAgent(Agent):
    """Agent that makes decisions and learns from feedback."""

    def __init__(self, agent_id, message_bus, memory_store=None, event_bus=None):
        super().__init__(agent_id, message_bus)
        self.memory_store = memory_store
        self.event_bus = event_bus
        self.decision_history = []

    async def start(self):
        """Start the agent."""
        self.subscribe("make.decision")
        if self.event_bus:
            await self.event_bus.emit_event(
                "agent.started",
                {"agent_id": self.agent_id, "type": "decision_maker"},
                source=self.agent_id
            )

    async def handle_message(self, message: Message):
        """Handle decision requests."""
        if message.topic == "make.decision":
            await self._make_decision(message.payload)

    async def _make_decision(self, data):
        """Make a decision based on input data."""
        # Simulate decision-making logic
        options = data.get("options", [])
        selected = options[0] if options else "default"

        decision_data = {
            "input": data,
            "selected_option": selected,
            "reasoning": "Selected first available option"
        }

        # Store decision
        if self.memory_store:
            decision_id = await self.memory_store.store_decision(
                agent_id=self.agent_id,
                decision_type="option_selection",
                input_data=data,
                output_data=decision_data
            )
            self.decision_history.append(decision_id)

            # Emit event
            if self.event_bus:
                await self.event_bus.emit_event(
                    "decision.made",
                    {
                        "decision_id": decision_id,
                        "agent_id": self.agent_id,
                        "selected": selected
                    },
                    source=self.agent_id
                )

        # Publish result
        await self.publish("decision.result", {
            "decision_id": decision_id,
            "selected": selected
        })

    async def learn_from_feedback(self, feedback_store):
        """Analyze feedback on past decisions."""
        if not self.decision_history:
            return {"message": "No decisions to learn from"}

        feedback_summary = {
            "total_decisions": len(self.decision_history),
            "total_feedback": 0,
            "positive_feedback": 0,
            "negative_feedback": 0,
            "avg_score": 0.0
        }

        all_scores = []
        for decision_id in self.decision_history:
            feedbacks = await feedback_store.get_feedback_for_decision(decision_id)
            feedback_summary["total_feedback"] += len(feedbacks)

            for fb in feedbacks:
                all_scores.append(fb.score)
                if fb.label == "success":
                    feedback_summary["positive_feedback"] += 1
                elif fb.label == "failure":
                    feedback_summary["negative_feedback"] += 1

        if all_scores:
            feedback_summary["avg_score"] = sum(all_scores) / len(all_scores)

        return feedback_summary


async def main():
    """Run custom agent example."""
    print("🧬 GENUS Example: Custom Agent with Feedback Learning\n")

    # Initialize components
    message_bus = MessageBus()
    event_bus = EventBus()
    memory_store = MemoryStore()
    feedback_store = FeedbackStore()

    await memory_store.init_db()
    await feedback_store.init_db()

    # Create custom agent
    agent = DecisionMakingAgent(
        "decision-agent-1",
        message_bus,
        memory_store,
        event_bus
    )
    await agent.start()
    print("✅ Custom agent started\n")

    # Send decision requests
    print("Making decisions...")
    for i in range(5):
        await agent.publish("make.decision", {
            "problem": f"problem_{i}",
            "options": [f"option_A_{i}", f"option_B_{i}", f"option_C_{i}"]
        })
        await asyncio.sleep(0.1)

    await asyncio.sleep(0.5)

    # Simulate feedback from external evaluator
    print("\nSimulating feedback from evaluator...")
    for i, decision_id in enumerate(agent.decision_history):
        # Vary feedback: mostly positive with some negative
        if i % 3 == 0:
            score, label, notes = -0.3, "failure", "Could have chosen better"
        else:
            score, label, notes = 0.8, "success", "Good choice!"

        await feedback_store.store_feedback(
            decision_id=decision_id,
            score=score,
            label=label,
            notes=notes,
            source="external_evaluator"
        )
        print(f"  Feedback: {label} (score: {score}) for decision {decision_id[:8]}...")

    # Agent learns from feedback
    print("\nAgent analyzing feedback...")
    summary = await agent.learn_from_feedback(feedback_store)

    print("\n📊 Learning Summary:")
    print(f"  Total decisions made: {summary['total_decisions']}")
    print(f"  Total feedback received: {summary['total_feedback']}")
    print(f"  Positive feedback: {summary['positive_feedback']}")
    print(f"  Negative feedback: {summary['negative_feedback']}")
    print(f"  Average score: {summary['avg_score']:.2f}")

    if summary['avg_score'] > 0.5:
        print("\n✅ Agent performance is good!")
    elif summary['avg_score'] > 0:
        print("\n⚠️  Agent performance is acceptable but could improve")
    else:
        print("\n❌ Agent needs improvement")

    # Cleanup
    print("\n🧹 Cleaning up...")
    await memory_store.close()
    await feedback_store.close()
    print("✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())
