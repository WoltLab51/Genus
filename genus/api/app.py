"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from genus.core.config import Config
from genus.communication.message_bus import MessageBus
from genus.storage.memory_store import MemoryStore
from genus.storage.decision_store import DecisionStore
from genus.storage.feedback_store import FeedbackStore
from genus.agents.data_collector import DataCollectorAgent
from genus.agents.analysis import AnalysisAgent
from genus.agents.decision import DecisionAgent
from genus.api.errors import ErrorHandlingMiddleware
from genus.api.middleware import AuthenticationMiddleware

logger = logging.getLogger(__name__)


def setup_logging(log_level: str = "INFO"):
    """
    Setup logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for application startup and shutdown.

    Args:
        app: FastAPI application instance
    """
    # Startup
    logger.info("Starting GENUS application...")

    # Initialize configuration
    config = Config.from_env()
    app.state.config = config

    # Setup logging
    setup_logging(config.log_level)

    # Initialize dependencies
    message_bus = MessageBus()
    memory_store = MemoryStore()
    decision_store = DecisionStore()
    feedback_store = FeedbackStore()

    # Store in app state
    app.state.message_bus = message_bus
    app.state.memory_store = memory_store
    app.state.decision_store = decision_store
    app.state.feedback_store = feedback_store

    # Initialize agents
    data_collector = DataCollectorAgent(message_bus, memory_store)
    analysis_agent = AnalysisAgent(message_bus, memory_store)
    decision_agent = DecisionAgent(message_bus, decision_store)

    # Store agents in app state
    app.state.agents = [data_collector, analysis_agent, decision_agent]

    # Initialize all agents
    for agent in app.state.agents:
        await agent.initialize()
        await agent.start()

    logger.info("GENUS application started successfully")

    yield

    # Shutdown
    logger.info("Shutting down GENUS application...")

    # Stop all agents
    for agent in app.state.agents:
        await agent.stop()

    logger.info("GENUS application shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="GENUS",
        description="Generic Engineering System for Universal Solutions",
        version="0.1.0",
        lifespan=lifespan
    )

    # Root endpoint (excluded from auth)
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {"message": "GENUS API", "version": "0.1.0"}

    # Health check endpoint (excluded from auth)
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy"}

    # API endpoints requiring authentication
    @app.post("/data/collect")
    async def collect_data(data: dict):
        """
        Collect data for processing.

        Args:
            data: Data to collect

        Returns:
            Confirmation message
        """
        await app.state.message_bus.publish("data.collect", data)
        return {"status": "accepted", "message": "Data collection initiated"}

    @app.get("/memory")
    async def get_memories(limit: int = 10):
        """
        Get recent memories.

        Args:
            limit: Maximum number of memories to return

        Returns:
            List of memories
        """
        memories = await app.state.memory_store.query(limit=limit)
        return {"memories": memories, "count": len(memories)}

    @app.get("/decisions")
    async def get_decisions(agent: str = None, limit: int = 10):
        """
        Get recent decisions.

        Args:
            agent: Optional agent name filter
            limit: Maximum number of decisions to return

        Returns:
            List of decisions
        """
        decisions = await app.state.decision_store.query_decisions(
            agent=agent,
            limit=limit
        )
        return {"decisions": decisions, "count": len(decisions)}

    @app.get("/feedback")
    async def get_feedback(target: str = None, limit: int = 10):
        """
        Get recent feedback.

        Args:
            target: Optional target filter
            limit: Maximum number of feedback entries to return

        Returns:
            List of feedback entries
        """
        feedback = await app.state.feedback_store.query_feedback(
            target=target,
            limit=limit
        )
        return {"feedback": feedback, "count": len(feedback)}

    @app.post("/feedback")
    async def submit_feedback(feedback: dict):
        """
        Submit feedback.

        Args:
            feedback: Feedback data

        Returns:
            Feedback ID
        """
        feedback_id = await app.state.feedback_store.store_feedback(
            target=feedback.get("target", "system"),
            feedback_type=feedback.get("type", "general"),
            content=feedback.get("content", {}),
            source=feedback.get("source")
        )
        return {"feedback_id": feedback_id, "status": "stored"}

    # Add middleware (order matters - last added is executed first)
    # Error handling should be outermost
    app.add_middleware(ErrorHandlingMiddleware)

    # Authentication middleware with excluded paths
    # Note: We create a factory function to avoid accessing app.state.config
    # before it's initialized
    @app.middleware("http")
    async def auth_middleware(request, call_next):
        """Authentication middleware wrapper."""
        # Excluded paths: GET / and GET /health
        excluded = []
        if request.url.path == "/" and request.method == "GET":
            return await call_next(request)
        if request.url.path == "/health" and request.method == "GET":
            return await call_next(request)

        # Use the middleware logic
        middleware = AuthenticationMiddleware(
            app,
            api_key=app.state.config.api_key,
            excluded_paths=excluded
        )
        return await middleware.dispatch(request, call_next)

    return app
