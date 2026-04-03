from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Optional


class AgentStatus(BaseModel):
    agent_id: str
    name: str
    status: str  # "idle", "running", "error"
    last_active: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataItem(BaseModel):
    source: str
    content: Any
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    tags: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    input_data: Any
    summary: str
    insights: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


class Decision(BaseModel):
    analysis_result: AnalysisResult
    recommendation: str
    priority: int = Field(ge=1, le=5, default=3)
    decided_at: datetime = Field(default_factory=datetime.utcnow)


class EventLogEntry(BaseModel):
    type: str
    payload: Any
    timestamp: str


class MemoryEntry(BaseModel):
    namespace: str
    key: str
    value: Any
