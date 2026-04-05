from genus.core.logger import Logger
from genus.core.memory import Memory


class SimpleFeedbackAgent:
    def __init__(self, name, bus):
        self.name = name
        self.bus = bus

    async def handle_message(self, message):
        Logger.log(self.name, "evaluating decision", message.payload)

        decision = message.payload.get("decision")

        import random

        # 70% Chance dass BUY gut ist
        if decision == "BUY":
            feedback = "GOOD" if random.random() > 0.3 else "BAD"
        else:
            feedback = "NEUTRAL"

        Memory.add_feedback(feedback)

        stats = Memory.get_stats()

        Logger.log(self.name, f"feedback = {feedback}")
        Logger.log(self.name, "memory stats", stats)