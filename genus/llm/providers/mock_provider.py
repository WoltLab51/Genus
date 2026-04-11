"""MockProvider — fully deterministic test provider."""

import asyncio
from typing import List, Optional

from genus.llm.exceptions import LLMProviderUnavailableError
from genus.llm.models import LLMRequest, LLMResponse
from genus.llm.providers.base import LLMProvider, ProviderCapabilities


class MockProvider(LLMProvider):
    """Test provider with configurable responses.

    Args:
        responses: List of response strings returned in order. After the last
                   element the last entry is repeated indefinitely.
        latency_ms: Simulated latency in milliseconds.
        fail_after: After this many calls LLMProviderUnavailableError is raised.
                    None = never fail.
        available: Whether is_available() returns True.
    """

    _name = "mock"

    def __init__(
        self,
        responses: Optional[List[str]] = None,
        latency_ms: float = 0.0,
        fail_after: Optional[int] = None,
        available: bool = True,
    ) -> None:
        self._responses = responses or ["Mock response."]
        self._call_count = 0
        self._latency_ms = latency_ms
        self._fail_after = fail_after
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self._name,
            local=True,
            cost_per_1k_tokens=0.0,
            max_context_tokens=4096,
            strengths=["testing"],
            requires_api_key=False,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Returns the next configured response.

        Raises:
            LLMProviderUnavailableError: when fail_after is exceeded.
        """
        if self._fail_after is not None and self._call_count >= self._fail_after:
            raise LLMProviderUnavailableError(
                f"MockProvider: fail_after={self._fail_after} reached."
            )

        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        index = min(self._call_count, len(self._responses) - 1)
        content = self._responses[index]
        self._call_count += 1

        model = request.model or "mock-model"
        return LLMResponse(
            content=content,
            model=model,
            provider=self._name,
            latency_ms=self._latency_ms,
        )

    async def is_available(self) -> bool:
        return self._available
