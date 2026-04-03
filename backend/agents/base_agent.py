from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from core.logger import get_logger
from core.memory import memory_store
from core.messaging import event_bus


class BaseAgent(ABC):
    """Abstract base class for all GENUS agents."""

    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name
        self.status = "idle"
        self.last_active: datetime | None = None  # timezone-aware UTC
        self.logger = get_logger(f"agent.{agent_id}")
        self.memory = memory_store
        self.bus = event_bus

    async def run(self, payload: Any = None) -> Any:
        self.status = "running"
        self.last_active = datetime.now(timezone.utc)
        self.logger.info(f"Agent '{self.name}' started")
        try:
            result = await self.execute(payload)
            self.status = "idle"
            self.logger.info(f"Agent '{self.name}' completed")
            return result
        except Exception as exc:
            self.status = "error"
            self.logger.error(f"Agent '{self.name}' error: {exc}")
            raise

    @abstractmethod
    async def execute(self, payload: Any = None) -> Any:
        """Core logic of the agent - must be implemented by each agent."""
        ...

    def get_status(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "last_active": self.last_active.isoformat() if self.last_active else None,
        }
