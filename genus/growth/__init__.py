"""
Growth Package

Provides components for GENUS's self-directed growth capabilities, including
identity management, stability rules, need observation, growth orchestration,
and agent bootstrapping.
"""

from genus.growth.identity_profile import IdentityProfile, StabilityRules
from genus.growth.agent_spec import AgentSpec, AgentMorphology, AgentLayer, AgentDomain
from genus.growth.need_record import NeedRecord
from genus.growth.need_observer import NeedObserver
from genus.growth.growth_orchestrator import GrowthOrchestrator
from genus.growth.bootstrapper import AgentBootstrapper

__all__ = [
    "IdentityProfile",
    "StabilityRules",
    "AgentSpec",
    "AgentMorphology",
    "AgentLayer",
    "AgentDomain",
    "NeedRecord",
    "NeedObserver",
    "GrowthOrchestrator",
    "AgentBootstrapper",
]
