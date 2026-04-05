from genus.communication.message_bus import Message
from genus.core.logger import Logger
from genus.core.memory import Memory


class SimpleDecisionAgent:
    def __init__(self, name, bus):
        self.name = name
        self.bus = bus

    async def handle_message(self, message):
        stats = Memory.get_stats()

        Logger.log(self.name, "making decision", {
            "input": message.payload,
            "memory": stats
        })

        base_score = message.payload["score"]

        # 🔥 LEARNING LOGIC
        threshold = 50

        if stats["good_ratio"] > 0.7:
            threshold = 40  # aggressiver
        elif stats["good_ratio"] < 0.3:
            threshold = 60  # vorsichtiger

        decision = "BUY" if base_score > threshold else "WAIT"

        Logger.log(self.name, f"decision = {decision} (threshold={threshold})")

        new_message = Message(
            topic="decision.made",
            payload={"decision": decision},
            sender_id=self.name
        )

        await self.bus.publish(new_message)