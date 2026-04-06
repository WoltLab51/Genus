"""
Meta Layer for GENUS

Provides evaluation and learning capabilities that transform a dev-automation
workflow into a system with "DNA" - the ability to learn from runs and improve
strategies over time.

Key components:
- taxonomy: Failure classification and strategy recommendations (enums/constants)
- evaluation_models: Data models for evaluation input and output
- evaluator: Heuristic-based run evaluator (deterministic, no ML)
- evaluation_agent: Agent that evaluates runs and publishes insights

All evaluation is deterministic and uses simple heuristics. No ML, no external
services, no network calls.
"""

from genus.meta.taxonomy import (
    FailureClass,
    RootCauseHint,
    StrategyRecommendation,
)
from genus.meta.evaluation_models import (
    EvaluationInput,
    EvaluationArtifact,
)
from genus.meta.evaluator import RunEvaluator

__all__ = [
    "FailureClass",
    "RootCauseHint",
    "StrategyRecommendation",
    "EvaluationInput",
    "EvaluationArtifact",
    "RunEvaluator",
]
