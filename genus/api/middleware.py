"""
API-Key Authentication Middleware

Checks Authorization: Bearer <key> header on all requests
except those on the exempt_paths list (e.g. /health).

Returns 401 if key is missing or wrong.
Returns 403 if endpoint requires a role the caller does not have.

Role model:
- admin_key   → role "admin"   (darf alles)
- operator_key → role "operator" (darf Operator + Reader)
- reader_key  → role "reader"  (nur GET-Endpoints)
"""

import json
from typing import Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from genus.identity.actor_registry import ActorRegistry, build_actor_registry

EXEMPT_PATHS: Set[str] = {"/health", "/docs", "/openapi.json", "/", "/favicon.ico"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Validates the ``Authorization: Bearer <key>`` header on protected routes.

    Builds a key→role lookup table from the provided keys.  A single ``api_key``
    (legacy mode) is treated as an admin key so it gains all permissions.
    """

    def __init__(
        self,
        app,
        *,
        admin_key: str = "",
        operator_key: str = "",
        reader_key: str = "",
        actor_registry: Optional[ActorRegistry] = None,
    ) -> None:
        super().__init__(app)
        self._registry = actor_registry or build_actor_registry(
            admin_key=admin_key,
            operator_key=operator_key,
            reader_key=reader_key,
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_PATHS or request.url.path.startswith("/static/"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _unauthorized("Missing or malformed Authorization header")

        token = auth_header[len("Bearer "):]
        actor = self._registry.lookup_actor(token)
        if actor is None:
            return _unauthorized("Invalid API key")

        request.state.authenticated = True
        request.state.role = actor.role.api_role
        request.state.actor = actor
        return await call_next(request)


def _unauthorized(message: str) -> Response:
    body = json.dumps({"error": "unauthorized", "message": message})
    return Response(content=body, status_code=401, media_type="application/json")
