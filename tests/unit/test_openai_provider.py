"""Tests for genus.llm.providers.openai_provider — OpenAIProvider."""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from genus.llm.exceptions import (
    LLMCredentialMissingError,
    LLMError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
)
from genus.llm.models import LLMMessage, LLMRequest, LLMRole
from genus.llm.providers.openai_provider import OpenAIProvider


def _make_request(content: str = "Hello") -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role=LLMRole.USER, content=content)],
        model="gpt-4o-mini",
        max_tokens=256,
        temperature=0.2,
    )


def _make_openai_mock():
    """Creates a minimal fake openai module."""
    openai_mod = types.ModuleType("openai")

    # Exceptions
    openai_mod.OpenAIError = Exception
    openai_mod.AuthenticationError = type("AuthenticationError", (Exception,), {})
    openai_mod.RateLimitError = type("RateLimitError", (Exception,), {})
    openai_mod.APIConnectionError = type("APIConnectionError", (Exception,), {})

    # AsyncOpenAI client
    mock_choice = MagicMock()
    mock_choice.message.content = "The answer."

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 20

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage = mock_usage
    mock_completion.model = "gpt-4o-mini"

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
    mock_client.models.list = AsyncMock(return_value=[])

    openai_mod.AsyncOpenAI = MagicMock(return_value=mock_client)

    return openai_mod, mock_client, mock_completion


class TestOpenAIProviderCapabilities:
    def test_name(self):
        provider = OpenAIProvider()
        assert provider.name == "openai"

    def test_capabilities_name(self):
        provider = OpenAIProvider()
        assert provider.capabilities.name == "openai"

    def test_capabilities_requires_api_key(self):
        provider = OpenAIProvider()
        assert provider.capabilities.requires_api_key is True

    def test_capabilities_not_local(self):
        provider = OpenAIProvider()
        assert provider.capabilities.local is False

    def test_capabilities_has_strengths(self):
        provider = OpenAIProvider()
        assert "code" in provider.capabilities.strengths


class TestOpenAIProviderCompleteImportError:
    async def test_raises_unavailable_when_openai_not_installed(self):
        provider = OpenAIProvider()
        with patch.dict(sys.modules, {"openai": None}):
            with pytest.raises(LLMProviderUnavailableError, match="openai package"):
                await provider.complete(_make_request())


class TestOpenAIProviderCompleteWithMock:
    async def test_returns_response_with_correct_content(self):
        openai_mod, mock_client, _ = _make_openai_mock()
        provider = OpenAIProvider()

        # Inject fake API key so no CredentialMissingError
        provider._get_api_key = lambda: "sk-test"  # type: ignore[method-assign]

        with patch.dict(sys.modules, {"openai": openai_mod}):
            response = await provider.complete(_make_request())

        assert response.content == "The answer."
        assert response.provider == "openai"
        assert response.model == "gpt-4o-mini"

    async def test_messages_formatted_correctly(self):
        openai_mod, mock_client, _ = _make_openai_mock()
        provider = OpenAIProvider()
        provider._get_api_key = lambda: "sk-test"  # type: ignore[method-assign]

        request = LLMRequest(
            messages=[
                LLMMessage(role=LLMRole.SYSTEM, content="You are helpful."),
                LLMMessage(role=LLMRole.USER, content="Do the thing."),
            ],
            model="gpt-4o-mini",
        )

        with patch.dict(sys.modules, {"openai": openai_mod}):
            await provider.complete(request)

        _call = mock_client.chat.completions.create.call_args
        sent_messages = _call.kwargs.get("messages") or _call.args[0] if _call.args else _call.kwargs["messages"]
        assert sent_messages[0] == {"role": "system", "content": "You are helpful."}
        assert sent_messages[1] == {"role": "user", "content": "Do the thing."}

    async def test_token_counts_filled(self):
        openai_mod, _, _ = _make_openai_mock()
        provider = OpenAIProvider()
        provider._get_api_key = lambda: "sk-test"  # type: ignore[method-assign]

        with patch.dict(sys.modules, {"openai": openai_mod}):
            response = await provider.complete(_make_request())

        assert response.prompt_tokens == 10
        assert response.completion_tokens == 20

    async def test_no_api_key_raises_credential_missing(self):
        openai_mod, _, _ = _make_openai_mock()
        provider = OpenAIProvider()  # no credential_store → key is None

        with patch.dict(sys.modules, {"openai": openai_mod}):
            with pytest.raises(LLMCredentialMissingError):
                await provider.complete(_make_request())


