"""
Agent Specification

Defines the data models that describe the structural identity of every agent
GENUS can build or manage.  These models answer the question: *where does this
agent live in the system, and what constraints govern its lifecycle?*

``AgentSpec`` sits at the intersection of three GENUS subsystems:

- **Builder-Agent** — uses ``AgentSpec`` to describe a new agent before
  building it.  The spec is the contract that the builder must fulfil.
- **GrowthOrchestrator** — inspects ``AgentSpec`` fields (layer, domain,
  replaceable, max_instances) to decide whether a build or replacement is
  currently allowed.
- **PersonalityStore** — persists ``AgentSpec`` objects so that GENUS retains
  a record of every agent it has ever considered or built.

``AgentSpec.morphology_tags`` is the designated extension point for the future
``MorphologyEngine``.  Any free-form metadata that the engine needs (e.g.
variant identifiers, exploration flags, fitness scores) can be stored there
without changing the core schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List


class AgentLayer(Enum):
    """The architectural layer an agent belongs to.

    Layers enforce import discipline: higher layers may import from lower
    layers, but not vice versa.
    """

    KERNEL = "kernel"
    CAPABILITY = "capability"
    GROWTH = "growth"


class AgentDomain(Enum):
    """The functional domain an agent serves."""

    SYSTEM = "system"
    FAMILY = "family"
    HOME = "home"
    TRADING = "trading"
    SECURITY = "security"
    COMMUNICATION = "communication"


@dataclass
class AgentMorphology:
    """Structural constraints that govern an agent's lifecycle.

    Attributes:
        layer: The architectural layer this agent belongs to.
        domain: The functional domain this agent serves.
        replaceable: Whether GENUS is allowed to replace this agent
            automatically.  Kernel agents must always be ``False``.
        singleton: Whether only a single instance of this agent may exist at
            any time.
        max_instances: Maximum number of parallel instances allowed.  Must be
            >= 1.
        depends_on: Agent IDs or names that must be running before this agent
            can be started.
    """

    layer: AgentLayer
    domain: AgentDomain
    replaceable: bool = True
    singleton: bool = False
    max_instances: int = 1
    depends_on: List[str] = field(default_factory=list)


@dataclass
class AgentSpec:
    """The complete contract that every self-built agent must satisfy.

    ``AgentSpec`` is the single source of truth about an agent's identity,
    purpose, and lifecycle constraints.  It is created by the Builder-Agent,
    evaluated by the GrowthOrchestrator, and persisted by the
    PersonalityStore.

    ``morphology_tags`` is intentionally open-ended: it is the hook for the
    future ``MorphologyEngine`` to attach variant metadata, exploration flags,
    or fitness scores without requiring schema changes.

    Attributes:
        name: Unique human-readable name, e.g. ``"FamilyCalendarAgent"``.
        description: Short description of what this agent does.
        morphology: Layer, domain, and lifecycle constraints.
        version: Monotonically increasing version number.
        created_at: ISO 8601 UTC timestamp.  Set automatically on first
            instantiation if left empty.
        status: Lifecycle status.  One of ``"planned"``, ``"building"``,
            ``"active"``, or ``"deprecated"``.
        morphology_tags: Free-form key/value pairs for the MorphologyEngine.
    """

    name: str
    description: str
    morphology: AgentMorphology
    version: int = 1
    created_at: str = ""
    status: str = "planned"
    morphology_tags: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

        if self.morphology.max_instances < 1:
            raise ValueError(
                f"max_instances must be >= 1, got {self.morphology.max_instances}"
            )

        if (
            self.morphology.layer == AgentLayer.KERNEL
            and self.morphology.replaceable
        ):
            raise ValueError(
                f"Kernel agent '{self.name}' must not be replaceable=True. "
                "Kernel agents are permanent and must not be replaced by GENUS."
            )

    def is_kernel_safe(self) -> bool:
        """Return ``True`` if this agent belongs to the KERNEL layer.

        Kernel agents are by definition not replaceable.  If a kernel agent
        has ``replaceable=True`` this method raises ``ValueError`` because
        that combination is forbidden.

        Returns:
            ``True`` when ``morphology.layer == AgentLayer.KERNEL``,
            ``False`` otherwise.

        Raises:
            ValueError: If the agent is in the KERNEL layer but has
                ``replaceable=True``.
        """
        if self.morphology.layer == AgentLayer.KERNEL:
            if self.morphology.replaceable:
                raise ValueError(
                    f"Kernel agent '{self.name}' must not be replaceable=True."
                )
            return True
        return False
