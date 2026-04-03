"""Data Models - Pydantic models for type-safe data contracts."""

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class DataItem(BaseModel):
    """Data item collected by DataCollector agent."""
    source: str = Field(..., description="Source name/identifier")
    content: Any = Field(..., description="Raw content from source")
    tags: List[str] = Field(default_factory=list, description="Optional tags")
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Collection timestamp"
    )


class AnalysisResult(BaseModel):
    """Analysis result from Analysis agent."""
    input_data: Dict[str, Any] = Field(..., description="Input data summary")
    summary: str = Field(..., description="Analysis summary")
    insights: List[str] = Field(default_factory=list, description="Key insights")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    analyzed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Analysis timestamp"
    )


class Decision(BaseModel):
    """Decision from Decision agent."""
    analysis_result: AnalysisResult = Field(..., description="Input analysis")
    recommendation: str = Field(..., description="Decision recommendation")
    priority: int = Field(..., ge=1, le=5, description="Priority (1=highest, 5=lowest)")
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Decision timestamp"
    )


class Feedback(BaseModel):
    """User feedback on decisions."""
    decision_id: str = Field(..., description="Decision identifier")
    rating: int = Field(..., ge=1, le=5, description="Rating (1-5)")
    comment: Optional[str] = Field(None, description="Optional feedback comment")
    provided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Feedback timestamp"
    )
