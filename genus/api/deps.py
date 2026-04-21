"""
FastAPI Dependencies

Provides reusable dependency functions:
- get_run_store(request)    → JsonlRunStore from app.state or default instance
- get_message_bus(request) → MessageBus from app.state
- verify_admin(request)     → raises HTTPException 401/403 if not admin
- verify_operator(request)  → raises HTTPException 401/403 if not admin or operator
- verify_reader(request)    → raises HTTPException 401/403 if not authenticated
- get_kill_switch(request)  → KillSwitch from app.state or None
"""

from typing import Optional

from fastapi import HTTPException, Request

from genus.identity.actor_registry import Actor
from genus.memory.store_jsonl import JsonlRunStore


def get_run_store(request: Request) -> JsonlRunStore:
    """Return the JsonlRunStore from app state, or a default instance."""
    store = getattr(request.app.state, "run_store", None)
    if store is None:
        store = JsonlRunStore()
    return store


def get_message_bus(request: Request):
    """Return the MessageBus instance from app state."""
    return request.app.state.message_bus


def verify_admin(request: Request) -> None:
    """Require admin role.

    Raises:
        HTTPException: 401 if the request is missing authentication context.
        HTTPException: 403 if the caller's role is not "admin".
    """
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=401, detail="Unauthorized")
    role = getattr(request.state, "role", None)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def verify_operator(request: Request) -> None:
    """Require operator or admin role.

    Raises:
        HTTPException: 401 if the request is missing authentication context.
        HTTPException: 403 if the caller's role is neither "admin" nor "operator".
    """
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=401, detail="Unauthorized")
    role = getattr(request.state, "role", None)
    if role not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Operator role required")


def verify_reader(request: Request) -> None:
    """Require reader, operator, or admin role (any authenticated user).

    Raises:
        HTTPException: 401 if the request is missing authentication context.
        HTTPException: 403 if the caller has no recognised role.
    """
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=401, detail="Unauthorized")
    role = getattr(request.state, "role", None)
    if role not in {"admin", "operator", "reader"}:
        raise HTTPException(status_code=403, detail="Reader role required")


def get_kill_switch(request: Request) -> Optional[object]:
    """Return the KillSwitch instance from app state, or None."""
    return getattr(request.app.state, "kill_switch", None)


def get_current_actor(request: Request) -> Actor:
    """Return the authenticated actor from request state."""
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=401, detail="Unauthorized")
    actor = getattr(request.state, "actor", None)
    if actor is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return actor


def assert_kill_switch_consistent(app) -> None:
    """Assert that app.state.kill_switch and MessageBus.kill_switch are the same instance.

    Call this during lifespan startup to catch misconfiguration early.

    Raises:
        RuntimeError: If both are set but are different instances.
    """
    api_ks = getattr(app.state, "kill_switch", None)
    bus = getattr(app.state, "message_bus", None)
    if api_ks is None or bus is None:
        return
    bus_ks = getattr(bus, "_kill_switch", None) or getattr(bus, "kill_switch", None)
    if bus_ks is not None and bus_ks is not api_ks:
        raise RuntimeError(
            "KillSwitch mismatch: app.state.kill_switch and MessageBus.kill_switch "
            "are different instances. POST /kill-switch/activate would have no effect on the bus."
        )
