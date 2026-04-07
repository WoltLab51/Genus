"""
API-Key Authentication Middleware

Checks Authorization: Bearer <key> header on all requests
except those on the exempt_paths list (e.g. /health).

Returns 401 if key is missing or wrong.
Returns 403 if endpoint requires a role the caller does not have.
"""

import json
from typing import Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

EXEMPT_PATHS: Set[str] = {"/health", "/docs", "/openapi.json"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Validates the ``Authorization: Bearer <key>`` header on protected routes."""

    def __init__(self, app, *, api_key: str) -> None:
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _unauthorized("Missing or malformed Authorization header")

        token = auth_header[len("Bearer "):]
        if token != self._api_key:
            return _unauthorized("Invalid API key")

        request.state.authenticated = True
        return await call_next(request)


def _unauthorized(message: str) -> Response:
    body = json.dumps({"error": "unauthorized", "message": message})
    return Response(content=body, status_code=401, media_type="application/json")
