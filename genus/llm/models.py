"""LLM data models — LLMMessage, LLMRequest, LLMResponse, LLMRole."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LLMRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class LLMMessage:
    role: LLMRole
    content: str


@dataclass
class LLMRequest:
    messages: List[LLMMessage]
    model: Optional[str] = None        # None = provider default
    max_tokens: int = 2048
    temperature: float = 0.2
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str                       # the actual response text
    model: str                         # which model responded
    provider: str                      # which provider
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
