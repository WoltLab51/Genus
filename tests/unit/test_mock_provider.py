"""Tests for genus.llm.providers.mock_provider — MockProvider."""

import pytest

from genus.llm.exceptions import LLMProviderUnavailableError
from genus.llm.models import LLMMessage, LLMRequest, LLMRole
from genus.llm.providers.mock_provider import MockProvider


def _request(text: str = "hello") -> LLMRequest:
    return LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content=text)])


class TestMockProviderName:
    def test_name(self):
        assert MockProvider().name == "mock"


class TestMockProviderCapabilities:
    def test_capabilities(self):
        caps = MockProvider().capabilities
        assert caps.name == "mock"
        assert caps.local is True
        assert caps.cost_per_1k_tokens == 0.0
        assert caps.requires_api_key is False


class TestMockProviderAvailability:
    async def test_available_true(self):
        assert await MockProvider(available=True).is_available() is True

    async def test_available_false(self):
        assert await MockProvider(available=False).is_available() is False


class TestMockProviderResponses:
    async def test_default_response(self):
        provider = MockProvider()
        resp = await provider.complete(_request())
        assert resp.content == "Mock response."
        assert resp.provider == "mock"

    async def test_custom_single_response(self):
        provider = MockProvider(responses=["Custom answer."])
        resp = await provider.complete(_request())
        assert resp.content == "Custom answer."

    async def test_response_rotation(self):
        provider = MockProvider(responses=["first", "second", "third"])
        r1 = await provider.complete(_request())
        r2 = await provider.complete(_request())
        r3 = await provider.complete(_request())
        assert r1.content == "first"
        assert r2.content == "second"
        assert r3.content == "third"

    async def test_last_response_repeated(self):
        provider = MockProvider(responses=["only"])
        await provider.complete(_request())
        r2 = await provider.complete(_request())
        r3 = await provider.complete(_request())
        assert r2.content == "only"
        assert r3.content == "only"

    async def test_response_list_exhausted_repeats_last(self):
        provider = MockProvider(responses=["a", "b"])
        await provider.complete(_request())  # a
        await provider.complete(_request())  # b
        r3 = await provider.complete(_request())  # b again
        assert r3.content == "b"

    async def test_model_from_request(self):
        provider = MockProvider()
        req = LLMRequest(
            messages=[LLMMessage(role=LLMRole.USER, content="hi")],
            model="gpt-4",
        )
        resp = await provider.complete(req)
        assert resp.model == "gpt-4"

    async def test_model_default_when_none(self):
        provider = MockProvider()
        resp = await provider.complete(_request())
        assert resp.model == "mock-model"


class TestMockProviderFailAfter:
    async def test_fail_after_raises(self):
        provider = MockProvider(fail_after=2)
        await provider.complete(_request())
        await provider.complete(_request())
        with pytest.raises(LLMProviderUnavailableError):
            await provider.complete(_request())

    async def test_fail_after_none_never_fails(self):
        provider = MockProvider(fail_after=None)
        for _ in range(10):
            resp = await provider.complete(_request())
        assert resp.content == "Mock response."

    async def test_fail_after_zero_fails_immediately(self):
        provider = MockProvider(fail_after=0)
        with pytest.raises(LLMProviderUnavailableError):
            await provider.complete(_request())


class TestMockProviderLatency:
    async def test_latency_recorded_in_response(self):
        provider = MockProvider(latency_ms=10.0)
        resp = await provider.complete(_request())
        assert resp.latency_ms == 10.0

    async def test_zero_latency(self):
        provider = MockProvider(latency_ms=0.0)
        resp = await provider.complete(_request())
        assert resp.latency_ms == 0.0
