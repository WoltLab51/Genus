"""Tests for genus.llm.router — LLMRouter."""

import json
from pathlib import Path
from typing import List, Optional

import pytest

from genus.llm.exceptions import LLMProviderUnavailableError
from genus.llm.models import LLMMessage, LLMRequest, LLMResponse, LLMRole
from genus.llm.providers.base import LLMProvider, ProviderCapabilities
from genus.llm.providers.mock_provider import MockProvider
from genus.llm.providers.registry import ProviderRegistry
from genus.llm.router import LLMRouter, RoutingStrategy, TaskType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _NamedMockProvider(LLMProvider):
    """MockProvider with configurable name, capabilities and availability."""

    def __init__(
        self,
        name: str,
        local: bool = False,
        cost_per_1k_tokens: float = 0.01,
        strengths: Optional[List[str]] = None,
        available: bool = True,
        responses: Optional[List[str]] = None,
    ) -> None:
        self._name = name
        self._caps = ProviderCapabilities(
            name=name,
            local=local,
            cost_per_1k_tokens=cost_per_1k_tokens,
            max_context_tokens=4096,
            strengths=strengths or [],
            requires_api_key=False,
        )
        self._available = available
        self._responses = responses or ["response from " + name]
        self._call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._caps

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self._available:
            raise LLMProviderUnavailableError(f"{self._name} unavailable")
        index = min(self._call_count, len(self._responses) - 1)
        content = self._responses[index]
        self._call_count += 1
        return LLMResponse(
            content=content,
            model="test-model",
            provider=self._name,
        )

    async def is_available(self) -> bool:
        return self._available


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_scores(tmp_path: Path) -> Path:
    return tmp_path / "router_scores.jsonl"


@pytest.fixture
def registry_with_providers() -> ProviderRegistry:
    """Registry with three providers of distinct characteristics."""
    registry = ProviderRegistry()

    # cheap local provider — strengths: planning
    registry.register(
        _NamedMockProvider(
            name="local_mock",
            local=True,
            cost_per_1k_tokens=0.0,
            strengths=["planning"],
            available=True,
        )
    )
    # expensive cloud provider — strengths: code_gen, code_review, reasoning
    registry.register(
        _NamedMockProvider(
            name="cloud_mock",
            local=False,
            cost_per_1k_tokens=0.02,
            strengths=["code_gen", "code_review", "reasoning"],
            available=True,
        )
    )
    # medium provider — strengths: summarize
    registry.register(
        _NamedMockProvider(
            name="mid_mock",
            local=False,
            cost_per_1k_tokens=0.01,
            strengths=["summarize"],
            available=True,
        )
    )
    return registry


# ---------------------------------------------------------------------------
# Tests — TaskType / RoutingStrategy enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_task_type_values(self):
        assert TaskType.PLANNING == "planning"
        assert TaskType.CODE_GEN == "code_gen"
        assert TaskType.CODE_REVIEW == "code_review"
        assert TaskType.REASONING == "reasoning"
        assert TaskType.SUMMARIZE == "summarize"
        assert TaskType.GENERAL == "general"

    def test_routing_strategy_values(self):
        assert RoutingStrategy.QUALITY == "quality"
        assert RoutingStrategy.COST == "cost"
        assert RoutingStrategy.LOCAL == "local"
        assert RoutingStrategy.ADAPTIVE == "adaptive"


# ---------------------------------------------------------------------------
# Tests — COST strategy
# ---------------------------------------------------------------------------

class TestCostStrategy:
    def test_selects_cheapest_provider(
        self, registry_with_providers: ProviderRegistry, tmp_scores: Path
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            strategy=RoutingStrategy.COST,
            scores_path=tmp_scores,
        )
        provider = router.select_provider(TaskType.GENERAL)
        assert provider is not None
        assert provider.capabilities.cost_per_1k_tokens == 0.0

    def test_selects_cheapest_name(
        self, registry_with_providers: ProviderRegistry, tmp_scores: Path
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            strategy=RoutingStrategy.COST,
            scores_path=tmp_scores,
        )
        provider = router.select_provider(TaskType.CODE_GEN)
        assert provider is not None
        assert provider.name == "local_mock"


