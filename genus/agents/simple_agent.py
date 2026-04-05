from genus.communication.message_bus import Message
from genus.core.logger import Logger


class SimpleAgent:
    def __init__(self, name, bus):
        self.name = name
        self.bus = bus

    async def execute(self):
        data = {"value": 42}

        Logger.log(self.name, "collecting data", data)

        message = Message(
            topic="data.collected",
            payload=data,
            sender_id=self.name
        )

        await self.bus.publish(message)