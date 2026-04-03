"""API schemas for GENUS system."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime


class FeedbackCreate(BaseModel):
    """Schema for creating feedback."""
    decision_id: str = Field(..., description="ID of the decision to provide feedback for")
    score: float = Field(..., ge=-1.0, le=1.0, description="Feedback score from -1 to 1")
    label: str = Field(..., description="Feedback label: success, failure, or neutral")
    notes: Optional[str] = Field(None, description="Optional notes about the feedback")
    source: Optional[str] = Field(None, description="Source of the feedback")

    @field_validator("label")
    @classmethod
    def validate_label(cls, v):
        valid_labels = ["success", "failure", "neutral"]
        if v not in valid_labels:
            raise ValueError(f"Label must be one of: {', '.join(valid_labels)}")
        return v


class FeedbackResponse(BaseModel):
    """Schema for feedback response."""
    id: str
    decision_id: str
    score: float
    label: str
    timestamp: datetime
    notes: Optional[str] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class DecisionCreate(BaseModel):
    """Schema for creating a decision."""
    agent_id: str = Field(..., description="ID of the agent making the decision")
    decision_type: str = Field(..., description="Type of decision")
    input_data: Optional[Dict[str, Any]] = Field(None, description="Input data for the decision")
    output_data: Optional[Dict[str, Any]] = Field(None, description="Output data from the decision")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class DecisionResponse(BaseModel):
    """Schema for decision response."""
    id: str
    agent_id: str
    decision_type: str
    timestamp: datetime
    input_data: Optional[str] = None
    output_data: Optional[str] = None
    meta_data: Optional[str] = None

    class Config:
        from_attributes = True


class DecisionWithFeedback(DecisionResponse):
    """Schema for decision with its feedback."""
    feedbacks: list[FeedbackResponse] = []

    class Config:
        from_attributes = True
