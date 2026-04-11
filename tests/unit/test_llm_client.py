"""Tests for genus.llm.client — LLMClient."""

import pytest

from genus.llm.client import LLMClient
from genus.llm.exceptions import LLMProviderUnavailableError
from genus.llm.models import LLMMessage, LLMResponse, LLMRole
from genus.llm.providers.mock_provider import MockProvider


def _user(text: str) -> LLMMessage:
    return LLMMessage(role=LLMRole.USER, content=text)


class TestLLMClientComplete:
    async def test_delegates_to_provider(self):
        provider = MockProvider(responses=["The answer."])
        client = LLMClient(provider=provider)
        resp = await client.complete(messages=[_user("question")])
        assert isinstance(resp, LLMResponse)
        assert resp.content == "The answer."

    async def test_response_fields_filled(self):
        provider = MockProvider(responses=["42"])
        client = LLMClient(provider=provider)
        resp = await client.complete(messages=[_user("what?")])
        assert resp.provider == "mock"
        assert resp.model is not None

    async def test_model_passed_to_provider(self):
        provider = MockProvider()
        client = LLMClient(provider=provider)
        resp = await client.complete(messages=[_user("hi")], model="gpt-4")
        assert resp.model == "gpt-4"

    async def test_metadata_default_empty(self):
        provider = MockProvider()
        client = LLMClient(provider=provider)
        resp = await client.complete(messages=[_user("hi")])
        assert isinstance(resp, LLMResponse)

    async def test_metadata_passed_through(self):
        provider = MockProvider()
        client = LLMClient(provider=provider)
        resp = await client.complete(
            messages=[_user("hi")],
            metadata={"run_id": "r-1"},
        )
        assert isinstance(resp, LLMResponse)

    async def test_provider_error_propagates(self):
        provider = MockProvider(fail_after=0)
        client = LLMClient(provider=provider)
        with pytest.raises(LLMProviderUnavailableError):
            await client.complete(messages=[_user("hi")])

    async def test_multiple_messages(self):
        provider = MockProvider(responses=["done"])
        client = LLMClient(provider=provider)
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content="You are helpful."),
            LLMMessage(role=LLMRole.USER, content="Do the thing."),
        ]
        resp = await client.complete(messages=messages)
        assert resp.content == "done"


class TestLLMClientIsAvailable:
    async def test_available_delegates(self):
        client = LLMClient(provider=MockProvider(available=True))
        assert await client.is_available() is True

    async def test_unavailable_delegates(self):
        client = LLMClient(provider=MockProvider(available=False))
        assert await client.is_available() is False


class TestLLMClientWithCredentialStore:
    async def test_accepts_credential_store(self, tmp_path):
        from genus.llm.credential_store import CredentialStore

        store = CredentialStore(
            storage_path=tmp_path / "creds.enc",
            key_path=tmp_path / ".key",
        )
        client = LLMClient(provider=MockProvider(), credential_store=store)
        resp = await client.complete(messages=[_user("hi")])
        assert resp.content == "Mock response."
