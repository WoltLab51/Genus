"""
Pydantic request / response schemas for the GENUS API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
#  Feedback
# ---------------------------------------------------------------------------

class FeedbackCreate(BaseModel):
    decision_id: str = Field(..., description="ID of the decision")
    score: float = Field(..., ge=-1.0, le=1.0, description="Score from -1 to 1")
    label: str = Field(..., description="success / failure / neutral")
    notes: Optional[str] = Field(None)
    source: Optional[str] = Field(None)

    @field_validator("label")
    @classmethod
    def _validate_label(cls, v: str) -> str:
        if v not in ("success", "failure", "neutral"):
            raise ValueError("label must be success, failure, or neutral")
        return v


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    decision_id: str
    score: float
    label: str
    timestamp: datetime
    notes: Optional[str] = None
    source: Optional[str] = None


# ---------------------------------------------------------------------------
#  Decision
# ---------------------------------------------------------------------------

class DecisionCreate(BaseModel):
    agent_id: str = Field(..., description="Agent that made the decision")
    decision_type: str = Field(..., description="Type of decision")
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    decision_type: str
    timestamp: datetime
    input_data: Optional[str] = None
    output_data: Optional[str] = None
    meta_data: Optional[str] = None


class DecisionWithFeedback(DecisionResponse):
    feedbacks: List[FeedbackResponse] = []


# ---------------------------------------------------------------------------
#  Agent status
# ---------------------------------------------------------------------------

class AgentStatusResponse(BaseModel):
    agent_id: str
    name: str
    state: str
    created_at: str
