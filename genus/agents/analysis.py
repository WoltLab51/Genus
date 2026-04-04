"""
Analysis Agent Implementation

Simple agent that analyzes collected data.
"""

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message, MessagePriority
from genus.utils.logger import get_logger
from typing import Optional


class AnalysisAgent(Agent):
    """
    Analysis agent that processes collected data and performs simple analysis.

    Demonstrates:
    - Subscribing to data topics
    - Processing data
    - Publishing analysis results
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        message_bus: Optional[MessageBus] = None
    ):
        """
        Initialize the analysis agent.

        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            message_bus: Message bus for communication
        """
        super().__init__(agent_id, name)
        self._message_bus = message_bus
        self._logger = get_logger(f"{self.__class__.__name__}.{self.id}")
        self._running = False
        self._analysis_count = 0

    async def initialize(self) -> None:
        """Initialize the analysis agent."""
        self._logger.info(f"Initializing {self.name}")

        if self._message_bus:
            # Subscribe to data.collected topic
            self._message_bus.subscribe(
                "data.collected",
                self.id,
                self.process_message
            )
            self._logger.info(f"Subscribed to 'data.collected'")

        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Start the analysis agent."""
        self._logger.info(f"Starting {self.name}")
        self._running = True
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        """Stop the analysis agent."""
        self._logger.info(f"Stopping {self.name}")
        self._running = False

        if self._message_bus:
            self._message_bus.unsubscribe_all(self.id)

        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Message) -> None:
        """
        Process an incoming data message and perform analysis.

        Args:
            message: The message to process
        """
        self._logger.info(f"Analyzing data from {message.sender_id}")

        # Extract data from payload
        data = message.payload

        # Perform simple analysis
        analysis_result = {
            "original_data": data,
            "analysis": {
                "temperature_status": self._analyze_temperature(data.get("temperature")),
                "humidity_status": self._analyze_humidity(data.get("humidity")),
                "summary": "Data analyzed successfully"
            },
            "analyzed_by": self.id
        }

        self._analysis_count += 1
        self._logger.info(f"Analysis #{self._analysis_count} completed: {analysis_result['analysis']['summary']}")

        # Publish analysis result
        if self._message_bus:
            result_message = Message(
                topic="data.analyzed",
                payload=analysis_result,
                sender_id=self.id,
                priority=MessagePriority.NORMAL,
            )
            await self._message_bus.publish(result_message)
            self._logger.info(f"Published data.analyzed message")

    def _analyze_temperature(self, temp: float) -> str:
        """Analyze temperature value."""
        if temp is None:
            return "unknown"
        if temp < 20:
            return "cold"
        elif temp > 25:
            return "warm"
        else:
            return "normal"

    def _analyze_humidity(self, humidity: float) -> str:
        """Analyze humidity value."""
        if humidity is None:
            return "unknown"
        if humidity < 40:
            return "dry"
        elif humidity > 70:
            return "humid"
        else:
            return "normal"

    def get_stats(self) -> dict:
        """
        Get analysis agent statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            "analysis_count": self._analysis_count,
            "state": self.state.value,
        }
