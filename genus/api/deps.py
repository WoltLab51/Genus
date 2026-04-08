"""
FastAPI Dependencies

Provides reusable dependency functions:
- get_run_store(request)    → JsonlRunStore from app.state or default instance
- get_message_bus(request) → MessageBus from app.state
- verify_operator(request)  → raises HTTPException 403 if not authorized
- verify_admin(request)     → raises HTTPException 403 if not authorized
- get_kill_switch(request)  → KillSwitch from app.state or None
"""

from typing import Optional

from fastapi import HTTPException, Request

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


def verify_operator(request: Request) -> None:
    """Verify that the caller has operator-level access.

    For v1: ApiKeyMiddleware already authenticated the caller before the
    request reaches any route handler.  This dependency is a guard-rail that
    raises 403 if the request somehow arrives here without the ``authenticated``
    flag set on ``request.state`` (which the middleware sets on success).

    Role-level enforcement via the role model follows in Phase 2.

    Raises:
        HTTPException: 403 if the request is missing authentication context.
    """
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=403, detail="Forbidden")


def verify_admin(request: Request) -> None:
    """Verify that the caller has admin-level access.

    For v1: same mechanism as verify_operator — ApiKeyMiddleware sets
    request.state.authenticated. Admin role enforcement via role model
    follows in a future phase.

    Raises:
        HTTPException: 403 if not authenticated.
    """
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=403, detail="Forbidden")


def get_kill_switch(request: Request) -> Optional[object]:
    """Return the KillSwitch instance from app state, or None."""
    return getattr(request.app.state, "kill_switch", None)


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
