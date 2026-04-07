"""
Strategy Store - Persistent Storage for Learning Rules (v1)

Implements JSON-based storage for strategy preferences and learning history.
This is kept simple and file-based for v1 - no databases, no complexity.

Storage Layout
--------------
<base_dir>/
    strategy_store.json  - Main preferences and learning data

File Format
-----------
{
    "version": 1,
    "profiles": {
        "default": {
            "name": "default",
            "playbook_weights": {"playbook_id": weight, ...}
        }
    },
    "failure_class_weights": {
        "test_failure": {
            "target_failing_test_first": 3,
            "minimize_changeset": 1
        },
        "timeout": {
            "increase_timeout_once": 2
        }
    },
    "learning_history": [
        {
            "run_id": "...",
            "failure_class": "...",
            "root_cause_hint": "...",
            "selected_playbook": "...",
            "outcome_score": 75,
            "learned_at": "2026-04-06T19:00:00Z"
        }
    ]
}

Environment Variables
---------------------
GENUS_STRATEGY_STORE_DIR: Override the default base directory (var/strategy/)
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from genus.strategy.models import StrategyProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_BASE_DIR = "var/strategy"
_ENV_VAR = "GENUS_STRATEGY_STORE_DIR"
_STORE_FILENAME = "strategy_store.json"


# ---------------------------------------------------------------------------
# StrategyStoreJson
# ---------------------------------------------------------------------------

class StrategyStoreJson:
    """JSON-based storage for strategy preferences and learning history.

    Manages a single JSON file containing:
    - profiles: Named strategy profiles with playbook weights
    - learning_history: Record of past decisions and outcomes

    Args:
        base_dir: Optional explicit path to the strategy storage directory.
                  Defaults to GENUS_STRATEGY_STORE_DIR env var or var/strategy/.
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = Path(
            base_dir
            or os.environ.get(_ENV_VAR)
            or _DEFAULT_BASE_DIR
        )
        self._store_path = self._base_dir / _STORE_FILENAME
        self._lock = threading.Lock()
        self._ensure_base_dir()

    # ------------------------------------------------------------------
    # Directory management
    # ------------------------------------------------------------------

    def _ensure_base_dir(self) -> None:
        """Ensure base directory exists."""
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Load/Save
    # ------------------------------------------------------------------

    def _load_store(self) -> Dict[str, Any]:
        """Load the entire store from disk.

        Returns:
            Dict with "version", "profiles", "failure_class_weights", and "learning_history" keys.
            Returns empty structure if file doesn't exist.
        """
        if not self._store_path.exists():
            return {
                "version": 1,
                "profiles": {},
                "failure_class_weights": {},
                "learning_history": []
            }

        try:
            with open(self._store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure required keys exist
                if "version" not in data:
                    data["version"] = 1
                if "profiles" not in data:
                    data["profiles"] = {}
                if "failure_class_weights" not in data:
                    data["failure_class_weights"] = {}
                if "learning_history" not in data:
                    data["learning_history"] = []
                return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to load strategy store from %s: %s",
                self._store_path, exc
            )
            return {
                "version": 1,
                "profiles": {},
                "failure_class_weights": {},
                "learning_history": []
            }

    def _save_store(self, data: Dict[str, Any]) -> None:
        """Save the entire store to disk.

        Args:
            data: Dict with "profiles" and "learning_history" keys.
        """
        try:
            # Write atomically via temp file
            temp_path = self._store_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(self._store_path)
            logger.debug("Saved strategy store to %s", self._store_path)
        except OSError as exc:
            logger.error(
                "Failed to save strategy store to %s: %s",
                self._store_path, exc
            )

    # ------------------------------------------------------------------
    # Profile operations
    # ------------------------------------------------------------------

    def get_profile(self, name: str) -> Optional[StrategyProfile]:
        """Load a strategy profile by name.

        Args:
            name: Profile name (e.g., "default").

        Returns:
            StrategyProfile if found, None otherwise.
        """
        data = self._load_store()
        profile_data = data["profiles"].get(name)
        if profile_data is None:
            return None
        return StrategyProfile.from_dict(profile_data)

    def save_profile(self, profile: StrategyProfile) -> None:
        """Save a strategy profile.

        Args:
            profile: The profile to save.
        """
        with self._lock:
            data = self._load_store()
            data["profiles"][profile.name] = profile.to_dict()
            self._save_store(data)

    def list_profiles(self) -> List[str]:
        """List all profile names.

        Returns:
            List of profile name strings.
        """
        data = self._load_store()
        return list(data["profiles"].keys())

    # ------------------------------------------------------------------
    # Learning history operations
    # ------------------------------------------------------------------

    def add_learning_entry(
        self,
        run_id: str,
        failure_class: Optional[str],
        root_cause_hint: Optional[str],
        selected_playbook: str,
        outcome_score: int,
    ) -> None:
        """Add a learning history entry.

        Args:
            run_id: The run identifier.
            failure_class: Failure classification (if any).
            root_cause_hint: Root cause hint (if any).
            selected_playbook: The playbook that was used.
            outcome_score: The final score/outcome (0-100).
        """
        with self._lock:
            data = self._load_store()
            entry = {
                "run_id": run_id,
                "failure_class": failure_class,
                "root_cause_hint": root_cause_hint,
                "selected_playbook": selected_playbook,
                "outcome_score": outcome_score,
                "learned_at": datetime.now(timezone.utc).isoformat(),
            }
            data["learning_history"].append(entry)
            self._save_store(data)
        logger.info(
            "Added learning entry for run_id=%s, playbook=%s, score=%d",
            run_id, selected_playbook, outcome_score
        )

    def get_learning_history(
        self,
        failure_class: Optional[str] = None,
        root_cause_hint: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query learning history with optional filters.

        Args:
            failure_class: Filter by failure class (optional).
            root_cause_hint: Filter by root cause hint (optional).
            limit: Maximum number of entries to return (most recent first).

        Returns:
            List of learning history entries (dicts).
        """
        data = self._load_store()
        entries = data["learning_history"]

        # Apply filters
        if failure_class is not None:
            entries = [e for e in entries if e.get("failure_class") == failure_class]
        if root_cause_hint is not None:
            entries = [e for e in entries if e.get("root_cause_hint") == root_cause_hint]

        # Return most recent first
        entries = list(reversed(entries))

        if limit is not None:
            entries = entries[:limit]

        return entries

    def clear_learning_history(self) -> None:
        """Clear all learning history (keep profiles intact).

        Useful for testing or reset scenarios.
        """
        with self._lock:
            data = self._load_store()
            data["learning_history"] = []
            self._save_store(data)
        logger.info("Cleared learning history")

    # ------------------------------------------------------------------
    # Failure class weights operations
    # ------------------------------------------------------------------

    def get_failure_class_weight(
        self,
        failure_class: str,
        playbook_id: str,
    ) -> int:
        """Get weight for a specific playbook in a failure class context.

        Args:
            failure_class: The failure classification (e.g., "test_failure").
            playbook_id: The playbook identifier.

        Returns:
            The weight for this playbook in this failure class (default 0).
        """
        data = self._load_store()
        failure_weights = data.get("failure_class_weights", {})
        class_weights = failure_weights.get(failure_class, {})
        return class_weights.get(playbook_id, 0)

    def set_failure_class_weight(
        self,
        failure_class: str,
        playbook_id: str,
        weight: int,
    ) -> None:
        """Set weight for a specific playbook in a failure class context.

        Args:
            failure_class: The failure classification (e.g., "test_failure").
            playbook_id: The playbook identifier.
            weight: The weight to set (integer, typically -20 to +20).
        """
        with self._lock:
            data = self._load_store()

            if "failure_class_weights" not in data:
                data["failure_class_weights"] = {}

            if failure_class not in data["failure_class_weights"]:
                data["failure_class_weights"][failure_class] = {}

            data["failure_class_weights"][failure_class][playbook_id] = weight
            self._save_store(data)

        logger.debug(
            "Set failure_class_weight: %s / %s = %d",
            failure_class, playbook_id, weight
        )

    def get_all_failure_class_weights(
        self,
        failure_class: str,
    ) -> Dict[str, int]:
        """Get all playbook weights for a specific failure class.

        Args:
            failure_class: The failure classification.

        Returns:
            Dict mapping playbook_id to weight for this failure class.
            Returns empty dict if no weights exist for this failure class.
        """
        data = self._load_store()
        failure_weights = data.get("failure_class_weights", {})
        return dict(failure_weights.get(failure_class, {}))

    def clear_failure_class_weights(self) -> None:
        """Clear all failure_class_weights.

        Useful for testing or reset scenarios.
        """
        with self._lock:
            data = self._load_store()
            data["failure_class_weights"] = {}
            self._save_store(data)
        logger.info("Cleared all failure_class_weights")
