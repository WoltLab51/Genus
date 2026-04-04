from genus.core.agent import Agent


class DataCollectorAgent(Agent):
    async def execute(self):
        # Simulierte Daten (z.B. Temperatur)
        data = {
            "temperature": 25.0
        }

        # Nachricht veröffentlichen
        await self.message_bus.publish(
            topic="data.collected",
            data=data
        )
