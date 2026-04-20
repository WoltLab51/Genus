"""
Identity API Routes — Phase 14

Endpoints:
  GET  /me                       → own profile
  PUT  /me                       → update own profile (name, language, style)
  GET  /me/permissions           → which agents may I use?

  GET  /groups                   → my groups
  POST /groups                   → create new group
  GET  /groups/{group_id}        → group details
  POST /groups/{group_id}/invite → invite a member

  # Superadmin / Admin only:
  GET  /users                    → all users (Ronny as operator)
  GET  /users/{user_id}          → user details
  PUT  /users/{user_id}/permissions → set permissions
  GET  /parental/report/{child_user_id} → child report

  # Superadmin only:
  POST /users/{user_id}/lock     → lock account
  POST /users/{user_id}/unlock   → unlock account
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["identity"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    preferred_language: Optional[str] = None
    response_style: Optional[str] = None
    interests: Optional[List[str]] = None
    projects: Optional[List[str]] = None


class CreateGroupRequest(BaseModel):
    name: str
    group_type: str = "family"


class InviteMemberRequest(BaseModel):
    user_id: str
    role: str = "member"


class SetPermissionsRequest(BaseModel):
    allowed_agents: Optional[List[str]] = None
    denied_agents: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_profile_store(request: Request):
    store = getattr(request.app.state, "profile_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Identity module not available")
    return store


def _get_group_store(request: Request):
    store = getattr(request.app.state, "group_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Identity module not available")
    return store


def _get_permission_engine(request: Request):
    engine = getattr(request.app.state, "permission_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Identity module not available")
    return engine


def _get_parental_agent(request: Request):
    agent = getattr(request.app.state, "parental_agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="Identity module not available")
    return agent


def _require_auth(request: Request) -> None:
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_admin_or_superadmin(request: Request) -> None:
    _require_auth(request)
    role = getattr(request.state, "role", None)
    if role not in {"admin"}:
        raise HTTPException(status_code=403, detail="Admin role required")


def _get_user_id_from_request(request: Request) -> str:
    """Map the authenticated token to a user_id.

    Master key → ronny_wolter.
    Other keys → look up from profile store by api_key field (future).
    For now: admin role → ronny_wolter; others → "anonymous".
    """
    import os
    master_key = os.environ.get("GENUS_MASTER_KEY", "")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[len("Bearer "):] if auth_header.startswith("Bearer ") else ""
    if master_key and token == master_key:
        return "ronny_wolter"
    actor = getattr(request.state, "actor", None)
    if actor is not None and actor.user_id:
        return actor.user_id
    # Default: use the role as a hint (placeholder until user-key mapping is built)
    role = getattr(request.state, "role", "guest")
    return f"__role_{role}"


@router.get("/v1/identity/me")
async def get_actor_identity(request: Request) -> Dict[str, Any]:
    """Return actor identity resolved from API key authentication."""
    _require_auth(request)
    actor = getattr(request.state, "actor", None)
    if actor is None:
        raise HTTPException(
            status_code=500,
            detail="Internal error: actor identity not set in request context",
        )
    return actor.as_identity_payload()


# ---------------------------------------------------------------------------
# Own profile
# ---------------------------------------------------------------------------


@router.get("/me")
async def get_my_profile(request: Request) -> Dict[str, Any]:
    """Return the authenticated user's own profile."""
    _require_auth(request)
    profile_store = _get_profile_store(request)
    user_id = _get_user_id_from_request(request)
    profile = await profile_store.get(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found — start onboarding")
    return profile.model_dump(mode="json")


@router.put("/me")
async def update_my_profile(request: Request, body: ProfileUpdate) -> Dict[str, Any]:
    """Update own profile fields."""
    _require_auth(request)
    profile_store = _get_profile_store(request)
    user_id = _get_user_id_from_request(request)
    profile = await profile_store.get(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    if body.display_name is not None:
        profile = profile.model_copy(update={"display_name": body.display_name})
    if body.preferred_language is not None:
        profile = profile.model_copy(update={"preferred_language": body.preferred_language})
    if body.response_style is not None:
        profile = profile.model_copy(update={"response_style": body.response_style})
    if body.interests is not None:
        profile = profile.model_copy(update={"interests": body.interests})
    if body.projects is not None:
        profile = profile.model_copy(update={"projects": body.projects})

    await profile_store.save(profile)
    return profile.model_dump(mode="json")


@router.get("/me/permissions")
async def get_my_permissions(request: Request) -> Dict[str, Any]:
    """Return which agents the authenticated user may use."""
    _require_auth(request)
    profile_store = _get_profile_store(request)
    user_id = _get_user_id_from_request(request)
    profile = await profile_store.get(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {
        "user_id": user_id,
        "system_role": profile.system_role.value,
        "allowed_agents": profile.allowed_agents,
        "denied_agents": profile.denied_agents,
        "child_settings": (
            profile.child_settings.model_dump() if profile.child_settings else None
        ),
    }


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


@router.get("/groups")
async def list_my_groups(request: Request) -> List[Dict[str, Any]]:
    """Return groups that the authenticated user belongs to."""
    _require_auth(request)
    group_store = _get_group_store(request)
    user_id = _get_user_id_from_request(request)
    groups = await group_store.get_groups_for_user(user_id)
    return [g.model_dump(mode="json") for g in groups]


@router.post("/groups", status_code=201)
async def create_group(request: Request, body: CreateGroupRequest) -> Dict[str, Any]:
    """Create a new group."""
    _require_auth(request)
    from genus.identity.models import Group, GroupMember, GroupType
    group_store = _get_group_store(request)
    user_id = _get_user_id_from_request(request)

    try:
        group_type = GroupType(body.group_type)
    except ValueError:
        group_type = GroupType.CUSTOM

    # Build group_id from name
    safe_name = "".join(c if c.isalnum() else "_" for c in body.name.lower())
    group_id = f"{safe_name}_{user_id}"[:64]

    existing = await group_store.get(group_id)
    if existing:
        raise HTTPException(status_code=409, detail="Group already exists")

    group = Group(
        group_id=group_id,
        name=body.name,
        group_type=group_type,
        admin_user_id=user_id,
        members=[GroupMember(user_id=user_id, role="admin")],
    )
    await group_store.save(group)
    return group.model_dump(mode="json")


@router.get("/groups/{group_id}")
async def get_group(request: Request, group_id: str) -> Dict[str, Any]:
    """Return group details."""
    _require_auth(request)
    group_store = _get_group_store(request)
    user_id = _get_user_id_from_request(request)
    group = await group_store.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    # Must be member or admin/superadmin
    profile_store = _get_profile_store(request)
    profile = await profile_store.get(user_id)
    is_superadmin = profile and profile.is_superadmin()
    if not group.is_member(user_id) and not is_superadmin:
        raise HTTPException(status_code=403, detail="Not a member of this group")
    return group.model_dump(mode="json")


@router.post("/groups/{group_id}/invite", status_code=200)
async def invite_member(
    request: Request, group_id: str, body: InviteMemberRequest
) -> Dict[str, Any]:
    """Invite a user to a group."""
    _require_auth(request)
    from genus.identity.models import GroupMember
    group_store = _get_group_store(request)
    user_id = _get_user_id_from_request(request)
    group = await group_store.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.admin_user_id != user_id:
        profile_store = _get_profile_store(request)
        profile = await profile_store.get(user_id)
        if not (profile and profile.is_superadmin()):
            raise HTTPException(status_code=403, detail="Only group admin may invite")
    if group.is_member(body.user_id):
        raise HTTPException(status_code=409, detail="Already a member")
    group.members.append(GroupMember(user_id=body.user_id, role=body.role))
    await group_store.save(group)
    return {"status": "invited", "user_id": body.user_id, "group_id": group_id}


# ---------------------------------------------------------------------------
# User management (Admin / Superadmin)
# ---------------------------------------------------------------------------


@router.get("/users")
async def list_users(request: Request) -> List[Dict[str, Any]]:
    """Return all user profiles. Requires admin role."""
    _require_admin_or_superadmin(request)
    profile_store = _get_profile_store(request)
    profiles = await profile_store.list_all()
    return [p.model_dump(mode="json") for p in profiles]


@router.get("/users/{user_id}")
async def get_user(request: Request, user_id: str) -> Dict[str, Any]:
    """Return details for a specific user. Requires admin role."""
    _require_admin_or_superadmin(request)
    profile_store = _get_profile_store(request)
    profile = await profile_store.get(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    return profile.model_dump(mode="json")


@router.put("/users/{user_id}/permissions")
async def set_user_permissions(
    request: Request, user_id: str, body: SetPermissionsRequest
) -> Dict[str, Any]:
    """Set allowed/denied agents for a user. Requires admin role."""
    _require_admin_or_superadmin(request)
    profile_store = _get_profile_store(request)
    profile = await profile_store.get(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    updates: Dict[str, Any] = {}
    if body.allowed_agents is not None:
        updates["allowed_agents"] = body.allowed_agents
    if body.denied_agents is not None:
        updates["denied_agents"] = body.denied_agents
    if updates:
        profile = profile.model_copy(update=updates)
        await profile_store.save(profile)
    return profile.model_dump(mode="json")


@router.get("/parental/report/{child_user_id}")
async def get_parental_report(request: Request, child_user_id: str) -> Dict[str, Any]:
    """Generate a daily report for a child account. Requires admin role."""
    _require_admin_or_superadmin(request)
    parental_agent = _get_parental_agent(request)
    report = await parental_agent.generate_daily_report(child_user_id)
    return report


# ---------------------------------------------------------------------------
# Account lock / unlock (Superadmin only)
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/lock")
async def lock_user(request: Request, user_id: str) -> Dict[str, Any]:
    """Lock a user account. Requires admin role."""
    _require_admin_or_superadmin(request)
    profile_store = _get_profile_store(request)
    profile = await profile_store.get(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    profile = profile.model_copy(update={"onboarding_complete": False})
    await profile_store.save(profile)
    return {"status": "locked", "user_id": user_id}


@router.post("/users/{user_id}/unlock")
async def unlock_user(request: Request, user_id: str) -> Dict[str, Any]:
    """Unlock a user account. Requires admin role."""
    _require_admin_or_superadmin(request)
    profile_store = _get_profile_store(request)
    profile = await profile_store.get(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    profile = profile.model_copy(update={"onboarding_complete": True})
    await profile_store.save(profile)
    return {"status": "unlocked", "user_id": user_id}
