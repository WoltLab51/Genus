"""ProviderRegistry — auto-discovery and dynamic registration of LLM providers."""

import importlib
import inspect
import logging
import pkgutil
from typing import Dict, List, Optional

from genus.llm.providers.base import LLMProvider

logger = logging.getLogger(__name__)

# Files in providers/ that are not provider implementations
_EXCLUDED_MODULES = {"__init__", "base", "registry"}


class ProviderRegistry:
    """Manages all available LLM providers.

    Supports two registration paths:
    1. Auto-Discovery: Scans genus/llm/providers/ for LLMProvider subclasses
    2. Manual registration: register(provider) for external providers

    Usage::

        registry = ProviderRegistry()
        registry.discover()            # finds OpenAI, Ollama, Mock automatically
        registry.register(MyProvider()) # additional external provider

        provider = registry.get("openai")
        all_providers = registry.list()
    """

    def __init__(self) -> None:
        self._providers: Dict[str, LLMProvider] = {}

    def discover(self) -> None:
        """Scans genus/llm/providers/ and registers all LLMProvider subclasses.

        Imports all .py files in the providers/ directory (except __init__.py,
        base.py, registry.py) and finds all non-abstract LLMProvider subclasses.
        Each found class is automatically instantiated and registered.

        Errors when importing individual provider files are logged but not
        raised as exceptions — a broken provider does not break the overall
        discovery.
        """
        import genus.llm.providers as providers_pkg

        pkg_path = providers_pkg.__path__
        pkg_name = providers_pkg.__name__

        for module_info in pkgutil.iter_modules(pkg_path):
            module_name = module_info.name
            if module_name in _EXCLUDED_MODULES:
                continue

            full_module_name = f"{pkg_name}.{module_name}"
            try:
                module = importlib.import_module(full_module_name)
            except Exception as exc:
                logger.warning(
                    "ProviderRegistry.discover(): failed to import %s: %s",
                    full_module_name,
                    exc,
                )
                continue

            for _attr_name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    obj is LLMProvider
                    or not issubclass(obj, LLMProvider)
                    or inspect.isabstract(obj)
                ):
                    continue
                # Only register classes defined in this module (not re-imports)
                if obj.__module__ != full_module_name:
                    continue
                try:
                    instance = obj()
                    self.register(instance)
                    logger.debug(
                        "ProviderRegistry.discover(): registered %s as '%s'",
                        obj.__name__,
                        instance.name,
                    )
                except Exception as exc:
                    logger.warning(
                        "ProviderRegistry.discover(): failed to instantiate %s: %s",
                        obj.__name__,
                        exc,
                    )

    def register(self, provider: LLMProvider) -> None:
        """Registers a provider manually (overwrites existing)."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> Optional[LLMProvider]:
        """Returns the provider with the given name. None if not found."""
        return self._providers.get(name)

    def list(self) -> List[LLMProvider]:
        """Returns all registered providers."""
        return list(self._providers.values())

    def list_names(self) -> List[str]:
        """Returns all provider names."""
        return list(self._providers.keys())

    def unregister(self, name: str) -> None:
        """Removes a provider from the registry."""
        self._providers.pop(name, None)
