"""Memory API v1 routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from genus.identity.authorization import AuthorizationError, Operation, authorize
from genus.memory.episode_store import Episode
from genus.memory.fact_store import ConflictDetectedError, SemanticFact

router = APIRouter(tags=["memory"])


class UpsertFactRequest(BaseModel):
    key: str
    value: str
    user_id: Optional[str] = None
    scope: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None


class CreateEpisodeRequest(BaseModel):
    summary: str
    topics: List[str] = []
    session_ids: List[str] = []
    message_count: int = 0
    source: str = "api"
    user_id: Optional[str] = None
    scope: Optional[str] = None


def _require_auth(request: Request) -> None:
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _get_fact_store(request: Request):
    store = getattr(request.app.state, "fact_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Memory module not available")
    return store


def _get_episode_store(request: Request):
    store = getattr(request.app.state, "episode_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Memory module not available")
    return store


def _resolve_user_id(request: Request, requested_user_id: Optional[str]) -> str:
    if requested_user_id:
        return requested_user_id
    actor = getattr(request.state, "actor", None)
    if actor is not None and actor.user_id:
        return actor.user_id
    raise HTTPException(status_code=400, detail="user_id is required when actor has no user_id")


def _resolve_scope(scope: Optional[str], user_id: str) -> str:
    return scope or f"private:{user_id}"


def _validate_scope_user(scope: str, user_id: str) -> None:
    if scope.startswith("private:") and scope.split(":", 1)[1] != user_id:
        raise HTTPException(status_code=400, detail="private scope must match user_id")


def _authorize(request: Request, operation: Operation, scope: str) -> None:
    actor = getattr(request.state, "actor", None)
    if actor is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    registry = getattr(request.app.state, "actor_registry", None)
    try:
        authorize(actor, operation, scope, registry=registry)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _fact_to_payload(fact: SemanticFact) -> Dict[str, Any]:
    return {
        "key": fact.key,
        "value": fact.value,
        "notes": fact.notes,
        "source": fact.source,
        "scope": fact.scope,
        "created_by": fact.created_by,
        "created_at": fact.created_at,
        "updated_at": fact.updated_at,
    }


def _episode_to_payload(episode) -> Dict[str, Any]:
    return {
        "episode_id": episode.episode_id,
        "user_id": episode.user_id,
        "summary": episode.summary,
        "topics": episode.topics,
        "session_ids": episode.session_ids,
        "message_count": episode.message_count,
        "source": episode.source,
        "scope": episode.scope,
        "created_by": episode.created_by,
        "created_at": episode.created_at,
    }


@router.get("/v1/memory/facts")
async def list_facts(
    request: Request,
    user_id: Optional[str] = Query(default=None),
    scope: Optional[str] = Query(default=None),
) -> List[Dict[str, Any]]:
    _require_auth(request)
    resolved_user_id = _resolve_user_id(request, user_id)
    resolved_scope = _resolve_scope(scope, resolved_user_id)
    _validate_scope_user(resolved_scope, resolved_user_id)
    _authorize(request, Operation.READ, resolved_scope)

    fact_store = _get_fact_store(request)
    facts = fact_store.get_all(resolved_user_id, scope=resolved_scope)
    return [_fact_to_payload(fact) for fact in facts.values()]


@router.post("/v1/memory/facts", status_code=201)
async def upsert_fact(request: Request, body: UpsertFactRequest) -> Dict[str, Any]:
    _require_auth(request)
    resolved_user_id = _resolve_user_id(request, body.user_id)
    resolved_scope = _resolve_scope(body.scope, resolved_user_id)
    _validate_scope_user(resolved_scope, resolved_user_id)
    _authorize(request, Operation.WRITE, resolved_scope)

    actor = getattr(request.state, "actor", None)
    created_by = actor.actor_id if actor is not None else "system"
    source = body.source or created_by

    fact_store = _get_fact_store(request)
    fact = SemanticFact.create(
        user_id=resolved_user_id,
        key=body.key,
        value=body.value,
        source=source,
        notes=body.notes,
        scope=resolved_scope,
        created_by=created_by,
    )
    try:
        stored = fact_store.upsert(fact)
    except ConflictDetectedError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "key": exc.key,
                "existing_value": exc.existing_value,
                "new_value": exc.new_value,
            },
        ) from exc
    return _fact_to_payload(stored)


@router.get("/v1/memory/episodes")
async def list_episodes(
    request: Request,
    user_id: Optional[str] = Query(default=None),
    scope: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> List[Dict[str, Any]]:
    _require_auth(request)
    resolved_user_id = _resolve_user_id(request, user_id)
    resolved_scope = _resolve_scope(scope, resolved_user_id)
    _validate_scope_user(resolved_scope, resolved_user_id)
    _authorize(request, Operation.READ, resolved_scope)

    episode_store = _get_episode_store(request)
    episodes = episode_store.get_recent(resolved_user_id, limit=limit, scope=resolved_scope)
    return [_episode_to_payload(ep) for ep in episodes]


@router.post("/v1/memory/episodes", status_code=201)
async def create_episode(request: Request, body: CreateEpisodeRequest) -> Dict[str, Any]:
    _require_auth(request)
    resolved_user_id = _resolve_user_id(request, body.user_id)
    resolved_scope = _resolve_scope(body.scope, resolved_user_id)
    _validate_scope_user(resolved_scope, resolved_user_id)
    _authorize(request, Operation.WRITE, resolved_scope)

    actor = getattr(request.state, "actor", None)
    created_by = actor.actor_id if actor is not None else "system"

    episode_store = _get_episode_store(request)
    episode = Episode.create(
        user_id=resolved_user_id,
        summary=body.summary,
        topics=body.topics,
        session_ids=body.session_ids,
        message_count=body.message_count,
        source=body.source,
        scope=resolved_scope,
        created_by=created_by,
    )
    episode_store.append(episode)
    return _episode_to_payload(episode)
