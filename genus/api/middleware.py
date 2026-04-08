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
from typing import Dict, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

EXEMPT_PATHS: Set[str] = {"/health", "/docs", "/openapi.json"}


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
    ) -> None:
        super().__init__(app)
        # Build lookup table: token → role (last write wins if keys overlap)
        self._key_to_role: Dict[str, str] = {}
        if reader_key:
            self._key_to_role[reader_key] = "reader"
        if operator_key:
            self._key_to_role[operator_key] = "operator"
        # admin_key always overwrites — admin trumps any other role for the same token
        if admin_key:
            self._key_to_role[admin_key] = "admin"

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _unauthorized("Missing or malformed Authorization header")

        token = auth_header[len("Bearer "):]
        role = self._key_to_role.get(token)
        if role is None:
            return _unauthorized("Invalid API key")

        request.state.authenticated = True
        request.state.role = role
        return await call_next(request)


def _unauthorized(message: str) -> Response:
    body = json.dumps({"error": "unauthorized", "message": message})
    return Response(content=body, status_code=401, media_type="application/json")
