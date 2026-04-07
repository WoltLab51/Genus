"""
Feedback module – signal capture and journaling for GENUS feedback.

The FeedbackAgent bridges external outcome signals (outcome.recorded)
into the RunJournal as the single source of truth. It does NOT directly
influence strategy or learning — feedback is a signal, not a decision.
"""

from genus.feedback.outcome import OutcomePayload, validate_outcome_payload
from genus.feedback.agent import FeedbackAgent
from genus.feedback import topics

__all__ = [
    "OutcomePayload",
    "validate_outcome_payload",
    "FeedbackAgent",
    "topics",
]
