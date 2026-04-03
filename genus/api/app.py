"""FastAPI application factory."""

from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from genus.core.config import Config
from genus.core.system_state import SystemStateTracker
from genus.communication.message_bus import MessageBus
from genus.storage.memory_store import MemoryStore
from genus.storage.decision_store import DecisionStore
from genus.storage.feedback_store import FeedbackStore
from genus.agents.data_collector import DataCollectorAgent
from genus.agents.analysis import AnalysisAgent
from genus.agents.decision import DecisionAgent
from genus.api.middleware import AuthMiddleware
from genus.api.errors import ErrorHandlingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management.

    Creates dependencies and initializes agents.
    """
    # Create dependencies (no global singletons)
    config = Config()
    state_tracker = SystemStateTracker()
    message_bus = MessageBus(state_tracker=state_tracker)
    memory_store = MemoryStore()
    decision_store = DecisionStore()
    feedback_store = FeedbackStore()

    # Create agents with dependency injection
    agents = [
        DataCollectorAgent(message_bus, memory_store),
        AnalysisAgent(message_bus, memory_store),
        DecisionAgent(message_bus, decision_store),
    ]

    # Initialize and start agents
    for agent in agents:
        await agent.initialize()
        await agent.start()

    # Store in app state
    app.state.config = config
    app.state.state_tracker = state_tracker
    app.state.message_bus = message_bus
    app.state.memory_store = memory_store
    app.state.decision_store = decision_store
    app.state.feedback_store = feedback_store
    app.state.agents = agents

    # Background task to update agent states in tracker
    for agent in agents:
        state_tracker.update_agent_state(
            agent.name,
            agent.state.value,
            agent.last_success
        )

    yield

    # Cleanup: stop agents
    for agent in agents:
        await agent.stop()


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="GENUS",
        description="Self-aware agent orchestration system",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add error handling middleware
    app.add_middleware(ErrorHandlingMiddleware, debug=False)

    # Add auth middleware (will be configured after app state is available)
    @app.middleware("http")
    async def auth_middleware(request, call_next):
        """Authentication middleware."""
        middleware = AuthMiddleware(app, app.state.config)
        return await middleware.dispatch(request, call_next)

    @app.get("/health")
    async def basic_health():
        """Basic health check endpoint (no auth required).

        Returns:
            Simple health status
        """
        return {"status": "ok"}

    @app.get("/system/health")
    async def system_health():
        """Detailed system health endpoint (auth required).

        Returns:
            Comprehensive health report including:
            - System state (healthy/degraded/failing)
            - Agent statuses
            - Recent errors
            - Last successful runs
            - Error counts
        """
        state_tracker: SystemStateTracker = app.state.state_tracker

        # Update agent states before generating report
        for agent in app.state.agents:
            state_tracker.update_agent_state(
                agent.name,
                agent.state.value,
                agent.last_success
            )

        # Get agent statuses
        agent_statuses = {
            agent.name: agent.get_status()
            for agent in app.state.agents
        }

        # Get health report from tracker
        health_report = state_tracker.get_health_report()

        # Add agent statuses to report
        health_report["agents"] = agent_statuses

        # Add message bus stats
        health_report["message_bus_stats"] = app.state.message_bus.get_stats()

        return health_report

    @app.post("/data/ingest")
    async def ingest_data(data: Dict[str, Any]):
        """Ingest raw data into the system.

        Args:
            data: Raw data to process

        Returns:
            Acknowledgment
        """
        message_bus: MessageBus = app.state.message_bus
        await message_bus.publish("data.raw", data, source="api")
        return {"status": "ingested", "data": data}

    @app.get("/decisions")
    async def list_decisions(agent: str = None, limit: int = 100):
        """List recent decisions.

        Args:
            agent: Optional agent filter
            limit: Maximum number of decisions to return

        Returns:
            List of decisions
        """
        decision_store: DecisionStore = app.state.decision_store
        decisions = await decision_store.list_decisions(agent=agent, limit=limit)
        return {"decisions": decisions}

    @app.post("/feedback")
    async def submit_feedback(
        decision_id: str,
        rating: int,
        comment: str = None
    ):
        """Submit feedback on a decision.

        Args:
            decision_id: Decision to rate
            rating: Rating from 1-5
            comment: Optional feedback comment

        Returns:
            Acknowledgment
        """
        feedback_store: FeedbackStore = app.state.feedback_store
        import uuid
        feedback_id = str(uuid.uuid4())

        await feedback_store.record_feedback(
            feedback_id=feedback_id,
            decision_id=decision_id,
            rating=rating,
            comment=comment
        )

        return {
            "status": "recorded",
            "feedback_id": feedback_id,
        }

    return app
