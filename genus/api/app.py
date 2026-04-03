"""
FastAPI application factory for GENUS.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, status, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging

from genus.core.config import Config
from genus.communication.message_bus import MessageBus
from genus.storage.stores import MemoryStore, DecisionStore, FeedbackStore
from genus.agents.data_collector import DataCollectorAgent
from genus.agents.analysis import AnalysisAgent
from genus.agents.decision import DecisionAgent
from genus.api.middleware import AuthenticationMiddleware
from genus.api.errors import ErrorHandlingMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Pydantic models for API
class DataInput(BaseModel):
    """Input data model."""

    data: Any = Field(..., description="Data to be processed")


class FeedbackInput(BaseModel):
    """Feedback input model."""

    decision_id: str = Field(..., description="Decision ID to provide feedback for")
    score: float = Field(..., ge=0.0, le=1.0, description="Feedback score (0.0 to 1.0)")
    label: str = Field(..., description="Feedback label: 'success' or 'failure'")
    comment: Optional[str] = Field(None, description="Optional comment")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    agents: Dict[str, str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context.
    All dependencies are created here and passed to agents via constructor injection.
    FastAPI TestClient must be used with context manager to execute lifespan events.
    """
    logger.info("Starting GENUS application...")

    # Create dependencies
    config = Config()
    message_bus = MessageBus()
    memory_store = MemoryStore(config.database_url)
    decision_store = DecisionStore(config.database_url)
    feedback_store = FeedbackStore(config.database_url)

    # Initialize stores
    await memory_store.initialize()
    await decision_store.initialize()
    await feedback_store.initialize()

    # Create agents with dependency injection
    data_collector = DataCollectorAgent("DataCollector", message_bus)
    analysis_agent = AnalysisAgent("AnalysisAgent", message_bus, memory_store)
    decision_agent = DecisionAgent(
        "DecisionAgent", message_bus, decision_store, feedback_store
    )

    # Initialize and start agents (strict lifecycle)
    agents = [data_collector, analysis_agent, decision_agent]
    for agent in agents:
        await agent.initialize()
        await agent.start()

    # Store in app state
    app.state.config = config
    app.state.message_bus = message_bus
    app.state.memory_store = memory_store
    app.state.decision_store = decision_store
    app.state.feedback_store = feedback_store
    app.state.data_collector = data_collector
    app.state.analysis_agent = analysis_agent
    app.state.decision_agent = decision_agent

    logger.info("GENUS application started successfully")

    yield

    # Cleanup
    logger.info("Shutting down GENUS application...")
    for agent in agents:
        await agent.stop()

    await memory_store.close()
    await decision_store.close()
    await feedback_store.close()

    logger.info("GENUS application shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="GENUS - Learning Decision System",
        description="A learning system that improves decisions based on feedback",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Add error handling middleware first
    config = Config()
    app.add_middleware(ErrorHandlingMiddleware, debug=config.debug)

    # Add authentication middleware
    app.add_middleware(AuthenticationMiddleware, api_key=config.api_key)

    @app.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
    async def health_check():
        """Health check endpoint (no authentication required)."""
        agents_status = {
            "data_collector": app.state.data_collector.state.value,
            "analysis_agent": app.state.analysis_agent.state.value,
            "decision_agent": app.state.decision_agent.state.value,
        }
        return {"status": "healthy", "agents": agents_status}

    @app.post("/data", status_code=status.HTTP_202_ACCEPTED)
    async def submit_data(data_input: DataInput):
        """
        Submit data for processing.
        This triggers the full pipeline: data collection -> analysis -> decision.
        """
        await app.state.data_collector.collect_data(data_input.data)
        return {"status": "accepted", "message": "Data submitted for processing"}

    @app.post("/feedback", status_code=status.HTTP_201_CREATED)
    async def submit_feedback(feedback_input: FeedbackInput):
        """
        Submit feedback for a decision.
        This enables the learning mechanism.
        """
        # Validate label
        if feedback_input.label not in ["success", "failure"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Label must be 'success' or 'failure'",
            )

        # Check if decision exists
        decision = await app.state.decision_store.get_decision(feedback_input.decision_id)
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Decision {feedback_input.decision_id} not found",
            )

        # Submit feedback
        await app.state.decision_agent.submit_feedback(
            decision_id=feedback_input.decision_id,
            score=feedback_input.score,
            label=feedback_input.label,
            comment=feedback_input.comment,
        )

        return {
            "status": "created",
            "message": "Feedback submitted successfully",
            "decision_id": feedback_input.decision_id,
        }

    @app.get("/decisions", response_model=List[Dict[str, Any]])
    async def get_decisions():
        """Get all decisions."""
        decisions = await app.state.decision_store.get_all_decisions()
        return decisions

    @app.get("/decisions/{decision_id}", response_model=Dict[str, Any])
    async def get_decision(decision_id: str):
        """Get a specific decision by ID."""
        decision = await app.state.decision_store.get_decision(decision_id)
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Decision {decision_id} not found",
            )
        return decision

    @app.get("/feedback", response_model=List[Dict[str, Any]])
    async def get_feedback():
        """Get all feedback."""
        feedback = await app.state.feedback_store.get_all_feedback()
        return feedback

    @app.get("/learning/analysis", response_model=Dict[str, Any])
    async def get_learning_analysis():
        """
        Get learning analysis showing patterns and performance.
        This endpoint provides observability into the learning mechanism.
        """
        analysis = await app.state.decision_agent.learning_engine.analyze_feedback()
        return analysis

    @app.get("/messages", response_model=List[Dict[str, Any]])
    async def get_messages():
        """Get message history for observability."""
        return app.state.message_bus.get_message_history()

    return app
