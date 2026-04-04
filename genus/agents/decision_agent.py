from genus.core.agent import Agent


class DecisionAgent(Agent):
    async def handle_message(self, message):
        if message.topic != "data.analyzed":
            return

        classification = message.data.get("classification")
        temperature = message.data.get("temperature")

        if classification == "high":
            decision = "decrease"
            action = "Activate cooling"
        elif classification == "low":
            decision = "increase"
            action = "Increase heating"
        else:
            decision = "maintain"
            action = "Keep current state"

        result = {
            "temperature": temperature,
            "classification": classification,
            "decision": decision,
            "action": action
        }

        await self.message_bus.publish(
            topic="decision.made",
            data=result
        )
