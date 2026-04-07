"""
Error Handling Middleware

Catches unhandled exceptions and returns structured JSON error responses.

Format:
    {"error": "<error_type>", "message": "<human-readable>"}

Never leaks internal details (no stack traces) in production.
"""

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Catches unhandled exceptions and returns structured JSON."""

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception:
            body = json.dumps(
                {
                    "error": "internal_error",
                    "message": "An unexpected error occurred",
                }
            )
            return Response(
                content=body,
                status_code=500,
                media_type="application/json",
            )
