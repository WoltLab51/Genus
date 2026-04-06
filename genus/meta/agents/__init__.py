"""
Meta Agents

Agents that operate at the meta layer, analyzing and learning from runs.
These agents are read-only except for journal writes and message publishing.
"""

from genus.meta.agents.evaluation_agent import EvaluationAgent

__all__ = ["EvaluationAgent"]
