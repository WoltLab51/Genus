"""GENUS-2.0 Functional Agents.

Provides the abstract base class, registry, and built-in pilot agents
(Home, Family) that are wired into the /v1/agents/ API.
"""

from genus.functional_agents.base import AgentContext, AgentResponse, FunctionalAgent
from genus.functional_agents.registry import FunctionalAgentRegistry
from genus.functional_agents.home_agent import HomeAgent
from genus.functional_agents.family_agent import FamilyAgent

__all__ = [
    "AgentContext",
    "AgentResponse",
    "FunctionalAgent",
    "FunctionalAgentRegistry",
    "HomeAgent",
    "FamilyAgent",
]
