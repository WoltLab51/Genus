"""LLM exception hierarchy."""


class LLMError(Exception):
    """Base class for all LLM errors."""


class LLMProviderUnavailableError(LLMError):
    """Provider is not reachable (no network, service down)."""


class LLMCredentialMissingError(LLMError):
    """API key is missing and could not be obtained."""


class LLMResponseParseError(LLMError):
    """LLM response could not be parsed."""


class LLMRateLimitError(LLMError):
    """Provider rate limit reached."""