class TestOpenAIProviderErrorMapping:
    async def _complete_with_error(self, exc_type_name: str, exc_instance):
        openai_mod, mock_client, _ = _make_openai_mock()
        setattr(openai_mod, exc_type_name, type(exc_type_name, (Exception,), {}))
        exc = type(exc_type_name, (Exception,), {})()
        mock_client.chat.completions.create = AsyncMock(side_effect=exc)
        # Also patch the actual exception classes on the module
        openai_mod.AuthenticationError = type("AuthenticationError", (Exception,), {})
        openai_mod.RateLimitError = type("RateLimitError", (Exception,), {})
        openai_mod.APIConnectionError = type("APIConnectionError", (Exception,), {})
        openai_mod.OpenAIError = Exception

        return openai_mod, mock_client

    async def test_authentication_error_maps_to_credential_missing(self):
        openai_mod, mock_client, _ = _make_openai_mock()
        auth_exc_class = type("AuthenticationError", (Exception,), {})
        openai_mod.AuthenticationError = auth_exc_class
        mock_client.chat.completions.create = AsyncMock(
            side_effect=auth_exc_class("bad key")
        )
        provider = OpenAIProvider()
        provider._get_api_key = lambda: "sk-test"  # type: ignore[method-assign]

        with patch.dict(sys.modules, {"openai": openai_mod}):
            with pytest.raises(LLMCredentialMissingError):
                await provider.complete(_make_request())

    async def test_rate_limit_error_maps_to_rate_limit(self):
        openai_mod, mock_client, _ = _make_openai_mock()
        rate_exc_class = type("RateLimitError", (Exception,), {})
        openai_mod.RateLimitError = rate_exc_class
        mock_client.chat.completions.create = AsyncMock(
            side_effect=rate_exc_class("rate limit")
        )
        provider = OpenAIProvider()
        provider._get_api_key = lambda: "sk-test"  # type: ignore[method-assign]

        with patch.dict(sys.modules, {"openai": openai_mod}):
            with pytest.raises(LLMRateLimitError):
                await provider.complete(_make_request())

    async def test_connection_error_maps_to_unavailable(self):
        openai_mod, mock_client, _ = _make_openai_mock()
        conn_exc_class = type("APIConnectionError", (Exception,), {})
        openai_mod.APIConnectionError = conn_exc_class
        mock_client.chat.completions.create = AsyncMock(
            side_effect=conn_exc_class("no internet")
        )
        provider = OpenAIProvider()
        provider._get_api_key = lambda: "sk-test"  # type: ignore[method-assign]

        with patch.dict(sys.modules, {"openai": openai_mod}):
            with pytest.raises(LLMProviderUnavailableError):
                await provider.complete(_make_request())

    async def test_generic_openai_error_maps_to_llm_error(self):
        openai_mod, mock_client, _ = _make_openai_mock()
        generic_exc = Exception("something broke")
        openai_mod.OpenAIError = Exception
        mock_client.chat.completions.create = AsyncMock(side_effect=generic_exc)
        provider = OpenAIProvider()
        provider._get_api_key = lambda: "sk-test"  # type: ignore[method-assign]

        with patch.dict(sys.modules, {"openai": openai_mod}):
            with pytest.raises(LLMError):
                await provider.complete(_make_request())


class TestOpenAIProviderIsAvailable:
    async def test_returns_false_when_openai_not_installed(self):
        provider = OpenAIProvider()
        with patch.dict(sys.modules, {"openai": None}):
            assert await provider.is_available() is False

    async def test_returns_false_when_no_api_key(self):
        provider = OpenAIProvider()  # no credential_store
        assert await provider.is_available() is False

    async def test_returns_true_when_models_list_succeeds(self):
        openai_mod, mock_client, _ = _make_openai_mock()
        provider = OpenAIProvider()
        provider._get_api_key = lambda: "sk-test"  # type: ignore[method-assign]

        with patch.dict(sys.modules, {"openai": openai_mod}):
            result = await provider.is_available()

        assert result is True

    async def test_returns_false_when_models_list_raises(self):
        openai_mod, mock_client, _ = _make_openai_mock()
        mock_client.models.list = AsyncMock(side_effect=Exception("boom"))
        provider = OpenAIProvider()
        provider._get_api_key = lambda: "sk-test"  # type: ignore[method-assign]

        with patch.dict(sys.modules, {"openai": openai_mod}):
            result = await provider.is_available()

        assert result is False
