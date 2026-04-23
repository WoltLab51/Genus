"""DevLoop run API route.

POST /v1/devloop/run — trigger a full dev-loop run synchronously.
Requires operator-level authentication and an active kill-switch check.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from genus.api.deps import get_kill_switch, get_run_store, verify_operator
from genus.communication.message_bus import MessageBus
from genus.dev.agents.builder_agent import BuilderAgent
from genus.dev.agents.planner_agent import PlannerAgent
from genus.dev.agents.reviewer_agent import ReviewerAgent
from genus.dev.agents.tester_agent import TesterAgent
from genus.dev.devloop_orchestrator import DevLoopOrchestrator
from genus.dev.runtime import DevResponseTimeoutError
from genus.memory.run_journal import RunJournal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/devloop", tags=["devloop"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class DevloopRunRequest(BaseModel):
    """Request body for POST /v1/devloop/run."""

    goal: str = Field(..., min_length=1, description="Goal / task description for the dev loop.")
    run_id: Optional[str] = Field(
        None,
        pattern=r"^[a-zA-Z0-9_-]{1,128}$",
        description="Optional custom run ID (alphanumeric, hyphens, underscores, 1–128 chars); generated if omitted.",
    )
    timeout_s: float = Field(
        120.0,
        gt=0,
        le=3600.0,
        description="Maximum run duration in seconds.",
    )


class DevloopRunResponse(BaseModel):
    """Response body for POST /v1/devloop/run."""

    run_id: str
    status: str  # "completed" | "failed" | "ask_required"
    message: str
    phases: List[str]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/run", response_model=DevloopRunResponse)
async def run_devloop(body: DevloopRunRequest, request: Request) -> DevloopRunResponse:
    """Trigger a full dev-loop run synchronously.

    Sequences Plan → Implement → Test → Review using placeholder agents
    (no workspace or LLM required). Requires operator-level auth.

    Returns:
        DevloopRunResponse with status "completed", "failed", or "ask_required".

    Raises:
        HTTPException 401: Missing or invalid authentication.
        HTTPException 403: Insufficient role (operator or admin required).
        HTTPException 503: Kill-switch is currently active.
    """
    # --- Auth ---
    verify_operator(request)

    # --- Kill-switch guard ---
    kill_switch = get_kill_switch(request)
    if kill_switch is not None and kill_switch.is_active():
        raise HTTPException(status_code=503, detail="Kill-switch is active")

    run_id = body.run_id or str(uuid.uuid4())

    # --- In-process MessageBus (no Redis for this sync endpoint) ---
    bus = MessageBus(kill_switch=kill_switch)

    # --- Placeholder agents (no workspace / no LLM required) ---
    planner = PlannerAgent(bus, "devloop-api:planner")
    builder = BuilderAgent(bus, "devloop-api:builder")
    tester = TesterAgent(bus, "devloop-api:tester", mode="ok")
    reviewer = ReviewerAgent(bus, "devloop-api:reviewer")

    agents = [planner, builder, tester, reviewer]
    for agent in agents:
        agent.start()

    # --- RunJournal (use configured store, or the default provided by get_run_store) ---
    run_store = get_run_store(request)
    journal = RunJournal(run_id, run_store)

    orchestrator = DevLoopOrchestrator(
        bus,
        sender_id="devloop-api",
        timeout_s=body.timeout_s,
        run_journal=journal,
    )

    try:
        await orchestrator.run(run_id, body.goal)
        return DevloopRunResponse(
            run_id=run_id,
            status="completed",
            message="Dev loop completed successfully.",
            # Phases reflect the fixed DevLoopOrchestrator sequence; the
            # orchestrator does not currently return per-run phase tracking.
            phases=["plan", "implement", "test", "review"],
        )
    except DevResponseTimeoutError as exc:
        return DevloopRunResponse(
            run_id=run_id,
            status="failed",
            message=f"Dev loop timed out: {exc}",
            phases=[],
        )
    except Exception as exc:
        logger.exception("Unexpected devloop failure for run %s", run_id)
        raise HTTPException(
            status_code=500,
            detail="Dev loop failed due to an internal server error.",
        ) from exc
    finally:
        for agent in agents:
            try:
                agent.stop()
            except Exception:
                pass
