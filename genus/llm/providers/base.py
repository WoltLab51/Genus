"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from genus.llm.models import LLMRequest, LLMResponse


@dataclass
class ProviderCapabilities:
    name: str
    local: bool                    # runs on the Pi itself?
    cost_per_1k_tokens: float      # 0.0 for local providers
    max_context_tokens: int
    strengths: List[str]           # e.g. ["code", "reasoning", "planning"]
    requires_api_key: bool


class LLMProvider(ABC):
    """Abstract base class for all LLM providers.

    Each new provider only needs to implement this class and place its
    file in genus/llm/providers/ — no other code needs to change.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name, e.g. 'openai' or 'ollama'."""

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Describes what this provider can do and what it costs."""

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Sends a request and returns a response.

        Raises:
            LLMProviderUnavailableError: Provider is not reachable.
            LLMCredentialMissingError: API key is missing.
            LLMRateLimitError: Rate limit reached.
            LLMError: Any other error.
        """

    @abstractmethod
    async def is_available(self) -> bool:
        """Checks if the provider is currently available (health check)."""