# ---------------------------------------------------------------------------
# Tests — LOCAL strategy
# ---------------------------------------------------------------------------

class TestLocalStrategy:
    def test_selects_local_provider(
        self, registry_with_providers: ProviderRegistry, tmp_scores: Path
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            strategy=RoutingStrategy.LOCAL,
            scores_path=tmp_scores,
        )
        provider = router.select_provider(TaskType.GENERAL)
        assert provider is not None
        assert provider.capabilities.local is True

    def test_falls_back_to_quality_when_no_local(self, tmp_scores: Path):
        registry = ProviderRegistry()
        registry.register(
            _NamedMockProvider(
                name="cloud_only",
                local=False,
                cost_per_1k_tokens=0.02,
                strengths=["planning"],
            )
        )
        router = LLMRouter(
            registry=registry,
            strategy=RoutingStrategy.LOCAL,
            scores_path=tmp_scores,
        )
        provider = router.select_provider(TaskType.PLANNING)
        assert provider is not None
        assert provider.name == "cloud_only"


# ---------------------------------------------------------------------------
# Tests — QUALITY strategy
# ---------------------------------------------------------------------------

class TestQualityStrategy:
    def test_selects_provider_with_matching_strength(
        self, registry_with_providers: ProviderRegistry, tmp_scores: Path
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            strategy=RoutingStrategy.QUALITY,
            scores_path=tmp_scores,
        )
        provider = router.select_provider(TaskType.CODE_GEN)
        assert provider is not None
        assert "code_gen" in provider.capabilities.strengths

    def test_prefers_provider_with_more_strengths_on_tie(self, tmp_scores: Path):
        registry = ProviderRegistry()
        registry.register(
            _NamedMockProvider(name="a", strengths=["code_gen"])
        )
        registry.register(
            _NamedMockProvider(name="b", strengths=["code_gen", "reasoning", "planning"])
        )
        router = LLMRouter(
            registry=registry,
            strategy=RoutingStrategy.QUALITY,
            scores_path=tmp_scores,
        )
        provider = router.select_provider(TaskType.CODE_GEN)
        assert provider is not None
        assert provider.name == "b"

    def test_falls_back_to_first_provider_when_no_match(self, tmp_scores: Path):
        registry = ProviderRegistry()
        registry.register(_NamedMockProvider(name="only", strengths=[]))
        router = LLMRouter(
            registry=registry,
            strategy=RoutingStrategy.QUALITY,
            scores_path=tmp_scores,
        )
        provider = router.select_provider(TaskType.PLANNING)
        assert provider is not None
        assert provider.name == "only"


# ---------------------------------------------------------------------------
# Tests — ADAPTIVE strategy
# ---------------------------------------------------------------------------

class TestAdaptiveStrategy:
    def test_falls_back_to_quality_when_no_scores(
        self, registry_with_providers: ProviderRegistry, tmp_scores: Path
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            strategy=RoutingStrategy.ADAPTIVE,
            scores_path=tmp_scores,
        )
        # No scores → quality selection for CODE_GEN
        provider = router.select_provider(TaskType.CODE_GEN)
        assert provider is not None
        assert "code_gen" in provider.capabilities.strengths

    async def test_uses_stored_scores(
        self, registry_with_providers: ProviderRegistry, tmp_scores: Path
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            strategy=RoutingStrategy.ADAPTIVE,
            scores_path=tmp_scores,
        )
        # Record a high score for local_mock on planning
        await router.record_score("local_mock", TaskType.PLANNING, 0.95)
        # Now adaptive should pick local_mock for planning
        provider = router.select_provider(TaskType.PLANNING)
        assert provider is not None
        assert provider.name == "local_mock"

    async def test_adaptive_with_scores_overrides_quality(
        self, registry_with_providers: ProviderRegistry, tmp_scores: Path
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            strategy=RoutingStrategy.ADAPTIVE,
            scores_path=tmp_scores,
        )
        # cloud_mock has code_gen strength; force mid_mock via score
        await router.record_score("mid_mock", TaskType.CODE_GEN, 0.99)
        provider = router.select_provider(TaskType.CODE_GEN)
        assert provider is not None
        assert provider.name == "mid_mock"


