"""
GENUS - Generative ENvironment for Unified Systems

A modular agent-based framework with clean architecture principles.
"""

__version__ = "0.1.0"
__author__ = "WoltLab51"

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message

__all__ = [
    "Agent",
    "AgentState",
    "MessageBus",
    "Message",
]
