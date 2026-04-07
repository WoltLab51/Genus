"""
genus.security.sanitization – Input sanitization and payload guardrails.

Ensures only allow-listed, size-limited data passes through GENUS boundaries.
"""

from genus.security.sanitization.sanitization_policy import (
    SanitizationPolicy,
    sanitize_payload,
    DEFAULT_POLICY,
)

__all__ = [
    "SanitizationPolicy",
    "sanitize_payload",
    "DEFAULT_POLICY",
]
