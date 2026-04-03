"""FastAPI application for GENUS feedback system."""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from contextlib import asynccontextmanager

from genus.storage import MemoryStore, FeedbackStore
from genus.communication import EventBus
from .schemas import (
    FeedbackCreate,
    FeedbackResponse,
    DecisionCreate,
    DecisionResponse,
    DecisionWithFeedback
)


# Global instances
memory_store: Optional[MemoryStore] = None
feedback_store: Optional[FeedbackStore] = None
event_bus: Optional[EventBus] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    global memory_store, feedback_store, event_bus

    # Initialize stores and event bus
    memory_store = MemoryStore()
    feedback_store = FeedbackStore()
    event_bus = EventBus()

    await memory_store.init_db()
    await feedback_store.init_db()

    yield

    # Cleanup
    await memory_store.close()
    await feedback_store.close()


app = FastAPI(
    title="GENUS Feedback API",
    description="API for GENUS decision feedback system",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_memory_store() -> MemoryStore:
    """Dependency to get memory store."""
    if memory_store is None:
        raise HTTPException(status_code=500, detail="Memory store not initialized")
    return memory_store


def get_feedback_store() -> FeedbackStore:
    """Dependency to get feedback store."""
    if feedback_store is None:
        raise HTTPException(status_code=500, detail="Feedback store not initialized")
    return feedback_store


def get_event_bus() -> EventBus:
    """Dependency to get event bus."""
    if event_bus is None:
        raise HTTPException(status_code=500, detail="Event bus not initialized")
    return event_bus


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "GENUS Feedback API",
        "version": "0.1.0",
        "endpoints": {
            "feedback": "/feedback",
            "decisions": "/decisions"
        }
    }


@app.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def create_feedback(
    feedback_data: FeedbackCreate,
    store: FeedbackStore = Depends(get_feedback_store),
    memory: MemoryStore = Depends(get_memory_store),
    events: EventBus = Depends(get_event_bus)
):
    """Submit feedback for a decision."""
    # Verify decision exists
    decision = await memory.get_decision(feedback_data.decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")

    # Store feedback
    feedback_id = await store.store_feedback(
        decision_id=feedback_data.decision_id,
        score=feedback_data.score,
        label=feedback_data.label,
        notes=feedback_data.notes,
        source=feedback_data.source
    )

    # Emit event
    await events.emit_event(
        event_type="decision.feedback",
        data={
            "feedback_id": feedback_id,
            "decision_id": feedback_data.decision_id,
            "score": feedback_data.score,
            "label": feedback_data.label
        },
        source="api"
    )

    # Get and return the created feedback
    feedback = await store.get_feedback(feedback_id)
    return FeedbackResponse.model_validate(feedback)


@app.get("/feedback", response_model=List[FeedbackResponse])
async def get_feedback(
    label: Optional[str] = None,
    limit: int = 100,
    store: FeedbackStore = Depends(get_feedback_store)
):
    """Retrieve feedback history."""
    feedbacks = await store.get_all_feedback(label=label, limit=limit)
    return [FeedbackResponse.model_validate(f) for f in feedbacks]


@app.get("/feedback/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback_by_id(
    feedback_id: str,
    store: FeedbackStore = Depends(get_feedback_store)
):
    """Get specific feedback by ID."""
    feedback = await store.get_feedback(feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return FeedbackResponse.model_validate(feedback)


@app.post("/decisions", response_model=DecisionResponse, status_code=201)
async def create_decision(
    decision_data: DecisionCreate,
    store: MemoryStore = Depends(get_memory_store),
    events: EventBus = Depends(get_event_bus)
):
    """Create a new decision."""
    decision_id = await store.store_decision(
        agent_id=decision_data.agent_id,
        decision_type=decision_data.decision_type,
        input_data=decision_data.input_data,
        output_data=decision_data.output_data,
        metadata=decision_data.metadata
    )

    # Emit event
    await events.emit_event(
        event_type="decision.created",
        data={
            "decision_id": decision_id,
            "agent_id": decision_data.agent_id,
            "decision_type": decision_data.decision_type
        },
        source="api"
    )

    decision = await store.get_decision(decision_id)
    return DecisionResponse.model_validate(decision)


@app.get("/decisions", response_model=List[DecisionResponse])
async def get_decisions(
    agent_id: Optional[str] = None,
    decision_type: Optional[str] = None,
    limit: int = 100,
    store: MemoryStore = Depends(get_memory_store)
):
    """Retrieve decisions with optional filters."""
    decisions = await store.get_decisions(
        agent_id=agent_id,
        decision_type=decision_type,
        limit=limit
    )
    return [DecisionResponse.model_validate(d) for d in decisions]


@app.get("/decisions/{decision_id}", response_model=DecisionWithFeedback)
async def get_decision_by_id(
    decision_id: str,
    store: MemoryStore = Depends(get_memory_store),
    feedback_store: FeedbackStore = Depends(get_feedback_store)
):
    """Get specific decision by ID with its feedback."""
    decision = await store.get_decision(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")

    # Get feedback for this decision
    feedbacks = await feedback_store.get_feedback_for_decision(decision_id)

    # Manually construct response with feedback
    decision_dict = DecisionResponse.model_validate(decision).model_dump()
    decision_dict["feedbacks"] = [FeedbackResponse.model_validate(f) for f in feedbacks]

    return DecisionWithFeedback(**decision_dict)


@app.get("/events")
async def get_events(
    event_type: Optional[str] = None,
    limit: int = 100,
    events: EventBus = Depends(get_event_bus)
):
    """Get recent events for observability."""
    event_list = events.get_events(event_type=event_type, limit=limit)
    return [e.to_dict() for e in event_list]
