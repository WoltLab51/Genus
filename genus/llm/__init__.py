"""genus.llm — LLM integration foundation for GENUS agents."""

from genus.llm.client import LLMClient
from genus.llm.credential_store import CredentialStore
from genus.llm.exceptions import (
    LLMCredentialMissingError,
    LLMError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponseParseError,
)
from genus.llm.models import LLMMessage, LLMRequest, LLMResponse, LLMRole
from genus.llm.providers.base import LLMProvider, ProviderCapabilities
from genus.llm.providers.mock_provider import MockProvider
from genus.llm.providers.registry import ProviderRegistry
from genus.llm.router import LLMRouter, RoutingStrategy, TaskType

__all__ = [
    # Client
    "LLMClient",
    # Models
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMRole",
    # Providers
    "LLMProvider",
    "ProviderCapabilities",
    "MockProvider",
    "ProviderRegistry",
    # Router
    "LLMRouter",
    "RoutingStrategy",
    "TaskType",
    # Credential store
    "CredentialStore",
    # Exceptions
    "LLMError",
    "LLMProviderUnavailableError",
    "LLMCredentialMissingError",
    "LLMResponseParseError",
    "LLMRateLimitError",
]
