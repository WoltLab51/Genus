from genus.communication.message_bus import Message
from genus.core.logger import Logger


class SimpleAnalysisAgent:
    def __init__(self, name, bus):
        self.name = name
        self.bus = bus

    async def handle_message(self, message):
        Logger.log(self.name, "analyzing data", message.payload)

        result = {"score": message.payload["value"] * 2}

        new_message = Message(
            topic="data.analyzed",
            payload=result,
            sender_id=self.name
        )

        await self.bus.publish(new_message)