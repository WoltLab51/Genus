"""
Feedback topic constants for the GENUS message bus.
"""

#: Published when a user/operator submits outcome feedback.
#: Payload: see OutcomePayload.to_message_payload()
OUTCOME_RECORDED = "outcome.recorded"

#: Published by FeedbackAgent after successfully journaling feedback.
#: Payload: {"run_id": str, "outcome": str, "score_delta": float, "source": str}
FEEDBACK_RECEIVED = "feedback.received"
