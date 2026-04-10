"""
Identity Profile

Defines the ``IdentityProfile`` dataclass that captures the stable personality
and governance constraints for GENUS as a system.  Also defines
``StabilityRules``, which governs when and how often the growth layer is
allowed to replace or upgrade agents.

In the GENUS growth flow this module is consulted by the ``GrowthOrchestrator``
(and optionally ``GrowthGuard``) before any build or replacement decision is
made.  Temporal cooldowns prevent thrashing; score thresholds prevent replacing
agents that are performing adequately.

``StabilityRules.cooldown_same_domain_per_need`` is the key toggle that allows
GENUS to build multiple agents for the same domain (e.g. ``FamilyCalendarAgent``
and ``FamilySecurityAgent``) without waiting for the 12-hour domain cooldown,
because the cooldown is tracked per ``(domain, need_description)`` pair rather
than per domain alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StabilityRules:
    """Temporal and score-based constraints for agent replacement decisions.

    Attributes:
        min_agent_runtime_before_replace_s: An agent must have been running for
            at least this many seconds before GENUS is allowed to consider
            replacing it.  Default: 86 400 s (24 h).
        cooldown_same_domain_s: Minimum time in seconds that must pass between
            two consecutive build attempts in the same domain.  Default:
            43 200 s (12 h).
        cooldown_after_failed_build_s: Minimum time in seconds to wait before
            retrying after a failed build.  Default: 3 600 s (1 h).
        cooldown_same_domain_per_need: When ``True`` the domain cooldown is
            tracked per ``(domain, need_description)`` pair instead of per
            domain alone.  This allows GENUS to build both a
            ``FamilyCalendarAgent`` and a ``FamilySecurityAgent`` without
            waiting 12 h between them, because they address different needs
            within the same domain.  Default: ``True``.
        min_trigger_count_before_build: The growth trigger must fire at least
            this many times before a new agent build is initiated.  Prevents
            spurious one-off signals from causing immediate builds.
            Default: 2.
        min_observations_before_upgrade: Minimum number of scored run
            observations required before an upgrade decision is made.
            Default: 5.
        min_score_to_keep_agent: Agents whose average score falls below this
            value are candidates for replacement.  Default: 0.40.
        min_score_to_replace_agent: The replacement candidate must reach at
            least this score before it is allowed to take over.  Default: 0.65.
    """

    # Temporal locks (seconds)
    min_agent_runtime_before_replace_s: int = 86_400   # 24 h
    cooldown_same_domain_s: int = 43_200               # 12 h
    cooldown_after_failed_build_s: int = 3_600          # 1 h

    # Context-based cooldown control
    # When True, cooldown is tracked per (domain, need_description) pair, not
    # just per domain.  This lets GENUS build e.g. FamilyCalendarAgent AND
    # FamilySecurityAgent without waiting for the domain cooldown to expire.
    cooldown_same_domain_per_need: bool = True

    # Observation thresholds
    min_trigger_count_before_build: int = 2
    min_observations_before_upgrade: int = 5

    # Score thresholds
    min_score_to_keep_agent: float = 0.40
    min_score_to_replace_agent: float = 0.65


@dataclass
class IdentityProfile:
    """High-level identity and governance constraints for the GENUS system.

    Attributes:
        system_name: Human-readable name for this GENUS instance.
        owner: The person or organisation that owns and operates this instance.
        stability_rules: The ``StabilityRules`` governing when agents may be
            replaced or upgraded.
        description: Optional free-text description of this GENUS instance's
            purpose.
    """

    system_name: str
    owner: str
    stability_rules: StabilityRules = field(default_factory=StabilityRules)
    description: str = ""
