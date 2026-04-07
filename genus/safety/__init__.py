"""
genus.safety – DEPRECATED shim.

This module has been consolidated into genus.security.sanitization.
All imports from genus.safety still work but will be removed in a future version.

Prefer:
    from genus.security.sanitization import SanitizationPolicy, sanitize_payload
"""

import warnings

warnings.warn(
    "genus.safety is deprecated. Use genus.security.sanitization instead.",
    DeprecationWarning,
    stacklevel=2,
)

from genus.security.sanitization.sanitization_policy import (  # noqa: E402, F401
    SanitizationPolicy,
    sanitize_payload,
    DEFAULT_POLICY,
)

__all__ = [
    "SanitizationPolicy",
    "sanitize_payload",
    "DEFAULT_POLICY",
]
