"""
Strategy Layer - Playbook Selection and Learning Rules (v1)

This module implements GENUS's "DNA" v1 - a meta-driven approach to
strategy selection based on evaluation artifacts, taxonomy, and learning history.

The strategy layer provides:
- Strategy Registry: Named playbooks with machine-readable descriptions
- Learning Store: Persistent preferences for strategy selection
- Strategy Selector: Deterministic strategy selection based on context
- Learning Rules: Update preferences based on outcomes

Key principles:
- No ML, no network calls - pure heuristics + persistent rules
- All decisions logged in RunJournal
- Fully deterministic and explainable
"""

from genus.strategy.models import (
    PlaybookId,
    StrategyDecision,
    StrategyProfile,
)
from genus.strategy.registry import (
    PLAYBOOKS,
    all_playbook_ids,
    get_playbook_description,
)
from genus.strategy.selector import StrategySelector
from genus.strategy.store_json import StrategyStoreJson
from genus.strategy.learning import apply_learning_rule

__all__ = [
    "PlaybookId",
    "StrategyDecision",
    "StrategyProfile",
    "PLAYBOOKS",
    "all_playbook_ids",
    "get_playbook_description",
    "StrategySelector",
    "StrategyStoreJson",
    "apply_learning_rule",
]
