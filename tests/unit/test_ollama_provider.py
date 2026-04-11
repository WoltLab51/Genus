"""Tests for genus.llm.providers.ollama_provider — OllamaProvider."""

import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from genus.llm.exceptions import LLMError, LLMProviderUnavailableError
from genus.llm.models import LLMMessage, LLMRequest, LLMRole
from genus.llm.providers.ollama_provider import OllamaProvider


def _make_request(content: str = "Hello") -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role=LLMRole.USER, content=content)],
        max_tokens=256,
        temperature=0.2,
    )


def _make_httpx_mock(
    status_code: int = 200,
    response_data: dict = None,
    connect_error: bool = False,
    timeout_error: bool = False,
):
    """Creates a minimal fake httpx module."""
    if response_data is None:
        response_data = {
            "message": {"role": "assistant", "content": "Ollama response."},
            "model": "llama3.2",
            "prompt_eval_count": 42,
            "eval_count": 128,
        }

    httpx_mod = types.ModuleType("httpx")

    # Exception classes
    httpx_mod.ConnectError = type("ConnectError", (Exception,), {})
    httpx_mod.TimeoutException = type("TimeoutException", (Exception,), {})

    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = json.dumps(response_data)
    mock_response.json = MagicMock(return_value=response_data)

    # Mock client
    mock_client = MagicMock()

    if connect_error:
        mock_client.post = AsyncMock(
            side_effect=httpx_mod.ConnectError("connection refused")
        )
        mock_client.get = AsyncMock(
            side_effect=httpx_mod.ConnectError("connection refused")
        )
    elif timeout_error:
        mock_client.post = AsyncMock(
            side_effect=httpx_mod.TimeoutException("timed out")
        )
        mock_client.get = AsyncMock(
            side_effect=httpx_mod.TimeoutException("timed out")
        )
    else:
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock(return_value=mock_response)

    # AsyncClient context manager
    async_context = MagicMock()
    async_context.__aenter__ = AsyncMock(return_value=mock_client)
    async_context.__aexit__ = AsyncMock(return_value=False)
    httpx_mod.AsyncClient = MagicMock(return_value=async_context)

    return httpx_mod, mock_client


class TestOllamaProviderCapabilities:
    def test_name(self):
        provider = OllamaProvider()
        assert provider.name == "ollama"

    def test_capabilities_local(self):
        provider = OllamaProvider()
        assert provider.capabilities.local is True

    def test_capabilities_no_api_key(self):
        provider = OllamaProvider()
        assert provider.capabilities.requires_api_key is False

    def test_capabilities_zero_cost(self):
        provider = OllamaProvider()
        assert provider.capabilities.cost_per_1k_tokens == 0.0

    def test_capabilities_has_strengths(self):
        provider = OllamaProvider()
        assert "planning" in provider.capabilities.strengths


class TestOllamaProviderCompleteImportError:
    async def test_raises_unavailable_when_httpx_not_installed(self):
        provider = OllamaProvider()
        with patch.dict(sys.modules, {"httpx": None}):
            with pytest.raises(LLMProviderUnavailableError, match="httpx package"):
                await provider.complete(_make_request())


class TestOllamaProviderCompleteWithMock:
    async def test_returns_correct_response(self):
        httpx_mod, _ = _make_httpx_mock()
        provider = OllamaProvider()

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            response = await provider.complete(_make_request())

        assert response.content == "Ollama response."
        assert response.provider == "ollama"
        assert response.model == "llama3.2"

    async def test_token_counts_filled(self):
        httpx_mod, _ = _make_httpx_mock()
        provider = OllamaProvider()

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            response = await provider.complete(_make_request())

        assert response.prompt_tokens == 42
        assert response.completion_tokens == 128

    async def test_request_json_format(self):
        httpx_mod, mock_client = _make_httpx_mock()
        provider = OllamaProvider(default_model="llama3.2")

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            await provider.complete(_make_request("Test prompt"))

        call_kwargs = mock_client.post.call_args.kwargs
        sent_json = call_kwargs["json"]
        assert sent_json is not None
        assert sent_json["model"] == "llama3.2"
        assert sent_json["stream"] is False
        assert sent_json["messages"][0]["role"] == "user"
        assert sent_json["messages"][0]["content"] == "Test prompt"

    async def test_default_model_used_when_none(self):
        httpx_mod, mock_client = _make_httpx_mock()
        provider = OllamaProvider(default_model="phi3")

        request = LLMRequest(
            messages=[LLMMessage(role=LLMRole.USER, content="hi")],
            model=None,
        )

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            await provider.complete(request)

        call_kwargs = mock_client.post.call_args.kwargs
        sent_json = call_kwargs.get("json")
        assert sent_json["model"] == "phi3"

    async def test_http_error_raises_llm_error(self):
        httpx_mod, _ = _make_httpx_mock(
            status_code=500,
            response_data={"error": "model not found"},
        )
        provider = OllamaProvider()

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            with pytest.raises(LLMError):
                await provider.complete(_make_request())


class TestOllamaProviderErrorMapping:
    async def test_connect_error_maps_to_unavailable(self):
        httpx_mod, _ = _make_httpx_mock(connect_error=True)
        provider = OllamaProvider()

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            with pytest.raises(LLMProviderUnavailableError):
                await provider.complete(_make_request())

    async def test_timeout_error_maps_to_unavailable(self):
        httpx_mod, _ = _make_httpx_mock(timeout_error=True)
        provider = OllamaProvider()

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            with pytest.raises(LLMProviderUnavailableError):
                await provider.complete(_make_request())


class TestOllamaProviderIsAvailable:
    async def test_returns_false_when_httpx_not_installed(self):
        provider = OllamaProvider()
        with patch.dict(sys.modules, {"httpx": None}):
            assert await provider.is_available() is False

    async def test_returns_true_when_tags_endpoint_responds_200(self):
        httpx_mod, _ = _make_httpx_mock(status_code=200)
        provider = OllamaProvider()

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            result = await provider.is_available()

        assert result is True

    async def test_returns_false_when_connection_fails(self):
        httpx_mod, _ = _make_httpx_mock(connect_error=True)
        provider = OllamaProvider()

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            result = await provider.is_available()

        assert result is False

    async def test_returns_false_when_non_200_status(self):
        httpx_mod, _ = _make_httpx_mock(status_code=503)
        provider = OllamaProvider()

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            result = await provider.is_available()

        assert result is False

    async def test_does_not_raise_on_any_exception(self):
        httpx_mod, _ = _make_httpx_mock()
        httpx_mod.AsyncClient = MagicMock(side_effect=RuntimeError("boom"))
        provider = OllamaProvider()

        with patch.dict(sys.modules, {"httpx": httpx_mod}):
            # Must NOT raise — just return False
            result = await provider.is_available()

        assert result is False
