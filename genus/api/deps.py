"""
FastAPI Dependencies

Provides reusable dependency functions:
- get_message_bus(request) → MessageBus from app.state
- verify_operator(request)  → raises HTTPException 403 if not authorized
"""

from fastapi import HTTPException, Request


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
