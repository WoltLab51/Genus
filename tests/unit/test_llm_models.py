"""Tests for genus.llm.models — LLMRequest, LLMResponse, LLMRole."""

import pytest

from genus.llm.models import LLMMessage, LLMRequest, LLMResponse, LLMRole


class TestLLMRole:
    def test_enum_values(self):
        assert LLMRole.SYSTEM == "system"
        assert LLMRole.USER == "user"
        assert LLMRole.ASSISTANT == "assistant"

    def test_enum_is_str(self):
        assert isinstance(LLMRole.USER, str)


class TestLLMMessage:
    def test_fields(self):
        msg = LLMMessage(role=LLMRole.USER, content="Hello")
        assert msg.role == LLMRole.USER
        assert msg.content == "Hello"


class TestLLMRequest:
    def test_defaults(self):
        req = LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content="hi")])
        assert req.model is None
        assert req.max_tokens == 2048
        assert req.temperature == 0.2
        assert req.metadata == {}

    def test_custom_values(self):
        msg = LLMMessage(role=LLMRole.SYSTEM, content="You are helpful.")
        req = LLMRequest(
            messages=[msg],
            model="gpt-4",
            max_tokens=512,
            temperature=0.7,
            metadata={"run_id": "abc"},
        )
        assert req.model == "gpt-4"
        assert req.max_tokens == 512
        assert req.temperature == 0.7
        assert req.metadata == {"run_id": "abc"}

    def test_metadata_is_independent(self):
        req1 = LLMRequest(messages=[])
        req2 = LLMRequest(messages=[])
        req1.metadata["key"] = "value"
        assert "key" not in req2.metadata


class TestLLMResponse:
    def test_total_tokens(self):
        resp = LLMResponse(
            content="answer",
            model="mock",
            provider="mock",
            prompt_tokens=10,
            completion_tokens=5,
        )
        assert resp.total_tokens == 15

    def test_total_tokens_zero(self):
        resp = LLMResponse(content="x", model="m", provider="p")
        assert resp.total_tokens == 0

    def test_defaults(self):
        resp = LLMResponse(content="hi", model="m", provider="p")
        assert resp.prompt_tokens == 0
        assert resp.completion_tokens == 0
        assert resp.latency_ms == 0.0
        assert resp.metadata == {}

    def test_metadata_is_independent(self):
        resp1 = LLMResponse(content="a", model="m", provider="p")
        resp2 = LLMResponse(content="b", model="m", provider="p")
        resp1.metadata["x"] = 1
        assert "x" not in resp2.metadata
