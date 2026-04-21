"""Pydantic models for BuilderAgent workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class BuildRequest(BaseModel):
    name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)
    signature: str = Field(min_length=1)
    domain: str = "general"
    max_repair_attempts: int = Field(default=3, ge=1, le=10)

    @field_validator("description", "signature")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class BuildResult(BaseModel):
    request_id: str
    name: str
    status: Literal["success", "failed", "partial"]
    code: str | None = None
    test_output: str | None = None
    repair_attempts: int = 0
    registered: bool = False
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RepairAttempt(BaseModel):
    attempt: int
    error: str
    repaired_code: str
    test_output: str
    success: bool
