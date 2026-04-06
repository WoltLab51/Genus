"""
Strategy Registry - Single Source of Truth for Playbooks

Provides a stable registry of all available playbooks with their
descriptions and recommended use cases. This is intentionally simple
and stable - changes here should be rare and deliberate.
"""

from typing import Any, Dict, List

from genus.strategy.models import PlaybookId


# ---------------------------------------------------------------------------
# Playbook Registry
# ---------------------------------------------------------------------------

PLAYBOOKS: Dict[str, Dict[str, Any]] = {
    PlaybookId.TARGET_FAILING_TEST_FIRST: {
        "description": (
            "Focus next iteration on fixing the specific failing test(s). "
            "Narrow scope to the minimal change needed to make tests pass."
        ),
        "recommended_for": [
            "test_failure",
            "assertion_error",
        ],
        "use_when": "Tests ran but some failed with clear error messages.",
    },
    PlaybookId.MINIMIZE_CHANGESET: {
        "description": (
            "Reduce the scope of changes in the next iteration. "
            "Break down the problem into smaller, incremental steps."
        ),
        "recommended_for": [
            "github_checks_failure",
            "multiple failures",
        ],
        "use_when": "Large changesets are causing cascading failures.",
    },
    PlaybookId.INCREASE_TIMEOUT_ONCE: {
        "description": (
            "Increase execution timeout and retry once. "
            "Useful when operations are timing out but may succeed with more time."
        ),
        "recommended_for": [
            "timeout",
        ],
        "use_when": "Execution timed out before completion.",
    },
    PlaybookId.ASK_OPERATOR_WITH_CONTEXT: {
        "description": (
            "Situation requires human intervention. "
            "Provide full context (logs, artifacts, decisions) to operator."
        ),
        "recommended_for": [
            "policy_blocked",
            "unknown",
            "repeated failures",
        ],
        "use_when": "Automated recovery is unlikely or risky.",
    },
    PlaybookId.DEFAULT: {
        "description": (
            "Standard approach without special constraints. "
            "Use general best practices and heuristics."
        ),
        "recommended_for": [
            "first iteration",
            "no specific failure pattern",
        ],
        "use_when": "No specific guidance from evaluation or learning.",
    },
}


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def all_playbook_ids() -> List[str]:
    """Return list of all registered playbook IDs.

    Returns:
        List of playbook identifier strings.
    """
    return list(PLAYBOOKS.keys())


def get_playbook_description(playbook_id: str) -> str:
    """Get human-readable description for a playbook.

    Args:
        playbook_id: The playbook identifier.

    Returns:
        Description string, or "Unknown playbook" if not found.
    """
    playbook = PLAYBOOKS.get(playbook_id)
    if playbook is None:
        return f"Unknown playbook: {playbook_id}"
    return playbook.get("description", "No description available")


def get_playbook_recommended_for(playbook_id: str) -> List[str]:
    """Get list of scenarios this playbook is recommended for.

    Args:
        playbook_id: The playbook identifier.

    Returns:
        List of scenario identifiers (e.g., failure classes, root causes).
    """
    playbook = PLAYBOOKS.get(playbook_id)
    if playbook is None:
        return []
    return playbook.get("recommended_for", [])


def is_playbook_recommended(playbook_id: str, scenario: str) -> bool:
    """Check if a playbook is recommended for a given scenario.

    Args:
        playbook_id: The playbook identifier.
        scenario: Scenario identifier (e.g., "test_failure", "timeout").

    Returns:
        True if the playbook is recommended for this scenario.
    """
    return scenario in get_playbook_recommended_for(playbook_id)
