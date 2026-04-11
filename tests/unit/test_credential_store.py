"""Tests for genus.llm.credential_store — CredentialStore."""

import pytest

from genus.llm.credential_store import CredentialStore
from genus.llm.exceptions import LLMCredentialMissingError


def make_store(tmp_path, prompt_fn=None):
    """Return a CredentialStore backed by tmp_path."""
    return CredentialStore(
        storage_path=tmp_path / "credentials.enc",
        key_path=tmp_path / ".credential_key",
        prompt_fn=prompt_fn,
    )


class TestCredentialStoreGet:
    def test_get_missing_returns_none(self, tmp_path):
        store = make_store(tmp_path)
        assert store.get("openai") is None

    def test_get_after_set(self, tmp_path):
        store = make_store(tmp_path)
        store.set("openai", "sk-test-123")
        assert store.get("openai") == "sk-test-123"

    def test_get_different_provider_returns_none(self, tmp_path):
        store = make_store(tmp_path)
        store.set("openai", "sk-test-123")
        assert store.get("anthropic") is None


class TestCredentialStoreSet:
    def test_set_and_reload(self, tmp_path):
        """Key survives a new CredentialStore instance (persistent)."""
        store1 = make_store(tmp_path)
        store1.set("openai", "sk-persistent")

        store2 = make_store(tmp_path)
        assert store2.get("openai") == "sk-persistent"

    def test_overwrite_key(self, tmp_path):
        store = make_store(tmp_path)
        store.set("openai", "first")
        store.set("openai", "second")
        assert store.get("openai") == "second"


class TestCredentialStoreDelete:
    def test_delete_existing(self, tmp_path):
        store = make_store(tmp_path)
        store.set("openai", "key")
        store.delete("openai")
        assert store.get("openai") is None

    def test_delete_nonexistent_no_error(self, tmp_path):
        store = make_store(tmp_path)
        store.delete("nonexistent")  # must not raise

    def test_delete_leaves_others(self, tmp_path):
        store = make_store(tmp_path)
        store.set("openai", "key-a")
        store.set("anthropic", "key-b")
        store.delete("openai")
        assert store.get("anthropic") == "key-b"


class TestCredentialStoreListProviders:
    def test_empty(self, tmp_path):
        store = make_store(tmp_path)
        assert store.list_providers() == []

    def test_multiple_providers(self, tmp_path):
        store = make_store(tmp_path)
        store.set("openai", "k1")
        store.set("anthropic", "k2")
        providers = store.list_providers()
        assert set(providers) == {"openai", "anthropic"}

    def test_after_delete(self, tmp_path):
        store = make_store(tmp_path)
        store.set("openai", "k1")
        store.set("anthropic", "k2")
        store.delete("openai")
        assert store.list_providers() == ["anthropic"]


class TestCredentialStoreGetOrAsk:
    def test_returns_existing_key(self, tmp_path):
        store = make_store(tmp_path, prompt_fn=lambda name: "should-not-be-called")
        store.set("openai", "existing-key")
        assert store.get_or_ask("openai") == "existing-key"

    def test_calls_prompt_when_missing(self, tmp_path):
        called = []

        def fake_prompt(name):
            called.append(name)
            return "prompted-key"

        store = make_store(tmp_path, prompt_fn=fake_prompt)
        result = store.get_or_ask("openai")
        assert result == "prompted-key"
        assert called == ["openai"]

    def test_saves_prompted_key(self, tmp_path):
        store = make_store(tmp_path, prompt_fn=lambda name: "saved-key")
        store.get_or_ask("openai")
        assert store.get("openai") == "saved-key"

    def test_raises_when_empty_input(self, tmp_path):
        store = make_store(tmp_path, prompt_fn=lambda name: "")
        with pytest.raises(LLMCredentialMissingError):
            store.get_or_ask("openai")

    def test_raises_when_whitespace_input(self, tmp_path):
        store = make_store(tmp_path, prompt_fn=lambda name: "   ")
        with pytest.raises(LLMCredentialMissingError):
            store.get_or_ask("openai")


class TestCredentialStoreEncryption:
    def test_file_is_not_plaintext(self, tmp_path):
        """Encrypted file must not contain the key in plaintext."""
        store = make_store(tmp_path)
        store.set("openai", "super-secret-key-xyz")
        raw = (tmp_path / "credentials.enc").read_bytes()
        assert b"super-secret-key-xyz" not in raw

    def test_env_key_used_for_encryption(self, tmp_path, monkeypatch):
        """GENUS_CREDENTIAL_KEY env var is used as encryption key."""
        from cryptography.fernet import Fernet

        fernet_key = Fernet.generate_key().decode()
        monkeypatch.setenv("GENUS_CREDENTIAL_KEY", fernet_key)

        store = CredentialStore(
            storage_path=tmp_path / "credentials.enc",
            key_path=tmp_path / ".credential_key",
        )
        store.set("openai", "env-key-test")
        assert store.get("openai") == "env-key-test"
