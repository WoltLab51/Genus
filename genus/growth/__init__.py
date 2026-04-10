"""
Growth Package

Provides components for GENUS's self-directed growth capabilities, including
identity management and stability rules for agent replacement decisions.
"""

from genus.growth.identity_profile import IdentityProfile, StabilityRules
from genus.growth.agent_spec import AgentSpec, AgentMorphology, AgentLayer, AgentDomain

__all__ = [
    "IdentityProfile",
    "StabilityRules",
    "AgentSpec",
    "AgentMorphology",
    "AgentLayer",
    "AgentDomain",
]
