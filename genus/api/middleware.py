"""Authentication middleware."""

import logging
from typing import Optional

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for API key authentication.

    Validates API key for all endpoints except excluded paths.
    """

    def __init__(self, app, api_key: str, excluded_paths: Optional[list] = None):
        """
        Initialize authentication middleware.

        Args:
            app: FastAPI application
            api_key: Expected API key
            excluded_paths: List of paths to exclude from authentication
        """
        super().__init__(app)
        self._api_key = api_key
        self._excluded_paths = excluded_paths or []

    async def dispatch(self, request: Request, call_next):
        """
        Process request and validate authentication.

        Args:
            request: The incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response or 401 if authentication fails
        """
        # Check if path is excluded
        if request.url.path in self._excluded_paths:
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            logger.warning(f"Missing Authorization header for {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Missing Authorization header"}
            )

        # Validate API key format: "Bearer <key>"
        parts = auth_header.split(" ")
        if len(parts) != 2 or parts[0] != "Bearer":
            logger.warning(f"Invalid Authorization format for {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid Authorization format. Use: Bearer <api_key>"}
            )

        provided_key = parts[1]

        if provided_key != self._api_key:
            logger.warning(f"Invalid API key for {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid API key"}
            )

        # Authentication successful
        return await call_next(request)
