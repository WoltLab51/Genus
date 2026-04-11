"""
GENUS Conversation Module — Phase 13 / 13c

ConversationAgent, ConversationMemory, IntentClassifier, Intent,
SituationContext, SituationStore, ContextBuilder, PromptStrategy,
DevContextExtractor.
"""

from genus.conversation.conversation_agent import (
    ConversationAgent,
    ConversationMemory,
    ConversationResponse,
    Intent,
    IntentClassifier,
)
from genus.conversation.context_builder import ConversationContext, build_llm_context_block
from genus.conversation.dev_context_extractor import DevRunContext, extract_dev_context
from genus.conversation.prompt_strategy import PromptStrategy, resolve_prompt_strategy
from genus.conversation.situation import (
    ActivityHint,
    LocationHint,
    SituationContext,
    SituationStore,
)

__all__ = [
    # Phase 13
    "ConversationAgent",
    "ConversationMemory",
    "ConversationResponse",
    "Intent",
    "IntentClassifier",
    # Phase 13c
    "ActivityHint",
    "LocationHint",
    "SituationContext",
    "SituationStore",
    "ConversationContext",
    "build_llm_context_block",
    "DevRunContext",
    "extract_dev_context",
    "PromptStrategy",
    "resolve_prompt_strategy",
]
