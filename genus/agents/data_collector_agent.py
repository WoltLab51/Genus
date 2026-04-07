import logging

from genus.core.agent import Agent

logger = logging.getLogger(__name__)


class DataCollectorAgent(Agent):
    async def execute(self):
        data = {
            "temperature": 25.0
        }

        logger.debug("[Collector] Collected data: %s", data)
        await self.message_bus.publish(
            topic="data.collected",
            data=data
        )
