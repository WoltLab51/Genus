"""OllamaProvider — local Ollama instance (e.g. on Raspberry Pi)."""

import logging
from typing import Optional

from genus.llm.exceptions import LLMError, LLMProviderUnavailableError
from genus.llm.models import LLMRequest, LLMResponse
from genus.llm.providers.base import LLMProvider, ProviderCapabilities

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.2"
_DEFAULT_TIMEOUT = 120.0


class OllamaProvider(LLMProvider):
    """Local Ollama Provider — runs on the Raspberry Pi.

    Communicates with the Ollama REST API (no API key needed).

    Requires: httpx>=0.24.0 (lazy import).

    Args:
        base_url: Ollama API URL. Default: "http://localhost:11434"
        default_model: Default model. Default: "llama3.2"
        timeout_s: Request timeout. Default: 120.0 (local models are slower)
    """

    name = "ollama"

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        default_model: str = _DEFAULT_MODEL,
        timeout_s: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._timeout_s = timeout_s

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="ollama",
            local=True,
            cost_per_1k_tokens=0.0,
            max_context_tokens=8192,
            strengths=["planning", "reasoning"],
            requires_api_key=False,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Sends a request to the local Ollama instance via /api/chat endpoint.

        Error mapping:
        - httpx.ConnectError → LLMProviderUnavailableError
        - httpx.TimeoutException → LLMProviderUnavailableError
        - HTTP 4xx/5xx → LLMError
        - ImportError (httpx not installed) → LLMProviderUnavailableError
        """
        try:
            import httpx
        except ImportError:
            raise LLMProviderUnavailableError(
                "httpx package not installed. Run: pip install httpx"
            )

        model = request.model or self._default_model
        messages = [
            {"role": msg.role.value, "content": msg.content}
            for msg in request.messages
        ]

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        import time

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                )
        except httpx.ConnectError as exc:
            raise LLMProviderUnavailableError(
                f"Ollama not reachable at {self._base_url}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMProviderUnavailableError(
                f"Ollama request timed out: {exc}"
            ) from exc

        latency_ms = (time.monotonic() - start) * 1000.0

        if response.status_code >= 400:
            raise LLMError(
                f"Ollama returned HTTP {response.status_code}: {response.text}"
            )

        data = response.json()
        content = data.get("message", {}).get("content", "")
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)

        return LLMResponse(
            content=content,
            model=data.get("model", model),
            provider=self.name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )

    async def is_available(self) -> bool:
        """Checks if Ollama is running (GET /api/tags).

        Returns False if not reachable — no exception raised.
        """
        try:
            import httpx
        except ImportError:
            return False

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
