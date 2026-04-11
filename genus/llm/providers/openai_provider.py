"""OpenAI API Provider — GPT-4o, GPT-4o-mini, etc."""

import logging
from typing import Optional

from genus.llm.credential_store import CredentialStore
from genus.llm.exceptions import (
    LLMCredentialMissingError,
    LLMError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
)
from genus.llm.models import LLMRequest, LLMResponse
from genus.llm.providers.base import LLMProvider, ProviderCapabilities

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI API Provider (GPT-4o, GPT-4o-mini, etc.)

    Requires: openai>=1.0.0 (lazy import — no error if not installed,
    ImportError is converted to LLMProviderUnavailableError at complete() time).

    The API key comes from CredentialStore, NOT directly from an environment
    variable.

    Args:
        credential_store: CredentialStore for API key access.
        default_model: Default model. Default: "gpt-4o-mini"
        timeout_s: Request timeout in seconds. Default: 60.0
        base_url: Optional alternative base URL (for OpenAI-compatible APIs).
    """

    name = "openai"

    def __init__(
        self,
        credential_store: Optional[CredentialStore] = None,
        default_model: str = "gpt-4o-mini",
        timeout_s: float = 60.0,
        base_url: Optional[str] = None,
    ) -> None:
        self._credential_store = credential_store
        self._default_model = default_model
        self._timeout_s = timeout_s
        self._base_url = base_url

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="openai",
            local=False,
            cost_per_1k_tokens=0.00015,  # gpt-4o-mini input
            max_context_tokens=128000,
            strengths=["code", "reasoning", "planning", "review"],
            requires_api_key=True,
        )

    def _get_api_key(self) -> Optional[str]:
        """Retrieves the API key from CredentialStore if available."""
        if self._credential_store is None:
            return None
        try:
            return self._credential_store.get("openai")
        except Exception:
            return None

    def _build_client(self, openai_module, api_key: str):
        """Builds an AsyncOpenAI client."""
        kwargs = {
            "api_key": api_key,
            "timeout": self._timeout_s,
        }
        if self._base_url is not None:
            kwargs["base_url"] = self._base_url
        return openai_module.AsyncOpenAI(**kwargs)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Sends a request to the OpenAI API.

        Error mapping:
        - openai.AuthenticationError → LLMCredentialMissingError
        - openai.RateLimitError → LLMRateLimitError
        - openai.APIConnectionError → LLMProviderUnavailableError
        - All other openai.OpenAIError → LLMError
        - ImportError (openai not installed) → LLMProviderUnavailableError
        """
        try:
            import openai
        except ImportError:
            raise LLMProviderUnavailableError(
                "openai package not installed. Run: pip install openai"
            )

        api_key = self._get_api_key()
        if not api_key:
            raise LLMCredentialMissingError(
                "OpenAI API key not found in CredentialStore."
            )

        model = request.model or self._default_model
        messages = [
            {"role": msg.role.value, "content": msg.content}
            for msg in request.messages
        ]

        client = self._build_client(openai, api_key)
        import time

        start = time.monotonic()
        try:
            chat_response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except openai.AuthenticationError as exc:
            raise LLMCredentialMissingError(
                f"OpenAI authentication failed: {exc}"
            ) from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimitError(
                f"OpenAI rate limit reached: {exc}"
            ) from exc
        except openai.APIConnectionError as exc:
            raise LLMProviderUnavailableError(
                f"OpenAI API not reachable: {exc}"
            ) from exc
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI error: {exc}") from exc

        latency_ms = (time.monotonic() - start) * 1000.0
        choice = chat_response.choices[0]
        usage = chat_response.usage

        return LLMResponse(
            content=choice.message.content or "",
            model=chat_response.model,
            provider=self.name,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
        )

    async def is_available(self) -> bool:
        """Checks if OpenAI is reachable (tries to fetch models list).

        Returns False if no API key is present or no network connectivity.
        """
        try:
            import openai
        except ImportError:
            return False

        api_key = self._get_api_key()
        if not api_key:
            return False

        try:
            client = self._build_client(openai, api_key)
            await client.models.list()
            return True
        except Exception:
            return False
