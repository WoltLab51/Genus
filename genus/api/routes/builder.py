"""Builder API routes."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from genus.api.deps import get_current_actor
from genus.builder import BuildRequest, BuilderAgent
from genus.identity.actor_registry import Actor

router = APIRouter(prefix="/v1/builder", tags=["builder"])


def _ensure_builder_agent(request: Request) -> BuilderAgent:
    agent = getattr(request.app.state, "builder_agent", None)
    if agent is None:
        llm_router = getattr(request.app.state, "llm_router", None)
        agent = BuilderAgent(llm_router=llm_router)
        request.app.state.builder_agent = agent
    return agent


def _ensure_builder_role(actor: Actor) -> None:
    role_obj = getattr(actor, "role", None)
    role = role_obj.api_role if role_obj is not None else ""
    capabilities = getattr(actor, "capabilities", frozenset())
    if role == "admin" or "parent" in capabilities:
        return
    raise HTTPException(status_code=403, detail="Admin or parent role required")


@router.post("/build")
async def start_build(
    body: BuildRequest,
    request: Request,
    actor=Depends(get_current_actor),
) -> Dict[str, Any]:
    _ensure_builder_role(actor)
    agent = _ensure_builder_agent(request)
    result = await agent.build(body)
    return {"success": result.status == "success", "result": result.model_dump(mode="json")}


@router.get("/status/{request_id}")
async def get_build_status(
    request_id: str,
    request: Request,
    _actor=Depends(get_current_actor),
) -> Dict[str, Any]:
    agent = _ensure_builder_agent(request)
    result = await agent.get_status(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Build result not found")
    return {"success": True, "result": result.model_dump(mode="json")}


@router.get("/results")
async def list_build_results(
    request: Request,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    _actor=Depends(get_current_actor),
) -> Dict[str, List[Dict[str, Any]]]:
    agent = _ensure_builder_agent(request)
    results = await agent.list_results(page=page, per_page=per_page)
    return {
        "success": True,
        "page": page,
        "per_page": per_page,
        "results": [item.model_dump(mode="json") for item in results],
    }


@router.delete("/results/{request_id}")
async def delete_build_result(
    request_id: str,
    request: Request,
    actor=Depends(get_current_actor),
) -> Dict[str, Any]:
    _ensure_builder_role(actor)
    agent = _ensure_builder_agent(request)
    deleted = await agent.delete_result(request_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Build result not found")
    return {"success": True, "deleted": request_id}
