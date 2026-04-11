"""LLMRouter — adaptive provider selection for GENUS agents."""

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from genus.llm.exceptions import LLMProviderUnavailableError
from genus.llm.models import LLMMessage, LLMRequest, LLMResponse
from genus.llm.providers.base import LLMProvider
from genus.llm.providers.registry import ProviderRegistry

_DEFAULT_SCORES_PATH = Path.home() / ".genus" / "router_scores.jsonl"
_MAX_SCORES = 1000


class TaskType(str, Enum):
    """Categorisation of LLM tasks for intelligent routing."""

    PLANNING = "planning"
    CODE_GEN = "code_gen"
    CODE_REVIEW = "code_review"
    REASONING = "reasoning"
    SUMMARIZE = "summarize"
    GENERAL = "general"


class RoutingStrategy(str, Enum):
    """Routing strategy for provider selection."""

    QUALITY = "quality"
    COST = "cost"
    LOCAL = "local"
    ADAPTIVE = "adaptive"


class LLMRouter:
    """Intelligent LLM dispatcher.

    Automatically selects the best provider for a task based on
    availability, task type, experience scores, and a configurable strategy.

    GENUS learns over time which provider works best for which task_type.
    This experience is stored as RouterScores in a JSONL file (no external
    service required).

    Args:
        registry:       ProviderRegistry with all available providers.
        strategy:       RoutingStrategy. Default: ADAPTIVE.
        scores_path:    Path to the JSONL file with stored router scores.
                        Default: ~/.genus/router_scores.jsonl
        fallback_order: Order of fallback providers when the primary provider
                        is unavailable. Default: ["ollama", "mock"]

    Usage::

        router = LLMRouter(registry=registry)

        # Simple: router chooses on its own
        response = await router.complete(
            messages=[LLMMessage(role=LLMRole.USER, content="Plan this task")],
            task_type=TaskType.PLANNING,
        )

        # With feedback: router learns
        await router.record_score(
            provider_name="ollama",
            task_type=TaskType.PLANNING,
            score=0.85,
            run_id="run-001",
        )
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        strategy: RoutingStrategy = RoutingStrategy.ADAPTIVE,
        scores_path: Optional[Path] = None,
        fallback_order: Optional[List[str]] = None,
    ) -> None:
        self._registry = registry
        self._strategy = strategy
        self._scores_path: Path = scores_path or _DEFAULT_SCORES_PATH
        self._fallback_order: List[str] = (
            fallback_order if fallback_order is not None else ["ollama", "mock"]
        )
        self._scores: List[Dict[str, Any]] = self._load_scores()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: List[LLMMessage],
        task_type: TaskType = TaskType.GENERAL,
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Select a provider and send the request.

        Fallback chain:
        1. Primary provider (selected by strategy)
        2. Fallback providers in order
        3. LLMProviderUnavailableError if all providers fail
        """
        request = LLMRequest(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            metadata=metadata or {},
        )

        primary = await self.select_available_provider(task_type)
        candidates: List[LLMProvider] = []
        if primary is not None:
            candidates.append(primary)

        # Build fallback list (skip duplicates)
        for name in self._fallback_order:
            provider = self._registry.get(name)
            if provider is not None and provider not in candidates:
                candidates.append(provider)

        # Try every candidate in order
        last_error: Optional[Exception] = None
        for provider in candidates:
            try:
                if not await provider.is_available():
                    continue
                return await provider.complete(request)
            except LLMProviderUnavailableError as exc:
                last_error = exc
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        raise LLMProviderUnavailableError(
            "All providers are unavailable."
        ) from last_error

    def select_provider(self, task_type: TaskType) -> Optional[LLMProvider]:
        """Select the best provider synchronously (no availability check).

        Useful for tests and introspection.
        """
        strategy = self._strategy
        if strategy == RoutingStrategy.ADAPTIVE:
            return self._select_adaptive(task_type)
        if strategy == RoutingStrategy.QUALITY:
            return self._select_quality(task_type)
        if strategy == RoutingStrategy.COST:
            return self._select_cost(task_type)
        if strategy == RoutingStrategy.LOCAL:
            return self._select_local(task_type)
        return self._select_adaptive(task_type)

    async def select_available_provider(
        self, task_type: TaskType
    ) -> Optional[LLMProvider]:
        """Select the best *available* provider (with is_available() check)."""
        provider = self.select_provider(task_type)
        if provider is not None and await provider.is_available():
            return provider
        # Try fallbacks
        for name in self._fallback_order:
            fallback = self._registry.get(name)
            if fallback is not None and await fallback.is_available():
                return fallback
        return None

    async def record_score(
        self,
        provider_name: str,
        task_type: TaskType,
        score: float,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store an experience score for future routing decisions."""
        entry: Dict[str, Any] = {
            "provider": provider_name,
            "task_type": task_type.value,
            "score": score,
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if metadata:
            entry["metadata"] = metadata

        self._scores.append(entry)
        # Keep only the latest _MAX_SCORES entries in memory
        if len(self._scores) > _MAX_SCORES:
            self._scores = self._scores[-_MAX_SCORES:]

        self._append_score(entry)

    def get_scores(
        self,
        provider_name: Optional[str] = None,
        task_type: Optional[TaskType] = None,
    ) -> List[Dict[str, Any]]:
        """Return stored scores (optionally filtered)."""
        result = self._scores
        if provider_name is not None:
            result = [s for s in result if s.get("provider") == provider_name]
        if task_type is not None:
            result = [s for s in result if s.get("task_type") == task_type.value]
        return list(result)

    def get_best_provider_for(self, task_type: TaskType) -> Optional[str]:
        """Return the provider name with the highest average score."""
        relevant = [
            s for s in self._scores if s.get("task_type") == task_type.value
        ]
        if not relevant:
            return None

        totals: Dict[str, List[float]] = {}
        for entry in relevant:
            name = entry.get("provider", "")
            totals.setdefault(name, []).append(entry.get("score", 0.0))

        averages = {name: sum(vals) / len(vals) for name, vals in totals.items()}
        return max(averages, key=lambda n: averages[n])

    # ------------------------------------------------------------------
    # Routing strategies
    # ------------------------------------------------------------------

    def _select_adaptive(self, task_type: TaskType) -> Optional[LLMProvider]:
        best = self.get_best_provider_for(task_type)
        if best is not None:
            provider = self._registry.get(best)
            if provider is not None:
                return provider
        return self._select_quality(task_type)

    def _select_quality(self, task_type: TaskType) -> Optional[LLMProvider]:
        candidates = [
            p
            for p in self._registry.list()
            if task_type.value in p.capabilities.strengths
        ]
        if candidates:
            # Prefer provider with more strengths on a tie
            candidates.sort(key=lambda p: len(p.capabilities.strengths), reverse=True)
            return candidates[0]
        all_providers = self._registry.list()
        return all_providers[0] if all_providers else None

    def _select_cost(self, task_type: TaskType) -> Optional[LLMProvider]:
        providers = sorted(
            self._registry.list(),
            key=lambda p: p.capabilities.cost_per_1k_tokens,
        )
        return providers[0] if providers else None

    def _select_local(self, task_type: TaskType) -> Optional[LLMProvider]:
        local = [p for p in self._registry.list() if p.capabilities.local]
        return local[0] if local else self._select_quality(task_type)

    # ------------------------------------------------------------------
    # Score persistence
    # ------------------------------------------------------------------

    def _load_scores(self) -> List[Dict[str, Any]]:
        if not self._scores_path.exists():
            return []
        scores: List[Dict[str, Any]] = []
        try:
            with self._scores_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            scores.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except OSError:
            return []
        # Keep only the latest _MAX_SCORES entries
        return scores[-_MAX_SCORES:]

    def _append_score(self, entry: Dict[str, Any]) -> None:
        self._scores_path.parent.mkdir(parents=True, exist_ok=True)
        with self._scores_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
