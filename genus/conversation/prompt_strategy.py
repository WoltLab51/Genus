"""
PromptStrategy — Phase 13c

Determines *how* to call the LLM for each user request.

Instead of always using the same task_type / max_tokens / temperature,
the ConversationAgent resolves a :class:`PromptStrategy` that is adapted
to the current intent, user profile and situational context.
This ensures quality and resource efficiency at the same time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from genus.conversation.situation import ActivityHint, SituationContext
from genus.llm.router import TaskType


# ---------------------------------------------------------------------------
# PromptStrategy
# ---------------------------------------------------------------------------


@dataclass
class PromptStrategy:
    """Describes the optimal way to call the LLM for a given request.

    Args:
        task_type:       LLM router task type (affects provider selection).
        max_tokens:      Maximum tokens for the completion.
        temperature:     Sampling temperature.
        context_depth:   How many history messages to include.
        include_profile: Whether to inject the user profile block.
        include_episodic: Whether to include episodic (run-history) context.
    """

    task_type: TaskType
    max_tokens: int
    temperature: float
    context_depth: int
    include_profile: bool
    include_episodic: bool


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


# Import Intent lazily to avoid circular imports at module load time.
# The function below resolves it on first call.

def resolve_prompt_strategy(
    intent: object,
    profile: Optional[object] = None,
    situation: Optional[SituationContext] = None,
    response_policy: Optional[object] = None,
) -> PromptStrategy:
    """Return the optimal :class:`PromptStrategy` for the given context.

    Rules (applied in order):
    1. Base strategy from *intent*.
    2. Adjust *max_tokens* by *profile.response_style*
       (kurz → ×0.5, technisch → ×1.5, ausführlich → ×2.0).
    3. Child users: hard cap at 200 tokens, temperature raised to 0.5.
    4. COMMUTING situation: halve *max_tokens*.
    5. ResponsePolicy without audio: strip personal profile from context.
    """
    # Resolve intent value (works with str and Enum)
    intent_val: str = intent.value if hasattr(intent, "value") else str(intent)

    # ── 1. Base strategy per intent ──────────────────────────────────────────
    _bases: dict[str, PromptStrategy] = {
        "chat":           PromptStrategy(TaskType.GENERAL,   200, 0.7, 10, True,  False),
        "question":       PromptStrategy(TaskType.REASONING,  500, 0.2, 10, True,  False),
        "memory_request": PromptStrategy(TaskType.SUMMARIZE,  400, 0.2,  5, True,  True),
        "status_request": PromptStrategy(TaskType.GENERAL,   200, 0.1,  3, False, True),
        "dev_request":    PromptStrategy(TaskType.PLANNING,   800, 0.2,  5, True,  False),
        "situation_update": PromptStrategy(TaskType.GENERAL, 150, 0.5,  3, True,  False),
    }

    strategy = _bases.get(
        intent_val,
        PromptStrategy(TaskType.GENERAL, 300, 0.4, 10, True, False),
    )
    # Dataclass is mutable; work with a copy so the table stays clean
    strategy = PromptStrategy(
        task_type=strategy.task_type,
        max_tokens=strategy.max_tokens,
        temperature=strategy.temperature,
        context_depth=strategy.context_depth,
        include_profile=strategy.include_profile,
        include_episodic=strategy.include_episodic,
    )

    # ── 2. response_style adjustments ───────────────────────────────────────
    if profile is not None:
        style = getattr(profile, "response_style", None)
        _style_factors: dict[str, float] = {
            "kurz":        0.5,
            "ausführlich": 2.0,
            "technisch":   1.5,
        }
        factor = _style_factors.get(style or "", 1.0)
        strategy.max_tokens = max(50, int(strategy.max_tokens * factor))
        if style == "technisch":
            strategy.temperature = 0.1

        # ── 3. Child user cap ─────────────────────────────────────────────
        is_child_fn = getattr(profile, "is_child", None)
        if callable(is_child_fn) and is_child_fn():
            strategy.max_tokens = min(strategy.max_tokens, 200)
            strategy.temperature = 0.5

    # ── 4. COMMUTING — halve tokens ─────────────────────────────────────────
    if situation is not None and not situation.is_stale():
        if situation.activity == ActivityHint.COMMUTING:
            strategy.max_tokens = max(50, strategy.max_tokens // 2)

    # ── 5. ResponsePolicy — no personal context when not alone ──────────────
    if response_policy is not None:
        may_answer_aloud = getattr(response_policy, "may_answer_aloud", True)
        if not may_answer_aloud:
            strategy.include_profile = False

    return strategy
