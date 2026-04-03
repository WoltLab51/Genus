"""Example: Basic agent system with feedback."""
import asyncio
from genus.communication import MessageBus, EventBus
from genus.storage import MemoryStore, FeedbackStore
from genus.agents import CoordinatorAgent, WorkerAgent


async def main():
    """Run a basic example with agents and feedback."""
    print("🧬 GENUS Example: Basic Agent System with Feedback\n")

    # Initialize components
    print("Initializing components...")
    message_bus = MessageBus()
    event_bus = EventBus()
    memory_store = MemoryStore()
    feedback_store = FeedbackStore()

    await memory_store.init_db()
    await feedback_store.init_db()

    # Set up event logging
    async def log_event(event):
        print(f"📢 Event: {event.event_type} - {event.data}")

    event_bus.subscribe("decision.made", log_event)
    event_bus.subscribe("decision.feedback", log_event)
    event_bus.subscribe("task.completed", log_event)

    # Create and start agents
    print("Creating agents...")
    coordinator = CoordinatorAgent(
        "coordinator-1",
        message_bus,
        memory_store,
        event_bus
    )
    worker = WorkerAgent(
        "worker-1",
        message_bus,
        memory_store,
        event_bus
    )

    await coordinator.start()
    await worker.start()
    print("✅ Agents started\n")

    # Send task requests
    print("Sending task requests...\n")
    for i in range(3):
        await coordinator.publish("task.request", {
            "task_data": {
                "type": "process",
                "input": f"sample data {i+1}",
                "priority": "normal"
            }
        })
        await asyncio.sleep(0.2)

    # Wait for processing
    await asyncio.sleep(1)

    # Get decisions
    print("\n📊 Retrieving decisions...")
    decisions = await memory_store.get_decisions(limit=10)
    print(f"Found {len(decisions)} decisions\n")

    # Submit feedback on decisions
    print("Submitting feedback...")
    for i, decision in enumerate(decisions):
        score = 1.0 if i % 2 == 0 else -0.5
        label = "success" if score > 0 else "failure"

        feedback_id = await feedback_store.store_feedback(
            decision_id=decision.id,
            score=score,
            label=label,
            notes=f"Test feedback {i+1}",
            source="example_script"
        )
        print(f"  ✓ Feedback {label} (score: {score}) for decision {decision.id[:8]}...")

    # Query feedback
    print("\n📈 Feedback Summary:")
    all_feedback = await feedback_store.get_all_feedback(limit=100)
    success_count = len([f for f in all_feedback if f.label == "success"])
    failure_count = len([f for f in all_feedback if f.label == "failure"])
    avg_score = sum(f.score for f in all_feedback) / len(all_feedback) if all_feedback else 0

    print(f"  Total feedback: {len(all_feedback)}")
    print(f"  Success: {success_count}")
    print(f"  Failure: {failure_count}")
    print(f"  Average score: {avg_score:.2f}")

    # Show decision with feedback
    if decisions:
        print(f"\n📋 Example Decision with Feedback:")
        decision = decisions[0]
        feedbacks = await feedback_store.get_feedback_for_decision(decision.id)

        print(f"  Decision ID: {decision.id}")
        print(f"  Agent: {decision.agent_id}")
        print(f"  Type: {decision.decision_type}")
        print(f"  Timestamp: {decision.timestamp}")
        print(f"  Feedback count: {len(feedbacks)}")
        for fb in feedbacks:
            print(f"    - {fb.label} (score: {fb.score}): {fb.notes}")

    # Show event log
    print("\n📜 Recent Events:")
    events = event_bus.get_events(limit=5)
    for event in events[-5:]:
        print(f"  {event.timestamp.strftime('%H:%M:%S')} - {event.event_type} from {event.source}")

    # Cleanup
    print("\n🧹 Cleaning up...")
    await memory_store.close()
    await feedback_store.close()
    print("✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())