# ---------------------------------------------------------------------------
# Tests — record_score / get_scores / get_best_provider_for
# ---------------------------------------------------------------------------

class TestScorePersistence:
    async def test_record_score_writes_to_file(self, tmp_scores: Path, registry_with_providers: ProviderRegistry):
        router = LLMRouter(
            registry=registry_with_providers,
            scores_path=tmp_scores,
        )
        await router.record_score(
            provider_name="local_mock",
            task_type=TaskType.PLANNING,
            score=0.85,
            run_id="run-001",
        )
        assert tmp_scores.exists()
        lines = tmp_scores.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["provider"] == "local_mock"
        assert data["task_type"] == "planning"
        assert data["score"] == 0.85
        assert data["run_id"] == "run-001"
        assert "timestamp" in data

    async def test_record_score_appends_multiple(
        self, tmp_scores: Path, registry_with_providers: ProviderRegistry
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            scores_path=tmp_scores,
        )
        await router.record_score("local_mock", TaskType.PLANNING, 0.8)
        await router.record_score("cloud_mock", TaskType.CODE_GEN, 0.9)
        lines = tmp_scores.read_text().strip().splitlines()
        assert len(lines) == 2

    async def test_get_scores_all(
        self, tmp_scores: Path, registry_with_providers: ProviderRegistry
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            scores_path=tmp_scores,
        )
        await router.record_score("local_mock", TaskType.PLANNING, 0.8)
        await router.record_score("cloud_mock", TaskType.CODE_GEN, 0.9)
        scores = router.get_scores()
        assert len(scores) == 2

    async def test_get_scores_filtered_by_provider(
        self, tmp_scores: Path, registry_with_providers: ProviderRegistry
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            scores_path=tmp_scores,
        )
        await router.record_score("local_mock", TaskType.PLANNING, 0.8)
        await router.record_score("cloud_mock", TaskType.CODE_GEN, 0.9)
        scores = router.get_scores(provider_name="local_mock")
        assert len(scores) == 1
        assert scores[0]["provider"] == "local_mock"

    async def test_get_scores_filtered_by_task_type(
        self, tmp_scores: Path, registry_with_providers: ProviderRegistry
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            scores_path=tmp_scores,
        )
        await router.record_score("local_mock", TaskType.PLANNING, 0.8)
        await router.record_score("cloud_mock", TaskType.CODE_GEN, 0.9)
        scores = router.get_scores(task_type=TaskType.CODE_GEN)
        assert len(scores) == 1
        assert scores[0]["task_type"] == "code_gen"

    async def test_get_best_provider_for(
        self, tmp_scores: Path, registry_with_providers: ProviderRegistry
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            scores_path=tmp_scores,
        )
        await router.record_score("local_mock", TaskType.PLANNING, 0.6)
        await router.record_score("cloud_mock", TaskType.PLANNING, 0.95)
        best = router.get_best_provider_for(TaskType.PLANNING)
        assert best == "cloud_mock"

    def test_get_best_provider_for_no_scores(
        self, tmp_scores: Path, registry_with_providers: ProviderRegistry
    ):
        router = LLMRouter(
            registry=registry_with_providers,
            scores_path=tmp_scores,
        )
        assert router.get_best_provider_for(TaskType.PLANNING) is None

    async def test_scores_loaded_from_file(
        self, tmp_scores: Path, registry_with_providers: ProviderRegistry
    ):
        """Scores written by one router instance are visible to the next."""
        router1 = LLMRouter(
            registry=registry_with_providers,
            scores_path=tmp_scores,
        )
        await router1.record_score("local_mock", TaskType.PLANNING, 0.88)

        router2 = LLMRouter(
            registry=registry_with_providers,
            scores_path=tmp_scores,
        )
        scores = router2.get_scores(task_type=TaskType.PLANNING)
        assert len(scores) == 1
        assert scores[0]["provider"] == "local_mock"

    async def test_max_scores_in_memory(
        self, tmp_scores: Path, registry_with_providers: ProviderRegistry
    ):
        """Memory is capped at 1000 entries."""
        router = LLMRouter(
            registry=registry_with_providers,
            scores_path=tmp_scores,
        )
        for i in range(1005):
            await router.record_score(
                "local_mock", TaskType.GENERAL, 0.5, run_id=f"run-{i}"
            )
        assert len(router.get_scores()) <= 1000


