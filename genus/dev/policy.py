"""
DevLoop Ask/Stop Policy

Deterministic, stateless policy that decides whether GENUS must pause and
ask the human operator before continuing the dev loop.

Rules (in priority order):
1. Ask if ``security_impact`` is True.
2. Ask if ``scope_change`` is True.
3. Ask if any finding has ``severity`` >= ``"high"`` (i.e. "high" or "critical").
4. Otherwise do not ask.

No LLM calls, no IO, no side effects.
"""

from typing import List, Tuple

# Severity levels ordered from lowest to highest.
_SEVERITY_ORDER = ("none", "info", "low", "medium", "high", "critical")
_HIGH_THRESHOLD = "high"


def _severity_rank(severity: str) -> int:
    """Return the numeric rank of *severity* (case-insensitive).

    Unknown severities rank below ``"none"`` (returns -1) so they never
    trigger the high-severity rule.
    """
    try:
        return _SEVERITY_ORDER.index(severity.lower())
    except ValueError:
        return -1


def should_ask_user(
    findings: List[dict],
    risks: List[dict],
    scope_change: bool,
    security_impact: bool,
) -> Tuple[bool, str]:
    """Decide whether the dev loop must pause and ask the human operator.

    Args:
        findings:        List of review/test findings.  Each finding is a
                         dict and may contain a ``"severity"`` key (str).
        risks:           List of identified risk dicts.  **Currently unused** –
                         reserved for future rules (e.g. risk-severity
                         threshold).  Pass an empty list if not applicable.
        scope_change:    True if the iteration would change the agreed scope.
        security_impact: True if the iteration has a security-relevant effect.

    Returns:
        A ``(ask, reason)`` tuple where ``ask`` is ``True`` when the operator
        must be consulted and ``reason`` is a human-readable explanation.
        When ``ask`` is ``False``, ``reason`` is an empty string.
    """
    if security_impact:
        return True, "Security impact detected – operator confirmation required."

    if scope_change:
        return True, "Scope change detected – operator confirmation required."

    high_rank = _severity_rank(_HIGH_THRESHOLD)
    for finding in findings:
        sev = finding.get("severity", "")
        if isinstance(sev, str) and _severity_rank(sev) >= high_rank:
            return True, (
                f"Finding with severity {sev!r} requires operator review."
            )

    return False, ""
