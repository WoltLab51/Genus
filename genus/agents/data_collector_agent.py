from genus.core.agent import Agent


class DataCollectorAgent(Agent):
    async def execute(self):
        data = {
            "temperature": 25.0
        }

        print(f"[Collector] Collected data: {data}")
        await self.message_bus.publish(
            topic="data.collected",
            data=data
        )
