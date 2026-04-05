"""
Sanitization Policy – P1-C1

Provides a deterministic, fail-closed sanitization layer that transforms an
arbitrary payload dict into a small, auditable ``data`` dict plus an
``evidence`` record describing every modification made.

Design principles
-----------------
- **Whitelist-first**: only explicitly allowed top-level keys pass through.
- **Fail-closed**: unknown top-level keys are silently removed and listed in
  ``evidence["removed_fields"]``.
- **No IO / no network / no LLM**: pure, side-effect-free computation.
- **Deterministic**: same input always yields the same output.
- **Extensible**: replace the default policy with a source-specific one at
  call time; no code changes required.

Public API
----------
- :class:`SanitizationPolicy` – dataclass describing the sanitization rules.
- :func:`sanitize_payload`    – pure function; transforms a payload and
                                returns ``(sanitized_data, evidence)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# SanitizationPolicy
# ---------------------------------------------------------------------------

@dataclass
class SanitizationPolicy:
    """Rules that govern how a raw payload is sanitized.

    Attributes:
        policy_id:          Human-readable identifier for this policy.
        policy_version:     Semver-style version string for audit trails.
        allowed_keys:       Allowlist of top-level keys that may appear in
                            the sanitized output.  Keys absent from this list
                            are removed and logged in evidence.
        max_str_len:        Maximum length of any string value; longer values
                            are truncated to this length.
        max_list_len:       Maximum number of elements in any list value;
                            longer lists are truncated.
        max_keys_per_level: Maximum number of keys per dict at any nesting
                            level; excess keys are removed.
        max_depth:          Maximum nesting depth; sub-structures beyond this
                            depth are replaced with ``None``.
    """

    policy_id: str = "default"
    policy_version: str = "p1-c1"
    allowed_keys: List[str] = field(
        default_factory=lambda: [
            "source",
            "timestamp",
            "type",
            "event_type",
            "metrics",
        ]
    )
    max_str_len: int = 256
    max_list_len: int = 50
    max_keys_per_level: int = 50
    max_depth: int = 5


# ---------------------------------------------------------------------------
# Default policy singleton (module-level; immutable via frozen=False but
# callers should treat it as read-only)
# ---------------------------------------------------------------------------

DEFAULT_POLICY = SanitizationPolicy()


# ---------------------------------------------------------------------------
# sanitize_payload
# ---------------------------------------------------------------------------

def sanitize_payload(
    payload: Any,
    policy: Optional[SanitizationPolicy] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Sanitize *payload* according to *policy* and return ``(data, evidence)``.

    Args:
        payload: The raw input to sanitize.  Expected to be a ``dict``; any
                 other type results in an empty ``data`` dict and
                 ``blocked_by_policy=True`` in evidence.
        policy:  The :class:`SanitizationPolicy` to apply.  Defaults to
                 :data:`DEFAULT_POLICY`.

    Returns:
        A ``(data, evidence)`` tuple where

        * ``data``     – sanitized, whitelisted, size-limited ``dict``.
        * ``evidence`` – audit record with keys:

          - ``policy_id``        (str)
          - ``policy_version``   (str)
          - ``removed_fields``   (list[str]) – JSON-path-style field names
            that were removed because they were not in the allowlist.
          - ``truncated_fields`` (list[str]) – JSON-path-style field names
            whose values were truncated due to size limits.
          - ``blocked_by_policy`` (bool) – ``True`` when the entire payload
            was rejected (e.g. input was not a dict).
    """
    if policy is None:
        policy = DEFAULT_POLICY

    removed_fields: List[str] = []
    truncated_fields: List[str] = []

    # Non-dict input: fail closed
    if not isinstance(payload, dict):
        evidence = _build_evidence(
            policy, removed_fields, truncated_fields, blocked_by_policy=True
        )
        return {}, evidence

    # Step 1: enforce top-level allowlist
    sanitized: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in policy.allowed_keys:
            sanitized[key] = value
        else:
            removed_fields.append(key)

    # Step 2: recursively enforce size/depth limits starting at depth=1
    sanitized = _enforce_limits(sanitized, policy, removed_fields, truncated_fields, depth=1)

    blocked = len(sanitized) == 0 and len(removed_fields) > 0
    evidence = _build_evidence(policy, removed_fields, truncated_fields, blocked_by_policy=blocked)
    return sanitized, evidence


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enforce_limits(
    obj: Any,
    policy: SanitizationPolicy,
    removed_fields: List[str],
    truncated_fields: List[str],
    depth: int,
    path: str = "",
) -> Any:
    """Recursively apply depth/size limits to *obj*."""

    if depth > policy.max_depth:
        # Replaced with None; record as removed
        if path:
            removed_fields.append(path)
        return None

    if isinstance(obj, dict):
        limited: Dict[str, Any] = {}
        for i, (k, v) in enumerate(obj.items()):
            if i >= policy.max_keys_per_level:
                child_path = f"{path}.{k}" if path else k
                removed_fields.append(child_path)
                continue
            child_path = f"{path}.{k}" if path else k
            limited[k] = _enforce_limits(v, policy, removed_fields, truncated_fields, depth + 1, child_path)
        return limited

    if isinstance(obj, list):
        result = []
        truncated = False
        for i, item in enumerate(obj):
            if i >= policy.max_list_len:
                truncated = True
                break
            child_path = f"{path}[{i}]"
            result.append(_enforce_limits(item, policy, removed_fields, truncated_fields, depth + 1, child_path))
        if truncated and path:
            truncated_fields.append(path)
        return result

    if isinstance(obj, str):
        if len(obj) > policy.max_str_len:
            if path:
                truncated_fields.append(path)
            return obj[: policy.max_str_len]

    return obj


def _build_evidence(
    policy: SanitizationPolicy,
    removed_fields: List[str],
    truncated_fields: List[str],
    blocked_by_policy: bool,
) -> Dict[str, Any]:
    return {
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "removed_fields": list(removed_fields),
        "truncated_fields": list(truncated_fields),
        "blocked_by_policy": blocked_by_policy,
    }
