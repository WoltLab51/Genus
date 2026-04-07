import logging

from genus.core.agent import Agent

logger = logging.getLogger(__name__)


class AnalysisAgent(Agent):
    async def handle_message(self, message):
        if message.topic != "data.collected":
            return

        temperature = message.data.get("temperature")

        if temperature < 20:
            classification = "low"
        elif temperature > 28:
            classification = "high"
        else:
            classification = "normal"

        result = {
            "temperature": temperature,
            "classification": classification
        }
        logger.debug("[Analysis] Temperature: %s → %s", temperature, classification)
        await self.message_bus.publish(
            topic="data.analyzed",
            data=result
        )
