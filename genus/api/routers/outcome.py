"""
POST /outcome

Auth: Operator (Bearer token)
Body: OutcomePayload fields (outcome, score_delta, notes, source, timestamp)
Action: publishes outcome.recorded on MessageBus
Response: {"status": "recorded", "run_id": str}

IMPORTANT: Only publish, no direct Journal interaction.
FeedbackAgent handles Journal writes.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from genus.api.deps import get_message_bus, verify_operator
from genus.communication.message_bus import Message
from genus.feedback.outcome import OUTCOME_VALUES, validate_outcome_payload
from genus.feedback.topics import OUTCOME_RECORDED

router = APIRouter()


class OutcomeRequest(BaseModel):
    outcome: str
    score_delta: float
    run_id: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = "user"
    timestamp: Optional[str] = None

    @field_validator("outcome")
    @classmethod
    def validate_outcome_field(cls, v: str) -> str:
        if v.strip().lower() not in OUTCOME_VALUES:
            raise ValueError(
                f"'outcome' must be one of {sorted(OUTCOME_VALUES)!r}, got {v!r}"
            )
        return v.strip().lower()


@router.post("")
async def record_outcome(
    body: OutcomeRequest,
    _: None = Depends(verify_operator),
    bus=Depends(get_message_bus),
) -> JSONResponse:
    """Publish outcome.recorded on the MessageBus."""
    try:
        payload_dict = {
            "outcome": body.outcome,
            "score_delta": body.score_delta,
            "notes": body.notes,
            "source": body.source,
            "timestamp": body.timestamp,
        }
        validated = validate_outcome_payload(payload_dict)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    run_id = body.run_id or "unknown"
    msg = Message(
        topic=OUTCOME_RECORDED,
        payload=validated.to_message_payload(),
        sender_id="api",
        metadata={"run_id": run_id},
    )

    if bus is not None:
        await bus.publish(msg)

    return JSONResponse({"status": "recorded", "run_id": run_id})