# ---------------------------------------------------------------------------
# Tests — complete() with fallback chain
# ---------------------------------------------------------------------------

class TestCompleteWithFallback:
    async def test_complete_uses_available_provider(
        self, tmp_scores: Path
    ):
        registry = ProviderRegistry()
        registry.register(
            _NamedMockProvider(
                name="primary",
                strengths=["general"],
                available=True,
                responses=["hello"],
            )
        )
        router = LLMRouter(
            registry=registry,
            strategy=RoutingStrategy.QUALITY,
            scores_path=tmp_scores,
            fallback_order=[],
        )
        resp = await router.complete(
            messages=[LLMMessage(role=LLMRole.USER, content="hi")],
            task_type=TaskType.GENERAL,
        )
        assert resp.content == "hello"
        assert resp.provider == "primary"

    async def test_complete_falls_back_when_primary_unavailable(
        self, tmp_scores: Path
    ):
        registry = ProviderRegistry()
        registry.register(
            _NamedMockProvider(name="primary", available=False, strengths=["general"])
        )
        registry.register(
            _NamedMockProvider(
                name="fallback",
                available=True,
                responses=["fallback response"],
                strengths=[],
            )
        )
        router = LLMRouter(
            registry=registry,
            strategy=RoutingStrategy.QUALITY,
            scores_path=tmp_scores,
            fallback_order=["fallback"],
        )
        resp = await router.complete(
            messages=[LLMMessage(role=LLMRole.USER, content="hi")],
            task_type=TaskType.GENERAL,
        )
        assert resp.provider == "fallback"

    async def test_complete_raises_when_all_unavailable(
        self, tmp_scores: Path
    ):
        registry = ProviderRegistry()
        registry.register(
            _NamedMockProvider(name="p1", available=False, strengths=[])
        )
        router = LLMRouter(
            registry=registry,
            strategy=RoutingStrategy.QUALITY,
            scores_path=tmp_scores,
            fallback_order=[],
        )
        with pytest.raises(LLMProviderUnavailableError):
            await router.complete(
                messages=[LLMMessage(role=LLMRole.USER, content="hi")],
                task_type=TaskType.GENERAL,
            )

    async def test_complete_skips_unavailable_in_fallback_chain(
        self, tmp_scores: Path
    ):
        registry = ProviderRegistry()
        registry.register(_NamedMockProvider(name="p1", available=False, strengths=[]))
        registry.register(_NamedMockProvider(name="p2", available=False, strengths=[]))
        registry.register(
            _NamedMockProvider(
                name="p3",
                available=True,
                responses=["p3 answer"],
                strengths=[],
            )
        )
        router = LLMRouter(
            registry=registry,
            strategy=RoutingStrategy.QUALITY,
            scores_path=tmp_scores,
            fallback_order=["p2", "p3"],
        )
        resp = await router.complete(
            messages=[LLMMessage(role=LLMRole.USER, content="hi")],
            task_type=TaskType.GENERAL,
        )
        assert resp.provider == "p3"

    async def test_select_available_provider_returns_none_when_all_unavailable(
        self, tmp_scores: Path
    ):
        registry = ProviderRegistry()
        registry.register(_NamedMockProvider(name="p1", available=False, strengths=[]))
        router = LLMRouter(
            registry=registry,
            strategy=RoutingStrategy.QUALITY,
            scores_path=tmp_scores,
            fallback_order=[],
        )
        result = await router.select_available_provider(TaskType.GENERAL)
        assert result is None
