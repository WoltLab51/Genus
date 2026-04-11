"""LLMClient — central LLM entry point for all GENUS agents."""

import logging
from typing import Any, Dict, List, Optional

from genus.llm.credential_store import CredentialStore
from genus.llm.models import LLMMessage, LLMRequest, LLMResponse
from genus.llm.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class LLMClient:
    """Central LLM entry point for all GENUS agents.

    Agents only call complete() — which provider responds is transparent
    to the agent.

    Args:
        provider: The LLMProvider to use.
        credential_store: Optional — passed to the provider if it needs a key.

    Usage::

        client = LLMClient(provider=MockProvider())
        response = await client.complete(
            messages=[LLMMessage(role=LLMRole.USER, content="Plan this task")]
        )
        print(response.content)
    """

    def __init__(
        self,
        provider: LLMProvider,
        credential_store: Optional[CredentialStore] = None,
    ) -> None:
        self._provider = provider
        self._credential_store = credential_store

    async def complete(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Sends a prompt and returns the response."""
        request = LLMRequest(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            metadata=metadata or {},
        )
        logger.debug(
            "LLMClient.complete() -> provider=%s, messages=%d",
            self._provider.name,
            len(messages),
        )
        return await self._provider.complete(request)

    async def is_available(self) -> bool:
        """Checks if the current provider is available."""
        return await self._provider.is_available()
