"""Tests for genus.llm.providers.registry — ProviderRegistry."""

import pytest

from genus.llm.providers.mock_provider import MockProvider
from genus.llm.providers.registry import ProviderRegistry


class TestProviderRegistryBasicOps:
    def test_register_and_get(self):
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)
        assert registry.get("mock") is provider

    def test_get_returns_none_for_unknown(self):
        registry = ProviderRegistry()
        assert registry.get("nonexistent") is None

    def test_list_returns_all_registered(self):
        registry = ProviderRegistry()
        p1 = MockProvider()
        registry.register(p1)
        providers = registry.list()
        assert len(providers) == 1
        assert p1 in providers

    def test_list_names(self):
        registry = ProviderRegistry()
        registry.register(MockProvider())
        assert "mock" in registry.list_names()

    def test_unregister_removes_provider(self):
        registry = ProviderRegistry()
        registry.register(MockProvider())
        registry.unregister("mock")
        assert registry.get("mock") is None

    def test_unregister_nonexistent_does_not_raise(self):
        registry = ProviderRegistry()
        registry.unregister("never_existed")  # should not raise

    def test_register_overwrites_existing(self):
        registry = ProviderRegistry()
        p1 = MockProvider(responses=["first"])
        p2 = MockProvider(responses=["second"])
        registry.register(p1)
        registry.register(p2)
        assert registry.get("mock") is p2

    def test_usable_without_discover(self):
        registry = ProviderRegistry()
        registry.register(MockProvider())
        assert registry.get("mock") is not None

    def test_empty_registry_list(self):
        registry = ProviderRegistry()
        assert registry.list() == []
        assert registry.list_names() == []


class TestProviderRegistryDiscover:
    def test_discover_finds_mock_provider(self):
        registry = ProviderRegistry()
        registry.discover()
        assert registry.get("mock") is not None

    def test_discover_finds_openai_provider(self):
        registry = ProviderRegistry()
        registry.discover()
        assert registry.get("openai") is not None

    def test_discover_finds_ollama_provider(self):
        registry = ProviderRegistry()
        registry.discover()
        assert registry.get("ollama") is not None

    def test_discover_does_not_raise_on_broken_import(self, monkeypatch):
        """A broken provider import must not crash the whole discovery."""
        import genus.llm.providers as providers_pkg
        import pkgutil

        original_iter = pkgutil.iter_modules

        class _FakeModuleInfo:
            name = "broken_fake_module"
            ispkg = False

        def _patched_iter(path):
            yield _FakeModuleInfo()
            yield from original_iter(path)

        monkeypatch.setattr(pkgutil, "iter_modules", _patched_iter)

        # Should not raise even though broken_fake_module doesn't exist
        registry = ProviderRegistry()
        registry.discover()
        # mock, openai, ollama should still be discovered
        assert registry.get("mock") is not None

    def test_discover_idempotent(self):
        registry = ProviderRegistry()
        registry.discover()
        count_after_first = len(registry.list())
        registry.discover()
        count_after_second = len(registry.list())
        assert count_after_first == count_after_second

    def test_manual_register_after_discover(self):
        from genus.llm.providers.mock_provider import MockProvider as _Mock

        class CustomProvider(_Mock):
            _name = "custom"

        registry = ProviderRegistry()
        registry.discover()
        registry.register(CustomProvider())
        assert registry.get("custom") is not None
