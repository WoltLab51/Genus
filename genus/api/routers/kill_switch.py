"""
Kill-Switch API Router

POST /kill-switch/activate   — Admin only: activate the kill-switch
POST /kill-switch/deactivate — Admin only: deactivate the kill-switch
GET  /kill-switch/status     — Operator: current kill-switch state
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from genus.api.deps import get_kill_switch, verify_admin, verify_operator

router = APIRouter()


class KillSwitchActivateRequest(BaseModel):
    reason: str
    actor: Optional[str] = None


@router.post("/activate")
async def activate(
    body: KillSwitchActivateRequest,
    request: Request,
    _: None = Depends(verify_admin),
):
    ks = get_kill_switch(request)
    if ks is None:
        raise HTTPException(status_code=503, detail="Kill-switch not configured")
    ks.activate(reason=body.reason, actor=body.actor)
    return {"status": "activated", "active": True}


@router.post("/deactivate")
async def deactivate(request: Request, _: None = Depends(verify_admin)):
    ks = get_kill_switch(request)
    if ks is None:
        raise HTTPException(status_code=503, detail="Kill-switch not configured")
    ks.deactivate()
    return {"status": "deactivated", "active": False}


@router.get("/status")
async def status(request: Request, _: None = Depends(verify_operator)):
    ks = get_kill_switch(request)
    if ks is None:
        return {"active": False, "reason": "", "actor": None}
    return {"active": ks.is_active(), "reason": ks.reason, "actor": ks.actor}
